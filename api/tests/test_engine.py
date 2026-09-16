# -*- coding: utf-8 -*-
"""引擎测试：离散时刻空洞、同刻合流、跨支线消息、地点不可达、确定性反例。"""

import pytest

from app.engine import parse_storyboard
from app.engine.model import StoryboardError
from app.engine.proof import prove_revision
from app.engine.routes import enumerate_routes


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

def first_code(proof):
    fc = proof["first_contradiction"]
    return fc["code"] if fc else None


def code_counts(proof):
    counts = {}
    for outcome in proof["outcomes"]:
        counts[outcome["code"]] = counts.get(outcome["code"], 0) + 1
    return counts


# --------------------------------------------------------------------------- #
# 1) 离散时刻空洞：不能用连续区间把不存在的中间时刻当作可会面
# --------------------------------------------------------------------------- #

def _hole_spec(arrival_b):
    """A 的会面点到达时刻为离散集合 {2,4}；B 固定 arrival_b。

    第 3 分钟不在 A 的可达时刻里——“最早 2 / 最晚 4”的区间视图会
    错误地把第 3 分钟当成可会面时刻。
    """
    return {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "L", "durations": [0],
             "choices": [{"to": "x", "label": "A支线"},
                         {"to": "sb", "label": "B支线"}]},
            {"id": "x", "label": "A的时长选择点", "location": "L",
             "durations": [2, 4], "choices": [{"to": "ma"}]},
            {"id": "ma", "label": "A会面标记", "location": "L",
             "durations": [1], "choices": []},
            {"id": "sb", "label": "B的固定点", "location": "L",
             "durations": [arrival_b], "choices": [{"to": "mb"}]},
            {"id": "mb", "label": "B会面标记", "location": "L",
             "durations": [1], "choices": []},
        ],
        "meetings": [{"kind": "meeting", "scene_a": "ma", "scene_b": "mb",
                      "label": "空洞会面"}],
        "transitions": [],
    }


def _participating_outcomes(proof):
    """A 走 s→x 支线、B 走 s→sb 支线的结局。

    route_id 的 token 记“到达本步的边序”：
    A 在第二步（x）记录 e0；B 在第二步（sb）记录 e1。
    """
    def token_at(route_id: str, index: int) -> str:
        parts = route_id.split("/")
        return parts[index] if index < len(parts) else ""

    part = [
        o for o in proof["outcomes"]
        if token_at(o["ra"], 1).startswith("e0-")
        and token_at(o["rb"], 1).startswith("e1-")
    ]
    return part


def test_discrete_time_hole_is_not_an_interval():
    proof_3 = prove_revision(_hole_spec(3))
    participating = _participating_outcomes(proof_3)
    assert len(participating) == 2  # A 的两个时长选择 × B 的唯一路线
    assert all(not o["ok"] and o["code"] == "meeting" for o in participating)
    fc = proof_3["first_contradiction"]
    assert fc["code"] == "meeting" and fc["diff_minutes"] == 1
    # 2 与 4 是真实离散时刻：对应时长选择下可以同刻，另一个选择差 2 分钟。
    for arrival_b in (2, 4):
        proof = prove_revision(_hole_spec(arrival_b))
        part = _participating_outcomes(proof)
        assert len(part) == 2
        assert sum(o["ok"] for o in part) == 1
        assert sum((not o["ok"]) and o["code"] == "meeting" for o in part) == 1


def test_routes_keep_distinct_discrete_moments():
    story = parse_storyboard(_hole_spec(3))
    routes = enumerate_routes(story, "a")
    arrivals = sorted(step.arrival for r in routes
                      for step in r.steps if step.scene_id == "ma")
    assert arrivals == [2, 4]  # 只有两个离散时刻，3 不在其中

# --------------------------------------------------------------------------- #
# 2) 不同来路同刻合流：合流处不得混成一份状态
# --------------------------------------------------------------------------- #

def _converge_spec(r_duration=2):
    return {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "L", "durations": [1],
             "choices": [{"to": "p", "label": "绕钟楼"},
                         {"to": "q", "label": "穿连廊"}]},
            {"id": "p", "location": "L", "durations": [2],
             "choices": [{"to": "m"}]},
            {"id": "q", "location": "L", "durations": [2],
             "choices": [{"to": "r"}, {"to": "m"}]},
            {"id": "r", "location": "L", "durations": [r_duration],
             "choices": [{"to": "m"}]},
            {"id": "m", "label": "合流点", "location": "L",
             "durations": [1], "choices": []},
        ],
        "meetings": [{"kind": "meeting", "scene_a": "m", "scene_b": "m",
                      "label": "合流会面"}],
        "transitions": [],
    }


def test_same_time_convergence_keeps_separate_routes():
    # s 第 0 分钟到、第 1 分钟出发；三条路径全部在第 3 分钟同刻合流于 m：
    # s→p(停留2)→m、s→q(停留2)→m、s→q(停留2)→r(停留0)→m。
    story = parse_storyboard(_converge_spec(r_duration=0))
    routes = enumerate_routes(story, "a")
    assert len(routes) == 3
    m_arrivals = sorted(r.steps[-1].arrival for r in routes)
    assert m_arrivals == [3, 3, 3]
    paths = {"-".join(s.scene_id for s in r.steps) for r in routes}
    assert paths == {"s-p-m", "s-q-m", "s-q-r-m"}
    # 同刻合流仍按独立结局配对：3×3=9 个结局，没有被“合流状态合并”掉。
    proof = prove_revision(_converge_spec(r_duration=0))
    assert proof["counts"]["outcomes"] == 9
    assert proof["status"] == "valid"


def test_convergence_with_distinct_origins_remains_pair_distinguishable():
    """r 停留 2 分钟时三条路同刻；改成 3 分钟后只有 s-q-r-m 迟到（3→4）。"""
    proof = prove_revision(_converge_spec(r_duration=3))
    routes_a = proof["routes"]["a"]
    bad = [r for r in routes_a if any(s["scene"] == "r" for s in r["steps"])]
    good = [r for r in routes_a if not any(s["scene"] == "r" for s in r["steps"])]
    assert len(bad) == 1 and len(good) == 2
    failed = [o for o in proof["outcomes"] if not o["ok"]]
    assert all(o["ra"] == bad[0]["route_id"] or o["rb"] == bad[0]["route_id"]
               for o in failed)
    # 坏路参与的结局：坏×2好 + 2好×坏 + 坏×坏 = 5 个配对中的 4 个唯一结局
    # （坏×坏只有一个结局，不是两个）。另两条来路的两两配对不受污染。
    assert len(failed) == 4
    assert proof["counts"]["passed"] == 5


# --------------------------------------------------------------------------- #
# 3) 消息：发送必须严格早于阅读；跨支线引用要抓
# --------------------------------------------------------------------------- #

def test_message_send_must_strictly_precede_read():
    # 同刻不算：发送严格早于阅读。
    spec = _converge_spec()
    spec["messages"] = [
        {"kind": "message", "send_role": "a", "send_scene": "s",
         "read_role": "b", "read_scene": "s", "label": "同刻消息"},
    ]
    proof = prove_revision(spec)
    assert first_code(proof) == "message-order"
    fc = proof["first_contradiction"]
    assert fc["diff_minutes"] == 0  # 同刻倒置


def test_message_cross_branch_reference():
    # A 有两条支线；corridor 只存在于其中一条。
    # 阅读者固定到达会面点，跨支线的发送在另一些结局里根本不存在。
    spec = {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "L", "durations": [1],
             "choices": [{"to": "corridor"}, {"to": "tower"}]},
            {"id": "corridor", "label": "连廊", "location": "L",
             "durations": [1], "choices": [{"to": "m"}]},
            {"id": "tower", "label": "钟楼", "location": "L",
             "durations": [1], "choices": [{"to": "m"}]},
            {"id": "m", "label": "会面点", "location": "L",
             "durations": [1], "choices": []},
        ],
        "meetings": [{"kind": "meeting", "scene_a": "m", "scene_b": "m",
                      "label": "会面"}],
        "messages": [
            {"kind": "message", "send_role": "a", "send_scene": "corridor",
             "read_role": "b", "read_scene": "m", "label": "跨支线回信"},
        ],
        "transitions": [],
    }
    proof = prove_revision(spec)
    counts = code_counts(proof)
    assert counts["message-unreachable"] == 2  # A 走 tower 的两个配对结局
    assert counts[None] == 2                    # A 走 corridor 的结局有效
    # 会面同刻，因此全局首矛盾是跨支线缺失（按故事时间排序仍先报存在的约束问题）
    assert first_code(proof) == "message-unreachable"


# --------------------------------------------------------------------------- #
# 4) 地点不可达：缺最短转场不能瞬间跨楼
# --------------------------------------------------------------------------- #

def test_missing_transition_cannot_teleport():
    spec = {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "东楼", "durations": [1],
             "choices": [{"to": "m"}]},
            {"id": "m", "label": "西楼", "location": "西楼",
             "durations": [1], "choices": []},
        ],
        "meetings": [{"kind": "meeting", "scene_a": "m", "scene_b": "m",
                      "label": "西楼会面"}],
        "transitions": [],  # 东楼↔西楼没有给出最短转场
    }
    proof = prove_revision(spec)
    assert first_code(proof) == "location-unreachable"
    assert proof["counts"]["cut_a"] == 1 and proof["counts"]["cut_b"] == 1
    route = proof["routes"]["a"][0]
    assert route["ended"] is False
    assert route["fault"]["code"] == "location-unreachable"


def test_zero_transition_is_explicit_and_allowed():
    spec = {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "东楼", "durations": [1],
             "choices": [{"to": "m"}]},
            {"id": "m", "location": "西楼", "durations": [1],
             "choices": []},
        ],
        "meetings": [{"kind": "meeting", "scene_a": "m", "scene_b": "m"}],
        "transitions": [{"from": "东楼", "to": "西楼", "minutes": 0}],
    }
    proof = prove_revision(spec)
    assert proof["status"] == "valid"


# --------------------------------------------------------------------------- #
# 5) 确定性反例：首个矛盾按故事时间/边数/角色/边序裁决，可复述
# --------------------------------------------------------------------------- #

def test_first_contradiction_is_deterministic():
    spec = {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "L", "durations": [1],
             "choices": [{"to": "early", "label": "近路"},
                         {"to": "late", "label": "远路"}]},
            {"id": "early", "location": "L", "durations": [1],
             "choices": [{"to": "m"}]},
            {"id": "late", "location": "L", "durations": [4],
             "choices": [{"to": "m"}]},
            {"id": "m", "location": "L", "durations": [1], "choices": []},
        ],
        "windows": [{"scene": "m", "open": 0, "close": 1}],
        "meetings": [],
        "transitions": [],
    }
    p1 = prove_revision(spec)
    p2 = prove_revision(spec)
    assert p1["first_contradiction"] == p2["first_contradiction"]
    fc = p1["first_contradiction"]
    # 最早出问题的时刻是第 2 分钟（近路到达 m，窗口第 1 分钟关闭），
    # 而不是远路的第 6 分钟——逐结局而非只看最晚。
    assert fc["story_time"] == 2
    assert fc["code"] == "window-late"
    assert fc["retell"]["a"]["steps"][-1]["scene"] == "m"
    assert {e["scene"] for e in fc["events"]} == {"m"}


def test_ordering_prefers_earlier_story_time_then_edges():
    # 两个时长选择：arrival=1（窗口内）与 arrival=5（迟到）。
    spec = {
        "start": "s",
        "scenes": [
            {"id": "s", "location": "L", "durations": [1, 5],
             "choices": [{"to": "m"}]},
            {"id": "m", "location": "L", "durations": [1], "choices": []},
        ],
        "windows": [{"scene": "m", "open": 0, "close": 1}],
        "meetings": [],
        "transitions": [],
    }
    proof = prove_revision(spec)
    fc = proof["first_contradiction"]
    assert fc["code"] == "window-late"
    assert fc["story_time"] == 5
    assert fc["retell"]["a"]["steps"][-1]["arrival"] == 5


# --------------------------------------------------------------------------- #
# 结构校验
# --------------------------------------------------------------------------- #

def test_structure_errors():
    with pytest.raises(StoryboardError):
        parse_storyboard({"start": "x", "scenes": []})
    with pytest.raises(StoryboardError, match="环"):
        parse_storyboard({
            "start": "a",
            "scenes": [
                {"id": "a", "location": "L", "durations": [1],
                 "choices": [{"to": "b"}]},
                {"id": "b", "location": "L", "durations": [1],
                 "choices": [{"to": "a"}]},
            ],
        })
    with pytest.raises(StoryboardError, match="不可达"):
        parse_storyboard({
            "start": "a",
            "scenes": [
                {"id": "a", "location": "L", "durations": [1], "choices": []},
                {"id": "b", "location": "L", "durations": [1], "choices": []},
            ],
        })
    with pytest.raises(StoryboardError, match="1~3"):
        parse_storyboard({
            "start": "a",
            "scenes": [{"id": "a", "location": "L", "durations": [1, 2, 3, 4],
                        "choices": []}],
        })
