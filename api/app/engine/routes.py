# -*- coding: utf-8 -*-
"""每个角色的离散路线枚举。

一条“路线”是一条完整的选择序列，每个场景还独立选定一个时长：

* 到达/离开都是整数分钟上的**离散可达时刻**，绝不用连续区间表示；
* 同一场景即使被多条边合流抵达，各序列的 :class:`Route` 仍然各自独立，
  合流处绝不混成一份状态（不同来路同刻合流必须能被后续会面区分）；
* 地点之间缺少作者给出的最短转场时，该序列在此中断并挂一个
  ``location-unreachable`` 断层，不再继续；窗口矛盾不中断枚举，
  因为后续会面/消息仍需要这些离散时刻参与配对裁决。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import ROLES, Storyboard, Window


@dataclass(frozen=True)
class Step:
    scene_id: str
    role: str
    seq: int  # 该角色路径上的场景序号（0 起）
    arrival: int
    duration: int
    departure: int
    location: str
    edge_ord: int | None  # 从上一步过来用的边序（起点为 None）
    duration_ord: int  # 本步选择的时长序号
    label: str


@dataclass(frozen=True)
class RouteFault:
    kind: str  # location-unreachable | window-early | window-late
    scene_id: str
    role: str
    arrival: int
    edge_ord: int | None
    detail: str


@dataclass(frozen=True)
class Route:
    role: str
    route_id: str  # 每步一个 e<边序>-d<时长序> 记号，斜杠分隔
    steps: tuple[Step, ...]
    fault: RouteFault | None  # 至多一个：不可达会中断序列；窗口矛盾不中断
    ended: bool  # 是否真正走到无选择边的结局

    def step_at(self, scene_id: str) -> Step | None:
        for step in self.steps:
            if step.scene_id == scene_id:
                return step
        return None

    @property
    def edges_walked(self) -> int:
        return max(0, len(self.steps) - 1)


def enumerate_routes(story: Storyboard, role: str) -> list[Route]:
    """按（时长序、边序）字典序枚举，保证结果确定。"""
    if role not in ROLES:
        raise ValueError(f"未知角色：{role}")
    routes: list[Route] = []
    _walk(story, role, story.start, arrival=0, prev_steps=[], prev_tokens=[],
          edge_ord_here=None, routes=routes)
    return routes


def _window_fault(
    story: Storyboard, scene_id: str, arrival: int, role: str, edge_ord: int | None
) -> RouteFault | None:
    window: Window | None = story.windows.get(scene_id)
    if window is None:
        return None
    if arrival < window.open:
        return RouteFault(
            kind="window-early",
            scene_id=scene_id,
            role=role,
            arrival=arrival,
            edge_ord=edge_ord,
            detail=f"第 {arrival} 分钟到达 {scene_id}，早于窗口开启第 {window.open} 分钟",
        )
    if arrival > window.close:
        return RouteFault(
            kind="window-late",
            scene_id=scene_id,
            role=role,
            arrival=arrival,
            edge_ord=edge_ord,
            detail=f"第 {arrival} 分钟到达 {scene_id}，晚于窗口关闭第 {window.close} 分钟",
        )
    return None


def _walk(
    story: Storyboard,
    role: str,
    scene_id: str,
    arrival: int,
    prev_steps: list[Step],
    prev_tokens: list[str],
    edge_ord_here: int | None,
    routes: list[Route],
) -> None:
    scene = story.scenes[scene_id]
    seq = len(prev_steps)
    window_fault = _window_fault(story, scene_id, arrival, role, edge_ord_here)

    for duration_ord, duration in enumerate(scene.durations):
        departure = arrival + duration
        step = Step(
            scene_id=scene_id,
            role=role,
            seq=seq,
            arrival=arrival,
            duration=duration,
            departure=departure,
            location=scene.location,
            edge_ord=edge_ord_here,
            duration_ord=duration_ord,
            label=scene.label,
        )
        token = f"e{edge_ord_here if edge_ord_here is not None else 0}-d{duration_ord}"
        steps = [*prev_steps, step]
        tokens = [*prev_tokens, token]

        if not scene.choices:
            routes.append(
                Route(
                    role=role,
                    route_id="/".join(tokens),
                    steps=tuple(steps),
                    fault=window_fault,
                    ended=True,
                )
            )
            continue

        for edge_ord, edge in enumerate(scene.choices):
            gap = story.transition_minutes(scene.location, story.scenes[edge.to].location)
            if gap is None:
                # 序列在此中断：停在已完全解析的当前步，断层指向下一跳。
                fault = RouteFault(
                    kind="location-unreachable",
                    scene_id=edge.to,
                    role=role,
                    arrival=departure,
                    edge_ord=edge_ord,
                    detail=(
                        f"从 {scene.id}（{scene.location}）经第 {edge_ord} 条选择去 "
                        f"{edge.to}（{story.scenes[edge.to].location}）没有给出最短转场，"
                        f"不能瞬间跨越两座楼"
                    ),
                )
                routes.append(
                    Route(
                        role=role,
                        route_id="/".join([*tokens, f"x{edge_ord}"]),
                        steps=tuple(steps),
                        fault=fault,
                        ended=False,
                    )
                )
                continue

            _walk(
                story,
                role,
                edge.to,
                arrival=departure + gap,
                prev_steps=steps,
                prev_tokens=tokens,
                edge_ord_here=edge_ord,
                routes=routes,
            )
