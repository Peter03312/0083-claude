#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify 一次性服务编排脚本。

依次完成：
1. 传播算法与引擎/API 测试（pytest）；
2. 前端生产构建（vite build，含 vue-tsc）；
3. 通过**真实 HTTP** 等待 web/api 就绪，打开校样页，提交一份故事板，
   并验证修订冻结、影响域、跨修订拒绝、以及一个确定性反例被抓出。

任何一步失败立即以非零码退出，容器随之结束。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import requests

WEB_URL = os.environ.get("WEB_URL", "http://web:80")
API_URL = os.environ.get("API_URL", "http://api:8000")
WEB_PORT_PROXY = os.environ.get("WEB_PUBLIC_URL", "")  # 宿主侧地址（可选）


def step(title: str) -> None:
    print(f"\n\033[1;36m=== {title} ===\033[0m", flush=True)


def run(cmd: list[str], cwd: str | None = None) -> None:
    print("$", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"命令失败（退出码 {result.returncode}）：{' '.join(cmd)}", file=sys.stderr)
        sys.exit(result.returncode)


def wait_for(url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=3)
            if resp.status_code < 500:
                return
        except requests.RequestException as exc:
            last_err = exc
        time.sleep(1)
    raise SystemExit(f"等待 {url} 超时：{last_err}")


def must(condition: bool, message: str) -> None:
    if not condition:
        print(f"✕ {message}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ {message}")


def main() -> None:
    api_dir = os.environ.get("API_DIR", "/srv/api")
    web_dir = os.environ.get("WEB_DIR", "/srv/web")

    step("1/4 后端：引擎、传播算法、API 测试")
    run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=api_dir)

    step("2/4 前端：类型检查 + 生产构建")
    run(["npm", "run", "build"], cwd=web_dir)

    step("3/4 真实 HTTP：等待 web / api 常驻组件")
    wait_for(API_URL + "/api/health")
    wait_for(WEB_URL + "/healthz")
    health = requests.get(API_URL + "/api/health", timeout=5).json()
    must(health == {"ok": True}, "api /api/health 返回 ok")

    # 通过 web 的 nginx 反代访问 API（用户真实路径）。
    via_web = WEB_URL.rstrip("/") + "/api/health"
    must(requests.get(via_web, timeout=5).json() == {"ok": True},
         "经 web 反代访问 /api/health 成功")

    step("4/4 真实 HTTP：打开校样页并提交故事板（冻结/影响域/反例）")
    end_to_end()
    print("\n\033[1;32mVERIFY OK：传播算法、API、生产构建与真实 HTTP 校样全部通过\033[0m")


def end_to_end() -> None:
    s = requests.Session()

    # 打开校样页：首页 HTML 必须真的由 web 提供且挂载点存在。
    page = s.get(WEB_URL + "/", timeout=5)
    must(page.status_code == 200 and 'id="app"' in page.text,
         "GET / 返回校样应用 HTML")
    must("/assets/" in page.text, "HTML 引用了生产构建产物")

    # 最新修订由播种产生（sample_valid 链的最后一条）。
    latest = s.get(API_URL + "/api/revisions/latest", timeout=5).json()
    must(latest["proof"]["status"] == "contradiction",
         "播种链最新修订是跨支线反例（contradiction）")
    # 回溯链首：sample_valid 必须是通过的冻结校样。
    first = s.get(API_URL + "/api/revisions/1", timeout=5).json()
    must(first["proof"]["status"] == "valid",
         "修订 #1（sample_valid）冻结校样通过：每条可选路线都按时相遇")
    must(first["proof"]["counts"]["passed"] == 4
         and first["proof"]["counts"]["failed"] == 0,
         "2×2 四个结局全部通过")

    # 旧冻结校样不得漂移：再取一次逐字节一致。
    again = s.get(API_URL + "/api/revisions/1", timeout=5).json()
    must(again["proof"] == first["proof"], "旧修订 #1 冻结校样重复读取一致")

    # 真实提交一次编辑：把 sample_valid 的画廊时长改成 3，parent 指向 #1。
    spec = json.loads(json.dumps(first["spec"]))
    for scene in spec["scenes"]:
        if scene["id"] == "gallery":
            scene["durations"] = [3]
    spec["title"] = "verify 提交：画廊多停一分钟"
    created = s.post(API_URL + "/api/revisions", timeout=10,
                     json={"spec": spec, "parent_id": 1, "note": "verify 编辑"})
    must(created.status_code == 201, f"POST /api/revisions 201（实际 {created.status_code}）")
    rev = created.json()
    must(rev["proof"]["status"] == "contradiction", "新修订抓到会面时差反例")
    fc = rev["proof"]["first_contradiction"]
    must(fc["code"] == "meeting", f"首矛盾类型 meeting（实际 {fc['code']}）")
    must(fc["diff_minutes"] == 1, f"相差 1 分钟（实际 {fc['diff_minutes']}）")
    must(fc["story_time"] == 6, f"故事时间第 6 分钟（实际 {fc['story_time']}）")
    must({e["scene"] for e in fc["events"]} == {"belltower"},
         "相关事件定位在钟楼会面点")
    must(fc["retell"]["a"]["steps"][-1]["scene"] == "belltower"
         and fc["retell"]["b"]["steps"][-1]["scene"] == "belltower",
         "可复述两条路线的终点")

    # 影响域：只有画廊相关结局重算（路线级精确，双连廊结局 #3 不在内）。
    scope = rev["changes_from_parent"]
    must(scope is not None and scope["recompute_indices"] == [0, 1, 2],
         f"图依赖影响域为结局 0/1/2（实际 {scope and scope['recompute_indices']}）")
    must("corridor_w" not in scope["dirty_scenes"],
         "连廊场景不在画廊时长编辑的影响闭包内")

    # 提交一个地点不可达反例（删掉教学楼→钟楼转场）。
    unreachable = json.loads(json.dumps(first["spec"]))
    unreachable["transitions"] = [
        t for t in unreachable["transitions"]
        if not ({t["from"], t["to"]} == {"教学楼", "钟楼"})
    ]
    resp_un = s.post(API_URL + "/api/revisions", timeout=10,
                     json={"spec": unreachable, "parent_id": rev["revision_id"],
                           "note": "verify 缺转场"})
    rev_un = resp_un.json()
    cut = rev_un["proof"]["counts"]
    must(cut["cut_a"] >= 1 and cut["cut_b"] >= 1, "缺最短转场导致路线中断（不可瞬移）")
    codes = {o["code"] for o in rev_un["proof"]["outcomes"] if not o["ok"]}
    must("location-unreachable" in codes, "存在 location-unreachable 矛盾")

    # 中间场景窗口漏报回归：窗口只挂在中途画廊，终点会面同刻也必须失败。
    mid = json.loads(json.dumps(first["spec"]))
    mid["windows"] = [{"scene": "gallery", "open": 0, "close": 0}]
    resp_mid = s.post(API_URL + "/api/revisions", timeout=10,
                      json={"spec": mid, "parent_id": rev_un["revision_id"],
                            "note": "verify 中途窗口违规"})
    must(resp_mid.status_code == 201, "中途窗口违规故事板结构合法、已提交")
    rev_mid = resp_mid.json()
    fc_mid = rev_mid["proof"]["first_contradiction"]
    must(fc_mid["code"] == "window-late" and fc_mid["events"][0]["scene"] == "gallery",
         "窗口挂在路线中间场景时同样被抓出（不漏报）")
    must(rev_mid["proof"]["counts"]["passed"] == 1
         and rev_mid["proof"]["counts"]["failed"] == 3,
         "任一方经过画廊的 3 个结局失败，双连廊结局不被连坐")

    # 结局详情经真实 HTTP 获取，且事件时间带包含会面/到达事件。
    detail = s.get(f"{API_URL}/api/revisions/1/outcomes/0", timeout=5).json()
    kinds = {e["kind"] for e in detail["events"]}
    must({"arrival", "departure", "meeting"} <= kinds,
         "结局详情时间带含到达/离开/会面事件")
    must(detail["first"] is None, "sample_valid 结局 #0 无矛盾")

    # 结构非法（环）必须 422 且不产生新修订。
    cyclic = json.loads(json.dumps(first["spec"]))
    cyclic["scenes"][0]["choices"] = [
        {"to": "gallery"}, {"to": "corridor_w"},
    ]
    gallery = next(x for x in cyclic["scenes"] if x["id"] == "gallery")
    gallery["choices"] = [{"to": "gate"}]
    bad = s.post(API_URL + "/api/revisions", timeout=5,
                 json={"spec": cyclic, "parent_id": 1})
    must(bad.status_code == 422 and bad.json()["error"] == "structure",
         "含环故事板被结构校验拒绝（422）")

    # 跨修订错贴：用不存在的路线号查结局必须 422。
    stale = s.post(f"{API_URL}/api/revisions/{rev_un['revision_id']}/outcomes/lookup",
                   timeout=5, json={"ra": "x9-x9", "rb": "x9-x9"})
    must(stale.status_code == 422, "跨修订/不存在的旧路线标识被拒绝（防异步错贴）")

    # 再读旧修订：冻结校样仍未漂移。
    frozen = s.get(API_URL + "/api/revisions/1", timeout=5).json()
    must(frozen["proof"] == first["proof"], "多次编辑后修订 #1 冻结校样仍不漂移")


if __name__ == "__main__":
    main()
