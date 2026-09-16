# -*- coding: utf-8 -*-
"""逐结局校样。

把角色 A、B 的每一条离散路线做笛卡尔配对，每个配对就是一个“结局”：

* 窗口：到达时刻必须落在绝对时间窗口内；
* 转场：缺最短转场的序列已在枚举时中断（location-unreachable）；
* 会面：配对的两个场景必须都在该结局的两条路线上，且到达同一刻；
* 消息：阅读场景与被引用的发送场景必须都在路线上，且发送时刻严格早于阅读。

“最早 vs 最晚”的比较在这里不存在——每个结局使用的是各自选择序列的
离散时刻；同刻合流的不同来路仍然是不同路线、不同配对。

全局首个矛盾的裁决键（逐级比较）：
``(故事时间, A 已走边数, B 已走边数, 角色编号, 边序, 代码, 结局序号)``。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Storyboard, StoryboardError, content_hash, parse_storyboard
from .routes import Route, Step, enumerate_routes

ROLE_RANK = {"a": 0, "b": 1}

# 结局可能的矛盾代码
CODES = (
    "window-early",
    "window-late",
    "location-unreachable",
    "meeting",
    "meeting-unreachable",
    "message-order",
    "message-unreachable",
)


@dataclass(frozen=True)
class EventView:
    kind: str  # arrival | departure | meeting | send | read | attempted-edge
    time: int | None
    role: str | None
    scene: str | None
    location: str | None
    label: str
    ref: int | None = None  # 会面/消息在作者数组中的序号


@dataclass(frozen=True)
class Contradiction:
    code: str
    detail: str
    story_time: int | None
    diff_minutes: int | None
    role: str | None
    edge_ord: int | None
    edges_a: int
    edges_b: int
    route_a: str
    route_b: str
    outcome_index: int
    events: tuple[EventView, ...]


def prove_revision(raw_spec: dict) -> dict:
    """解析故事板并产出不可变校样（可直接 JSON 序列化）。"""
    story = parse_storyboard(raw_spec)
    routes_a = enumerate_routes(story, "a")
    routes_b = enumerate_routes(story, "b")

    outcomes: list[dict] = []
    candidates: list[Contradiction] = []

    index = 0
    for route_a in routes_a:
        for route_b in routes_b:
            contradictions = check_pair(story, route_a, route_b, index)
            first = _earliest(contradictions)
            outcomes.append(
                {
                    "i": index,
                    "ra": route_a.route_id,
                    "rb": route_b.route_id,
                    "ta": route_a.steps[-1].arrival,
                    "tb": route_b.steps[-1].arrival,
                    "ended_a": route_a.ended,
                    "ended_b": route_b.ended,
                    "ok": first is None,
                    "code": first.code if first else None,
                    "story_time": first.story_time if first else None,
                }
            )
            if first is not None:
                candidates.append(first)
            index += 1

    global_first = _earliest(candidates) if candidates else None

    return {
        "spec_hash": content_hash(raw_spec),
        "status": "valid" if global_first is None else "contradiction",
        "counts": {
            "routes_a": len(routes_a),
            "routes_b": len(routes_b),
            "outcomes": index,
            "passed": sum(1 for o in outcomes if o["ok"]),
            "failed": sum(1 for o in outcomes if not o["ok"]),
            "cut_a": sum(1 for r in routes_a if not r.ended),
            "cut_b": sum(1 for r in routes_b if not r.ended),
        },
        "routes": {
            "a": [route_json(story, route) for route in routes_a],
            "b": [route_json(story, route) for route in routes_b],
        },
        "outcomes": outcomes,
        "first_contradiction": (
            contradiction_json(story, global_first, routes_a, routes_b)
            if global_first is not None
            else None
        ),
    }


def pair_detail(raw_spec: dict, route_a_id: str, route_b_id: str) -> dict:
    """重算指定路线对的完整事件视图（结局详情，不改动任何冻结校样）。"""
    story = parse_storyboard(raw_spec)
    routes_a = enumerate_routes(story, "a")
    routes_b = enumerate_routes(story, "b")
    route_a = _find_route(routes_a, route_a_id)
    route_b = _find_route(routes_b, route_b_id)
    index = _outcome_index(routes_a, routes_b, route_a, route_b)
    contradictions = check_pair(story, route_a, route_b, index)
    first = _earliest(contradictions)
    return {
        "i": index,
        "route_a": route_json(story, route_a),
        "route_b": route_json(story, route_b),
        "events": [_event_dict(e) for e in _pair_events(story, route_a, route_b)],
        "contradictions": [
            contradiction_json(story, c, routes_a, routes_b) for c in contradictions
        ],
        "first": contradiction_json(story, first, routes_a, routes_b) if first else None,
    }


def _find_route(routes: list[Route], route_id: str) -> Route:
    for route in routes:
        if route.route_id == route_id:
            return route
    raise StoryboardError(f"路线不存在（可能属于另一修订）：{route_id}")


def _outcome_index(routes_a: list[Route], routes_b: list[Route],
                   route_a: Route, route_b: Route) -> int:
    ia = next(i for i, r in enumerate(routes_a) if r.route_id == route_a.route_id)
    ib = next(i for i, r in enumerate(routes_b) if r.route_id == route_b.route_id)
    return ia * len(routes_b) + ib


# --------------------------------------------------------------------------- #
# 配对检查
# --------------------------------------------------------------------------- #

def check_pair(story: Storyboard, route_a: Route, route_b: Route,
               outcome_index: int) -> list[Contradiction]:
    found: list[Contradiction] = []
    edges_pair = (route_a.edges_walked, route_b.edges_walked)

    # 1a) 转场断层（缺最短转场时序列已在枚举期中断）。
    for route in (route_a, route_b):
        if route.fault is not None:
            found.append(
                Contradiction(
                    code=route.fault.kind,
                    detail=route.fault.detail,
                    story_time=None,
                    diff_minutes=None,
                    role=route.role,
                    edge_ord=route.fault.edge_ord,
                    edges_a=edges_pair[0],
                    edges_b=edges_pair[1],
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=_fault_events(story, route),
                )
            )

    # 1b) 窗口：对路线上的**每一步**到达时刻裁决，中途场景也不能漏报。
    for route in (route_a, route_b):
        for step in route.steps:
            window = story.windows.get(step.scene_id)
            if window is None:
                continue
            if window.open <= step.arrival <= window.close:
                continue
            code = "window-early" if step.arrival < window.open else "window-late"
            found.append(
                Contradiction(
                    code=code,
                    detail=(
                        f"第 {step.arrival} 分钟到达{step.label or step.scene_id}"
                        f"（{step.location}），"
                        + (
                            f"早于窗口开启第 {window.open} 分钟"
                            if code == "window-early"
                            else f"晚于窗口关闭第 {window.close} 分钟，"
                                 f"超出 {step.arrival - window.close} 分钟"
                        )
                    ),
                    story_time=step.arrival,
                    diff_minutes=(
                        window.open - step.arrival if code == "window-early"
                        else step.arrival - window.close
                    ),
                    role=route.role,
                    edge_ord=step.edge_ord,
                    edges_a=edges_pair[0],
                    edges_b=edges_pair[1],
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=(
                        EventView("arrival", step.arrival, route.role,
                                  step.scene_id, step.location, step.label),
                    ),
                )
            )

    # 2) 会面：同刻出现。
    for ordinal, meeting in enumerate(story.meetings):
        step_a = route_a.step_at(meeting.scene_a)
        step_b = route_b.step_at(meeting.scene_b)
        if step_a is None or step_b is None:
            found.append(
                Contradiction(
                    code="meeting-unreachable",
                    detail=_meeting_unreachable_detail(meeting, step_a, step_b),
                    story_time=None,
                    diff_minutes=None,
                    role="b" if step_a is not None else "a",
                    edge_ord=None,
                    edges_a=route_a.edges_walked,
                    edges_b=route_b.edges_walked,
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=(
                        _event("arrival", step_a, ordinal, "arrival"),
                        _event("arrival", step_b, ordinal, "arrival"),
                    ),
                )
            )
            continue
        if step_a.arrival != step_b.arrival:
            later_role = "a" if step_a.arrival > step_b.arrival else "b"
            later_step = step_a if later_role == "a" else step_b
            found.append(
                Contradiction(
                    code="meeting",
                    detail=(
                        f"会面“{meeting.label or ordinal + 1}”未能同刻："
                        f"A 在第 {step_a.arrival} 分钟到达 {meeting.scene_a}，"
                        f"B 在第 {step_b.arrival} 分钟到达 {meeting.scene_b}，"
                        f"相差 {abs(step_a.arrival - step_b.arrival)} 分钟"
                    ),
                    story_time=min(step_a.arrival, step_b.arrival),
                    diff_minutes=abs(step_a.arrival - step_b.arrival),
                    role=later_role,
                    edge_ord=later_step.edge_ord,
                    edges_a=route_a.edges_walked,
                    edges_b=route_b.edges_walked,
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=(
                        EventView("meeting", step_a.arrival, "a", meeting.scene_a,
                                  step_a.location, meeting.label or f"会面 {ordinal + 1}", ordinal),
                        EventView("meeting", step_b.arrival, "b", meeting.scene_b,
                                  step_b.location, meeting.label or f"会面 {ordinal + 1}", ordinal),
                    ),
                )
            )

    # 3) 消息：发送必须严格早于阅读（同刻也不行）。
    for ordinal, message in enumerate(story.messages):
        send_route = route_a if message.send_role == "a" else route_b
        read_route = route_a if message.read_role == "a" else route_b
        send_step = send_route.step_at(message.send_scene)
        read_step = read_route.step_at(message.read_scene)
        if send_step is None or read_step is None:
            missing_role = message.send_role if send_step is None else message.read_role
            found.append(
                Contradiction(
                    code="message-unreachable",
                    detail=(
                        f"消息“{message.label or ordinal + 1}”的"
                        f"{'发送' if send_step is None else '阅读'}场景在该结局的路线上不存在"
                    ),
                    story_time=None,
                    diff_minutes=None,
                    role=missing_role,
                    edge_ord=None,
                    edges_a=route_a.edges_walked,
                    edges_b=route_b.edges_walked,
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=(
                        _event("send" if send_step is not None else "arrival",
                               send_step, ordinal, "send"),
                        _event("read" if read_step is not None else "arrival",
                               read_step, ordinal, "read"),
                    ),
                )
            )
            continue
        if send_step.arrival >= read_step.arrival:
            found.append(
                Contradiction(
                    code="message-order",
                    detail=(
                        f"消息“{message.label or ordinal + 1}”时序倒置："
                        f"{message.send_role.upper()} 在第 {send_step.arrival} 分钟于 "
                        f"{message.send_scene} 发送，"
                        f"{message.read_role.upper()} 在第 {read_step.arrival} 分钟于 "
                        f"{message.read_scene} 阅读，"
                        f"阅读比发送早 {send_step.arrival - read_step.arrival} 分钟"
                        if send_step.arrival > read_step.arrival
                        else f"消息“{message.label or ordinal + 1}”发送与阅读同在第 "
                        f"{send_step.arrival} 分钟，发送必须严格早于阅读"
                    ),
                    story_time=read_step.arrival,
                    diff_minutes=read_step.arrival - send_step.arrival,
                    role=message.read_role,
                    edge_ord=read_step.edge_ord,
                    edges_a=route_a.edges_walked,
                    edges_b=route_b.edges_walked,
                    route_a=route_a.route_id,
                    route_b=route_b.route_id,
                    outcome_index=outcome_index,
                    events=(
                        EventView("send", send_step.arrival, message.send_role,
                                  message.send_scene, send_step.location,
                                  message.label or f"消息 {ordinal + 1}", ordinal),
                        EventView("read", read_step.arrival, message.read_role,
                                  message.read_scene, read_step.location,
                                  message.label or f"消息 {ordinal + 1}", ordinal),
                    ),
                )
            )

    return found


def _earliest(contradictions: list[Contradiction]) -> Contradiction | None:
    if not contradictions:
        return None
    return min(contradictions, key=lambda c: (
        c.story_time if c.story_time is not None else 10**18,
        c.edges_a,
        c.edges_b,
        ROLE_RANK.get(c.role, 9),
        c.edge_ord if c.edge_ord is not None else 10**9,
        c.code,
        c.outcome_index,
    ))


def _meeting_unreachable_detail(meeting, step_a, step_b) -> str:
    missing = []
    if step_a is None:
        missing.append(f"A 路线不经过 {meeting.scene_a}")
    if step_b is None:
        missing.append(f"B 路线不经过 {meeting.scene_b}")
    return f"会面“{meeting.label or ''}”无法成立：{'，'.join(missing)}"


def _event(kind: str, step: Step | None, ordinal: int, fallback: str) -> EventView:
    if step is None:
        return EventView(fallback, None, None, None, None, "", ordinal)
    return EventView(kind, step.arrival, step.role, step.scene_id,
                     step.location, step.label, ordinal)


def _fault_events(story: Storyboard, route: Route) -> tuple[EventView, ...]:
    last = route.steps[-1]
    events = [EventView("departure", last.departure, route.role, last.scene_id,
                        last.location, last.label)]
    if route.fault and route.fault.kind == "location-unreachable":
        target = story.scenes[route.fault.scene_id]
        events.append(
            EventView("attempted-edge", None, route.role, target.id, target.location,
                      f"试图经第 {route.fault.edge_ord} 条选择跨越，缺少最短转场")
        )
    return tuple(events)


def _pair_events(story: Storyboard, route_a: Route, route_b: Route) -> list[EventView]:
    """结局时间带用的完整事件表：每人每步到达/离开 + 会面/消息标记。"""
    events: list[EventView] = []
    for route in (route_a, route_b):
        for step in route.steps:
            events.append(EventView("arrival", step.arrival, route.role,
                                    step.scene_id, step.location, step.label))
            events.append(EventView("departure", step.departure, route.role,
                                    step.scene_id, step.location, step.label))
    for ordinal, meeting in enumerate(story.meetings):
        step_a = route_a.step_at(meeting.scene_a)
        step_b = route_b.step_at(meeting.scene_b)
        if step_a and step_b and step_a.arrival == step_b.arrival:
            events.append(EventView("meeting", step_a.arrival, "a/b",
                                    f"{meeting.scene_a}↔{meeting.scene_b}",
                                    f"{step_a.location}/{step_b.location}",
                                    meeting.label or f"会面 {ordinal + 1}", ordinal))
    for ordinal, message in enumerate(story.messages):
        send_route = route_a if message.send_role == "a" else route_b
        read_route = route_a if message.read_role == "a" else route_b
        send_step = send_route.step_at(message.send_scene)
        read_step = read_route.step_at(message.read_scene)
        if send_step is not None:
            events.append(EventView("send", send_step.arrival, message.send_role,
                                    message.send_scene, send_step.location,
                                    message.label or f"消息 {ordinal + 1}", ordinal))
        if read_step is not None:
            events.append(EventView("read", read_step.arrival, message.read_role,
                                    message.read_scene, read_step.location,
                                    message.label or f"消息 {ordinal + 1}", ordinal))
    events.sort(key=lambda e: (
        e.time if e.time is not None else 10**18,
        ROLE_RANK.get((e.role or "z")[0], 9),
        e.kind,
    ))
    return events


# --------------------------------------------------------------------------- #
# JSON 序列化
# --------------------------------------------------------------------------- #

def route_json(story: Storyboard, route: Route) -> dict:
    steps: list[dict] = []
    for step in route.steps:
        edge_label = None
        if step.edge_ord is not None and step.seq > 0 and len(steps) > 0:
            prev_scene = story.scenes[steps[-1]["scene"]]
            if step.edge_ord < len(prev_scene.choices):
                edge_label = prev_scene.choices[step.edge_ord].label
        window = story.windows.get(step.scene_id)
        window_state = None
        if window is not None:
            if step.arrival < window.open:
                window_state = "window-early"
            elif step.arrival > window.close:
                window_state = "window-late"
            else:
                window_state = "in-window"
        steps.append(
            {
                "seq": step.seq,
                "scene": step.scene_id,
                "label": step.label,
                "location": step.location,
                "arrival": step.arrival,
                "duration": step.duration,
                "departure": step.departure,
                "edge_ord": step.edge_ord,
                "edge_label": edge_label,
                "duration_ord": step.duration_ord,
                "window": (
                    None if window is None
                    else {"open": window.open, "close": window.close,
                          "state": window_state}
                ),
            }
        )
    return {
        "role": route.role,
        "route_id": route.route_id,
        "ended": route.ended,
        "edges": route.edges_walked,
        "fault": (
            None
            if route.fault is None
            else {
                "code": route.fault.kind,
                "detail": route.fault.detail,
                "arrival": route.fault.arrival,
                "edge_ord": route.fault.edge_ord,
            }
        ),
        "steps": steps,
    }


def _event_dict(event: EventView) -> dict:
    return {
        "kind": event.kind,
        "time": event.time,
        "role": event.role,
        "scene": event.scene,
        "location": event.location,
        "label": event.label,
        "ref": event.ref,
    }


def contradiction_json(story: Storyboard, contradiction: Contradiction | None,
                       routes_a: list[Route], routes_b: list[Route]) -> dict | None:
    if contradiction is None:
        return None
    route_a = next(r for r in routes_a if r.route_id == contradiction.route_a)
    route_b = next(r for r in routes_b if r.route_id == contradiction.route_b)
    return {
        "code": contradiction.code,
        "detail": contradiction.detail,
        "story_time": contradiction.story_time,
        "diff_minutes": contradiction.diff_minutes,
        "role": contradiction.role,
        "edge_ord": contradiction.edge_ord,
        "edges_a": contradiction.edges_a,
        "edges_b": contradiction.edges_b,
        "outcome_index": contradiction.outcome_index,
        "events": [_event_dict(e) for e in contradiction.events],
        "retell": {
            "a": route_json(story, route_a),
            "b": route_json(story, route_b),
        },
    }
