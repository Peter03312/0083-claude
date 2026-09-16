# -*- coding: utf-8 -*-
"""故事板数据模型与结构校验。

作者输入（单一起点、有限无环的双角色场景图）：

* ``scenes[*]``：1~3 个整数分钟时长（选择项）、地点、按数组顺序裁决的选择边；
* ``windows``：场景的绝对时间窗口（按整数分钟）；
* ``transitions``：地点之间的*最短*转场分钟数（缺边即不可达，不是 0）；
* ``meetings``：要求两人同一刻出现的会面配对（角色 → 场景）；
* ``messages``：阅读事件必须显式引用发送事件。

结构问题（无环、起点、引用存在性等）抛 :class:`StoryboardError`；
故事时间上的矛盾留给校样引擎逐结局产出。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

ROLES = ("a", "b")
MAX_DURATIONS = 3
MAX_ROUTES_PER_ROLE = 5000  # 有限图保护：单角色选择序列上限


class StoryboardError(ValueError):
    """作者结构本身无法成立（区别于故事时间矛盾）。"""


@dataclass(frozen=True)
class Edge:
    to: str
    label: str = ""


@dataclass(frozen=True)
class Window:
    open: int
    close: int


@dataclass(frozen=True)
class Transition:
    a: str
    b: str
    minutes: int


@dataclass(frozen=True)
class Meeting:
    kind: str  # meeting
    scene_a: str
    scene_b: str
    label: str = ""


@dataclass(frozen=True)
class Message:
    kind: str  # message
    send_role: str
    send_scene: str
    read_role: str
    read_scene: str
    label: str = ""


@dataclass(frozen=True)
class Scene:
    id: str
    durations: tuple[int, ...]
    location: str
    choices: tuple[Edge, ...] = ()
    label: str = ""


@dataclass(frozen=True)
class Storyboard:
    start: str
    scenes: dict[str, Scene]
    windows: dict[str, Window]
    transitions: dict[tuple[str, str], int]
    meetings: tuple[Meeting, ...]
    messages: tuple[Message, ...]
    title: str = ""

    def transition_minutes(self, loc_from: str, loc_to: str) -> int | None:
        """同地点为 0；跨地点只承认作者显式给出的最短转场。"""
        if loc_from == loc_to:
            return 0
        if (loc_from, loc_to) in self.transitions:
            return self.transitions[(loc_from, loc_to)]
        return self.transitions.get((loc_to, loc_from))


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StoryboardError(message)


def _require_int(value: Any, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StoryboardError(message)
    return value


def canonical_json(spec: dict[str, Any]) -> str:
    """规范化 JSON：相同结构产生相同字节串（冻结校样的基础）。"""
    return json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(spec: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()[:16]


def parse_storyboard(raw: Any) -> Storyboard:
    """解析并做全部结构性校验。"""
    _require(isinstance(raw, dict), "故事板必须是 JSON 对象")
    start = raw.get("start")
    _require(isinstance(start, str) and start != "", "start 必须是非空场景 id")

    raw_scenes = raw.get("scenes")
    _require(isinstance(raw_scenes, list) and raw_scenes, "scenes 必须是非空数组")

    scenes: dict[str, Scene] = {}
    for index, item in enumerate(raw_scenes):
        where = f"scenes[{index}]"
        _require(isinstance(item, dict), f"{where} 必须是对象")
        sid = item.get("id")
        _require(isinstance(sid, str) and sid != "", f"{where}.id 必须是非空字符串")
        _require(sid not in scenes, f"场景 id 重复：{sid}")

        durations_raw = item.get("durations")
        _require(
            isinstance(durations_raw, list) and 1 <= len(durations_raw) <= MAX_DURATIONS,
            f"{where}({sid}).durations 必须是 1~3 个选择",
        )
        durations: list[int] = []
        for d in durations_raw:
            minutes = _require_int(d, f"{where}({sid}) 时长必须是整数分钟")
            _require(minutes >= 0, f"{where}({sid}) 时长不能为负")
            durations.append(minutes)
        _require(len(set(durations)) == len(durations), f"{where}({sid}) 时长存在重复选择")

        location = item.get("location")
        _require(isinstance(location, str) and location != "", f"{where}({sid}).location 必须非空")

        choices: list[Edge] = []
        for cindex, choice in enumerate(item.get("choices", []) or []):
            cwhere = f"{where}({sid}).choices[{cindex}]"
            _require(isinstance(choice, dict), f"{cwhere} 必须是对象")
            target = choice.get("to")
            _require(isinstance(target, str) and target != "", f"{cwhere}.to 必须非空")
            label = choice.get("label", "")
            _require(isinstance(label, str), f"{cwhere}.label 必须是字符串")
            choices.append(Edge(to=target, label=label))

        label = item.get("label", "")
        _require(isinstance(label, str), f"{where}({sid}).label 必须是字符串")
        scenes[sid] = Scene(
            id=sid,
            durations=tuple(durations),
            location=location,
            choices=tuple(choices),
            label=label,
        )

    _require(start in scenes, f"start 指向不存在的场景：{start}")

    # 选择边目标必须存在。
    for scene in scenes.values():
        for edge_index, edge in enumerate(scene.choices):
            _require(
                edge.to in scenes,
                f"场景 {scene.id} 的 choices[{edge_index}] 指向不存在的场景 {edge.to}",
            )

    _assert_finite_acyclic(start, scenes)

    # 所有场景必须从起点可达（“地点不可达”的结构性一面）。
    reachable = _reachable_from(start, scenes)
    unreachable = sorted(set(scenes) - reachable)
    _require(not unreachable, f"存在起点不可达的场景：{', '.join(unreachable)}")

    windows = _parse_windows(raw.get("windows", []), scenes)
    transitions = _parse_transitions(raw.get("transitions", []))
    meetings = tuple(_parse_meetings(raw.get("meetings", []), scenes))
    messages = tuple(_parse_messages(raw.get("messages", []), scenes))

    title = raw.get("title", "")
    _require(isinstance(title, str), "title 必须是字符串")

    story = Storyboard(
        start=start,
        scenes=scenes,
        windows=windows,
        transitions=transitions,
        meetings=meetings,
        messages=messages,
        title=title,
    )
    _assert_route_budget(story)
    return story


def _parse_windows(raw: Any, scenes: dict[str, Scene]) -> dict[str, Window]:
    _require(isinstance(raw, list), "windows 必须是数组")
    windows: dict[str, Window] = {}
    for index, item in enumerate(raw):
        where = f"windows[{index}]"
        _require(isinstance(item, dict), f"{where} 必须是对象")
        scene_id = item.get("scene")
        _require(isinstance(scene_id, str) and scene_id in scenes, f"{where}.scene 不存在")
        open_at = _require_int(item.get("open"), f"{where}.open 必须是整数分钟")
        close_at = _require_int(item.get("close"), f"{where}.close 必须是整数分钟")
        _require(open_at >= 0, f"{where}.open 不能为负")
        _require(open_at <= close_at, f"{where} 窗口起点不能晚于终点")
        _require(scene_id not in windows, f"场景 {scene_id} 的时间窗口重复")
        windows[scene_id] = Window(open_at, close_at)
    return windows


def _parse_transitions(raw: Any) -> dict[tuple[str, str], int]:
    _require(isinstance(raw, list), "transitions 必须是数组")
    transitions: dict[tuple[str, str], int] = {}
    for index, item in enumerate(raw):
        where = f"transitions[{index}]"
        _require(isinstance(item, dict), f"{where} 必须是对象")
        loc_a = item.get("from")
        loc_b = item.get("to")
        _require(isinstance(loc_a, str) and loc_a != "", f"{where}.from 必须非空")
        _require(isinstance(loc_b, str) and loc_b != "", f"{where}.to 必须非空")
        _require(loc_a != loc_b, f"{where} 同地点不需要转场")
        minutes = _require_int(item.get("minutes"), f"{where}.minutes 必须是整数分钟")
        _require(minutes >= 0, f"{where}.minutes 不能为负")
        key = tuple(sorted((loc_a, loc_b)))
        _require(key not in transitions, f"{where} 地点间转场重复")
        transitions[key] = minutes
    return transitions


def _parse_meetings(raw: Any, scenes: dict[str, Scene]) -> Iterable[Meeting]:
    _require(isinstance(raw, list), "meetings 必须是数组")
    for index, item in enumerate(raw):
        where = f"meetings[{index}]"
        _require(isinstance(item, dict), f"{where} 必须是对象")
        kind = item.get("kind", "meeting")
        _require(kind == "meeting", f"{where}.kind 必须是 meeting")
        scene_a = item.get("scene_a")
        scene_b = item.get("scene_b")
        _require(isinstance(scene_a, str) and scene_a in scenes, f"{where}.scene_a 不存在")
        _require(isinstance(scene_b, str) and scene_b in scenes, f"{where}.scene_b 不存在")
        label = item.get("label", "")
        _require(isinstance(label, str), f"{where}.label 必须是字符串")
        yield Meeting(
            kind="meeting",
            scene_a=scene_a,
            scene_b=scene_b,
            label=label,
        )


def _parse_messages(raw: Any, scenes: dict[str, Scene]) -> Iterable[Message]:
    _require(isinstance(raw, list), "messages 必须是数组")
    seen_pairs: set[tuple[str, str, str, str]] = set()
    for index, item in enumerate(raw):
        where = f"messages[{index}]"
        _require(isinstance(item, dict), f"{where} 必须是对象")
        kind = item.get("kind", "message")
        _require(kind == "message", f"{where}.kind 必须是 message")
        send_role = item.get("send_role")
        read_role = item.get("read_role")
        _require(send_role in ROLES, f"{where}.send_role 必须是 a 或 b")
        _require(read_role in ROLES, f"{where}.read_role 必须是 a 或 b")
        send_scene = item.get("send_scene")
        read_scene = item.get("read_scene")
        _require(isinstance(send_scene, str) and send_scene in scenes, f"{where}.send_scene 不存在")
        _require(isinstance(read_scene, str) and read_scene in scenes, f"{where}.read_scene 不存在")
        pair = (send_role, send_scene, read_role, read_scene)
        _require(pair not in seen_pairs, f"{where} 发送/阅读配对重复")
        seen_pairs.add(pair)
        label = item.get("label", "")
        _require(isinstance(label, str), f"{where}.label 必须是字符串")
        yield Message(
            kind="message",
            send_role=send_role,
            send_scene=send_scene,
            read_role=read_role,
            read_scene=read_scene,
            label=label,
        )


def _reachable_from(start: str, scenes: dict[str, Scene]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        stack.extend(edge.to for edge in scenes[sid].choices)
    return seen


def _assert_finite_acyclic(start: str, scenes: dict[str, Scene]) -> None:
    """DFS 三色法检查无环；环的存在会让离散枚举无限化。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(scenes, WHITE)
    stack: list[tuple[str, int]] = [(start, 0)]
    color[start] = GRAY
    while stack:
        sid, edge_index = stack[-1]
        choices = scenes[sid].choices
        if edge_index < len(choices):
            stack[-1] = (sid, edge_index + 1)
            nxt = choices[edge_index].to
            if color[nxt] == GRAY:
                raise StoryboardError(f"场景图存在环，涉及场景：{nxt}")
            if color[nxt] == WHITE:
                color[nxt] = GRAY
                stack.append((nxt, 0))
        else:
            color[sid] = BLACK
            stack.pop()


def _assert_route_budget(story: Storyboard) -> None:
    """估算各角色选择序列数，防止有限但过大的图拖垮枚举。"""
    memo: dict[str, int] = {}

    def count_from(sid: str) -> int:
        if sid in memo:
            return memo[sid]
        scene = story.scenes[sid]
        if not scene.choices:
            total = len(scene.durations)
        else:
            total = len(scene.durations) * sum(count_from(edge.to) for edge in scene.choices)
        memo[sid] = total
        return total

    total = count_from(story.start)
    if total > MAX_ROUTES_PER_ROLE:
        raise StoryboardError(
            f"选择序列数 {total} 超过单角色上限 {MAX_ROUTES_PER_ROLE}，请收敛分支"
        )
