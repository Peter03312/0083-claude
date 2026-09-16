# -*- coding: utf-8 -*-
"""修订影响域测试（图依赖传播）。"""

import copy

from app.engine import parse_storyboard
from app.engine.revisions import affected_outcomes, diff_affected
from app.sample_storyboards import SAMPLES


def _sample():
    return copy.deepcopy(SAMPLES["sample_valid"])


def _outcome_index(spec):
    story = parse_storyboard(spec)
    from app.engine.routes import enumerate_routes
    ra = enumerate_routes(story, "a")
    rb = enumerate_routes(story, "b")
    return ra, rb


def test_duration_edit_propagates_downstream():
    old = _sample()
    new = copy.deepcopy(old)
    # 改画廊时长：影响 gallery 自身与其下游 belltower；不碰连廊支线。
    for scene in new["scenes"]:
        if scene["id"] == "gallery":
            scene["durations"] = [3]
    affected = diff_affected(old, new)
    assert affected.changed_scene_durations == ("gallery",)
    assert "gallery" in affected.dirty_scenes
    assert "belltower" in affected.dirty_scenes
    assert "corridor_w" not in affected.dirty_scenes
    assert "corridor_e" not in affected.dirty_scenes

    scope = affected_outcomes(parse_storyboard(old), affected)
    # 只有“至少一人走画廊”的结局需要重算。
    ra, rb = _outcome_index(old)
    assert len(ra) == 2 and len(rb) == 2  # gallery / corridor 各一条
    # 路线级精确判定：重算索引 0(A画廊×B画廊)、1(A画廊×B连廊)、
    # 2(A连廊×B画廊)；3(双连廊)不受影响。
    assert scope["recompute_indices"] == [0, 1, 2]


def test_window_edit_marks_upstream_not_downstream():
    old = _sample()
    new = copy.deepcopy(old)
    for w in new["windows"]:
        if w["scene"] == "belltower":
            w["close"] = 30
    affected = diff_affected(old, new)
    assert affected.changed_windows == ("belltower",)
    # belltower 是终点，其上游是全部场景（两条支线都能走到它）。
    assert affected.dirty_scenes == frozenset(
        ["gate", "gallery", "corridor_w", "corridor_e", "belltower"]
    )

    # 只改连廊东端窗口：上游是 gate/corridor_w/corridor_e，画廊支线不受影响。
    new2 = copy.deepcopy(old)
    for w in new2["windows"]:
        if w["scene"] == "corridor_e":
            w["close"] = 30
    affected2 = diff_affected(old, new2)
    assert "gallery" not in affected2.dirty_scenes
    assert {"gate", "corridor_w", "corridor_e"} <= affected2.dirty_scenes


def test_transition_edit_marks_only_crossing_edges():
    old = _sample()
    new = copy.deepcopy(old)
    # 提高 教学楼↔钟楼 的转场下限：只有连廊支线的最后一跳跨越它。
    for t in new["transitions"]:
        if {t["from"], t["to"]} == {"教学楼", "钟楼"}:
            t["minutes"] = 3
    affected = diff_affected(old, new)
    changed = [(a, b) for a, b, _ in affected.changed_transitions]
    assert ("教学楼", "钟楼") in changed
    assert "gallery" not in affected.dirty_scenes
    assert "corridor_e" in affected.dirty_scenes
    assert "belltower" in affected.dirty_scenes


def test_transition_removal_is_just_a_bound_change():
    old = _sample()
    new = copy.deepcopy(old)
    new["transitions"] = [
        t for t in new["transitions"]
        if {t["from"], t["to"]} != {"教学楼", "钟楼"}
    ]
    affected = diff_affected(old, new)
    assert any((a, b, m) == ("教学楼", "钟楼", None)
               for a, b, m in affected.changed_transitions)
    # 不视为结构编辑（场景与边未变），影响域仍精确到跨越边。
    assert affected.structural is False
    scope = affected_outcomes(parse_storyboard(old), affected)
    # 只有走连廊的路线跨越教学楼↔钟楼：索引 1/2/3（A画廊0·连廊1 排列）。
    assert scope["recompute_indices"] == [1, 2, 3]


def test_constraint_edit_recomputes_all_outcomes():
    old = _sample()
    new = copy.deepcopy(old)
    new["meetings"][0]["label"] = "改了名字的会面"
    affected = diff_affected(old, new)
    assert affected.constraints_changed is True
    scope = affected_outcomes(parse_storyboard(old), affected)
    assert scope["recompute_indices"] == list(range(scope["total"]))


def test_no_edit_empty_blast_radius():
    old = _sample()
    affected = diff_affected(old, copy.deepcopy(old))
    scope = affected_outcomes(parse_storyboard(old), affected)
    assert scope["recompute_indices"] == []
    assert scope["recompute_count"] == 0
