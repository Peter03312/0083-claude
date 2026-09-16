# -*- coding: utf-8 -*-
"""修订与影响域（图依赖传播）。

一次编辑必须建立新修订；依据场景图依赖标出**必须重算**的场景与结局，
旧修订的冻结校样永不漂移：

* 改某场景的时长 → 该场景及其所有下游（离开时刻变化会一路传播）；
* 改某场景的时间窗口 → 该场景的所有上游及它自身（窗口只裁决到达时刻，
  受影响的是所有能走到它的路线）；
* 改地点间最短转场下限 → 所有跨越该地点对的选择边的源场景，及其下游
  （转场改变到达，再向下传播；新缺的转场还会让源序列中断）。

结构增删（场景/边）按拓扑闭包保守处理。会面与消息不参与时刻传播，
直接标记全部结局重算。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import Scene, Storyboard, content_hash, parse_storyboard
from .routes import enumerate_routes


@dataclass(frozen=True)
class AffectedGraph:
    """影响域（基于旧修订的图）。"""

    changed_scene_durations: tuple[str, ...]
    changed_windows: tuple[str, ...]
    changed_transitions: tuple[tuple[str, str, int | None], ...]
    structural: bool
    constraints_changed: bool  # 会面/消息增删改
    dirty_scenes: frozenset[str]
    seed_scenes: frozenset[str]  # 编辑直接落点（供解释“为什么重算”）
    reasons: dict[str, tuple[str, ...]] = field(default_factory=dict)


def revision_graph(story: Storyboard) -> dict[str, list[str]]:
    """场景 id → 选择边直达的下游场景。"""
    return {sid: [edge.to for edge in scene.choices]
            for sid, scene in story.scenes.items()}


def _downstream(graph: dict[str, list[str]], seeds) -> frozenset[str]:
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        stack.extend(graph.get(sid, ()))
    return frozenset(seen)


def _upstream(graph: dict[str, list[str]], seeds) -> frozenset[str]:
    reverse: dict[str, list[str]] = {}
    for sid, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, []).append(sid)
    seen: set[str] = set()
    stack = list(seeds)
    while stack:
        sid = stack.pop()
        if sid in seen:
            continue
        seen.add(sid)
        stack.extend(reverse.get(sid, ()))
    return frozenset(seen)


def diff_affected(old_raw: dict, new_raw: dict) -> AffectedGraph:
    """比较新旧故事板，基于旧图计算影响域。新结构无法解析时抛 ValueError。"""
    old_story = parse_storyboard(old_raw)
    new_story = parse_storyboard(new_raw)  # 新结构先过结构校验
    graph = revision_graph(old_story)

    duration_changes: list[str] = []
    window_changes: list[str] = []
    structural = False
    reasons: dict[str, list[str]] = {}

    def touch(sid: str, reason: str) -> None:
        reasons.setdefault(sid, []).append(reason)

    # 场景增删。
    old_ids = set(old_story.scenes)
    new_ids = set(new_story.scenes)
    if old_ids != new_ids or old_story.start != new_story.start:
        structural = True

    for sid in sorted(old_ids & new_ids):
        old_scene = old_story.scenes[sid]
        new_scene = new_story.scenes[sid]
        if list(old_scene.durations) != list(new_scene.durations):
            duration_changes.append(sid)
            touch(sid, "时长编辑：离开时刻变化，向下游传播")
        if old_scene.location != new_scene.location:
            structural = True
            touch(sid, "地点变更：转场依赖整体改变")
        if [(e.to, e.label) for e in old_scene.choices] != [
            (e.to, e.label) for e in new_scene.choices
        ]:
            structural = True
            touch(sid, "选择边增删或改接")
        old_w = old_story.windows.get(sid)
        new_w = new_story.windows.get(sid)
        if (old_w is None) != (new_w is None) or (
            old_w is not None and (old_w.open, old_w.close) != (new_w.open, new_w.close)
        ):
            window_changes.append(sid)
            touch(sid, "窗口编辑：所有能到达此处的路线需重新裁决")

    # 转场下限变化（用规范化的地点对匹配）。
    transition_changes: list[tuple[str, str, int | None]] = []
    pairs = sorted(set(old_story.transitions) | set(new_story.transitions))
    for pair in pairs:
        old_minutes = old_story.transitions.get(pair)
        new_minutes = new_story.transitions.get(pair)
        if old_minutes != new_minutes:
            transition_changes.append((pair[0], pair[1], new_minutes))

    # 会面/消息变化不参与时刻传播，但需要全部结局重新裁决约束。
    constraints_changed = (
        [tuple(m.__dict__.values()) for m in old_story.meetings]
        != [tuple(m.__dict__.values()) for m in new_story.meetings]
        or [tuple(m.__dict__.values()) for m in old_story.messages]
        != [tuple(m.__dict__.values()) for m in new_story.messages]
    )

    seeds: set[str] = set()
    dirty: set[str] = set()

    # 时长：场景自身 + 下游。
    for sid in duration_changes:
        if sid in old_story.scenes:
            block = _downstream(graph, [sid])
            seeds.add(sid)
            dirty.update(block)

    # 窗口：上游 + 自身。
    for sid in window_changes:
        if sid in old_story.scenes:
            block = _upstream(graph, [sid]) | {sid}
            seeds.add(sid)
            dirty.update(block)

    # 转场：找到旧图中跨越该地点对的选择边，源场景 + 其下游。
    for loc_a, loc_b, _new in transition_changes:
        edge_sources: set[str] = set()
        for sid, scene in old_story.scenes.items():
            for edge in scene.choices:
                target = old_story.scenes.get(edge.to)
                if target is None:
                    continue
                if {scene.location, target.location} == {loc_a, loc_b}:
                    edge_sources.add(sid)
        for sid in edge_sources:
            touch(sid, f"转场下限编辑（{loc_a} ↔ {loc_b}）：到达变化向下游传播")
            seeds.add(sid)
            dirty.update(_downstream(graph, [sid]))
        if not edge_sources:
            # 没有边跨越则不影响时刻，但仍记录为已编辑。
            pass

    if structural:
        # 保守处理：从旧起点闭包；新起点若不存在于旧图，稍后整表重算。
        if old_story.start in old_story.scenes:
            dirty.update(_downstream(graph, [old_story.start]))
        else:
            dirty.update(old_ids)
        seeds.update(sid for sid, _ in reasons.items()
                     if "地点变更" in " ".join(reasons[sid])
                     or "选择边" in " ".join(reasons[sid]))

    return AffectedGraph(
        changed_scene_durations=tuple(duration_changes),
        changed_windows=tuple(window_changes),
        changed_transitions=tuple(transition_changes),
        structural=structural,
        constraints_changed=constraints_changed,
        dirty_scenes=frozenset(dirty),
        seed_scenes=frozenset(seeds),
        reasons={sid: tuple(msgs) for sid, msgs in reasons.items()},
    )


def affected_outcomes(old_story: Storyboard, affected: AffectedGraph) -> dict:
    """在旧修订的结局索引上标出必须重算的结局序号。

    结构/约束变化 → 全部结局。时刻类编辑在**路线级**精确判定：
    合流场景即使落在下游闭包里，没有经过编辑点/跨越编辑边的路线也不重算。
    """
    routes_a = enumerate_routes(old_story, "a")
    routes_b = enumerate_routes(old_story, "b")
    total = len(routes_a) * len(routes_b)
    recompute_all = affected.structural or affected.constraints_changed

    transition_pairs = {
        tuple(sorted((loc_a, loc_b)))
        for loc_a, loc_b, _ in affected.changed_transitions
    }

    def route_is_dirty(route) -> bool:
        scenes = [s.scene_id for s in route.steps]
        scene_set = set(scenes)
        if scene_set & set(affected.changed_scene_durations):
            return True
        if scene_set & set(affected.changed_windows):
            return True
        if transition_pairs:
            for prev, nxt in zip(route.steps, route.steps[1:]):
                if prev.location != nxt.location and \
                        tuple(sorted((prev.location, nxt.location))) in transition_pairs:
                    return True
        return False

    recompute: list[int] = []
    if recompute_all:
        recompute = list(range(total))
    else:
        dirty_a = {r.route_id for r in routes_a if route_is_dirty(r)}
        dirty_b = {r.route_id for r in routes_b if route_is_dirty(r)}
        for ia, route_a in enumerate(routes_a):
            hit_a = route_a.route_id in dirty_a
            for ib, route_b in enumerate(routes_b):
                if hit_a or route_b.route_id in dirty_b:
                    recompute.append(ia * len(routes_b) + ib)

    return {
        "total": total,
        "recompute_count": len(recompute),
        "recompute_indices": recompute,
        "dirty_scenes": sorted(affected.dirty_scenes),
        "seed_scenes": sorted(affected.seed_scenes),
        "reasons": affected.reasons,
        "structural": affected.structural,
        "constraints_changed": affected.constraints_changed,
    }
