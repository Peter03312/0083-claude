# -*- coding: utf-8 -*-
"""内置示例故事板（钟楼 / 连廊双路线）。

只提供作者结构样例，不包含续写台词或剧情推荐。

样例校样时刻（整数分钟）：
  绕钟楼：校门(0~1) →1′ 画廊(2~4) →2′ 钟楼(6)
  穿连廊：校门(0~1) →1′ 连廊西(2~3) →1′ 连廊东/教学楼(4~5) →1′ 钟楼(6)
两条可选路线都在第 6 分钟到达同一“钟声会面”。
"""

from __future__ import annotations

import copy


def _base() -> dict:
    return {
        "title": "艺术周声音漫游 · 钟楼与连廊",
        "start": "gate",
        "scenes": [
            {
                "id": "gate",
                "label": "校门（起点）",
                "location": "校门广场",
                "durations": [1],
                "choices": [
                    {"to": "gallery", "label": "绕钟楼方向"},
                    {"to": "corridor_w", "label": "穿连廊方向"},
                ],
            },
            {
                "id": "gallery",
                "label": "画廊留言墙",
                "location": "艺术楼",
                "durations": [2],
                "choices": [{"to": "belltower", "label": "走向钟楼"}],
            },
            {
                "id": "corridor_w",
                "label": "玻璃连廊西端",
                "location": "连廊",
                "durations": [1],
                "choices": [{"to": "corridor_e", "label": "穿过连廊"}],
            },
            {
                "id": "corridor_e",
                "label": "连廊东端",
                "location": "教学楼",
                "durations": [1],
                "choices": [{"to": "belltower", "label": "走向钟楼"}],
            },
            {
                "id": "belltower",
                "label": "钟楼下的同声景",
                "location": "钟楼",
                "durations": [3],
                "choices": [],
            },
        ],
        "windows": [
            {"scene": "belltower", "open": 5, "close": 8},
            {"scene": "corridor_e", "open": 3, "close": 8},
        ],
        "transitions": [
            {"from": "校门广场", "to": "艺术楼", "minutes": 1},
            {"from": "校门广场", "to": "连廊", "minutes": 1},
            {"from": "艺术楼", "to": "钟楼", "minutes": 2},
            {"from": "连廊", "to": "教学楼", "minutes": 1},
            {"from": "教学楼", "to": "钟楼", "minutes": 1},
        ],
        "meetings": [
            {"kind": "meeting", "scene_a": "belltower", "scene_b": "belltower",
             "label": "钟声会面"},
        ],
        "messages": [
            {
                "kind": "message",
                "send_role": "a",
                "send_scene": "gate",
                "read_role": "b",
                "read_scene": "belltower",
                "label": "出发口信",
            },
        ],
    }


SAMPLES: dict[str, dict] = {}


def _build() -> None:
    valid = _base()
    SAMPLES["sample_valid"] = valid

    bad = copy.deepcopy(valid)
    # 画廊多停留 1 分钟（钟楼 6 → 7）：与走连廊的同伴在钟楼差 1 分钟，
    # “只比最早最晚”看不出的中间空洞在这里被逐结局抓出。
    bad["title"] = "反例：画廊多停一分钟"
    for scene in bad["scenes"]:
        if scene["id"] == "gallery":
            scene["durations"] = [3]
    SAMPLES["sample_bad"] = bad

    unreachable = copy.deepcopy(valid)
    unreachable["title"] = "反例：教学楼→钟楼缺少转场（不能瞬间跨楼）"
    unreachable["transitions"] = [
        t for t in unreachable["transitions"]
        if not ({t["from"], t["to"]} == {"教学楼", "钟楼"})
    ]
    SAMPLES["sample_unreachable"] = unreachable

    crossbranch = copy.deepcopy(valid)
    crossbranch["title"] = "反例：回信跨支线引用另一路才有的发送"
    crossbranch["messages"].append(
        {
            "kind": "message",
            "send_role": "a",
            "send_scene": "corridor_e",  # A 若走画廊支线，则不经过这里
            "read_role": "b",
            "read_scene": "belltower",
            "label": "跨支线回信",
        }
    )
    SAMPLES["sample_crossbranch"] = crossbranch


_build()
