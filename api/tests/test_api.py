# -*- coding: utf-8 -*-
"""API 测试：修订不可变、冻结校样不漂移、跨修订拒绝、结构错误 422。"""

import copy
import os
import tempfile

import pytest

from app.server import create_app


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "test.sqlite3")
    app = create_app(db, seed=False)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


VALID_SPEC = {
    "title": "api-test",
    "start": "s",
    "scenes": [
        {"id": "s", "label": "起", "location": "L", "durations": [1],
         "choices": [{"to": "m"}]},
        {"id": "m", "label": "会面", "location": "L", "durations": [1],
         "choices": []},
    ],
    "windows": [{"scene": "m", "open": 0, "close": 9}],
    "transitions": [],
    "meetings": [{"kind": "meeting", "scene_a": "m", "scene_b": "m",
                  "label": "见"}],
    "messages": [],
}


def _post(client, url, payload):
    return client.post(url, json=payload)


def test_health_and_samples(client):
    assert client.get("/api/health").get_json() == {"ok": True}
    samples = client.get("/api/samples").get_json()
    assert "sample_valid" in samples


def test_create_and_get_frozen_revision(client):
    resp = _post(client, "/api/revisions", {"spec": VALID_SPEC, "note": "r1"})
    assert resp.status_code == 201
    rev = resp.get_json()
    rid = rev["revision_id"]
    assert rev["proof"]["status"] == "valid"
    assert rev["changes_from_parent"] is None

    # 再读一次：冻结校样逐字节一致。
    again = client.get(f"/api/revisions/{rid}").get_json()
    assert again["proof"] == rev["proof"]
    assert again["spec"] == rev["spec"]


def test_old_frozen_proof_does_not_drift(client):
    r1 = _post(client, "/api/revisions", {"spec": VALID_SPEC}).get_json()
    changed = copy.deepcopy(VALID_SPEC)
    changed["windows"][0]["close"] = 0  # 会面点 arrival=1，必定迟到
    r2 = _post(client, "/api/revisions",
               {"spec": changed, "parent_id": r1["revision_id"], "note": "收紧窗口"}
               ).get_json()
    assert r2["proof"]["status"] == "contradiction"

    # r1 的冻结校样没有漂移，且影响域说明记录了窗口编辑。
    frozen = client.get(f"/api/revisions/{r1['revision_id']}").get_json()
    assert frozen["proof"]["status"] == "valid"
    changes = r2["changes_from_parent"]
    assert changes["dirty_scenes"] == ["m", "s"]


def test_structure_error_returns_422_and_creates_nothing(client):
    bad = copy.deepcopy(VALID_SPEC)
    bad["scenes"][0]["choices"][0]["to"] = "ghost"
    resp = _post(client, "/api/revisions", {"spec": bad})
    assert resp.status_code == 422
    assert resp.get_json()["error"] == "structure"
    listing = client.get("/api/revisions").get_json()["revisions"]
    assert listing == []


def test_cross_revision_route_id_rejected(client):
    r1 = _post(client, "/api/revisions", {"spec": VALID_SPEC}).get_json()
    changed = copy.deepcopy(VALID_SPEC)
    changed["scenes"][1]["durations"] = [2]
    r2 = _post(client, "/api/revisions",
               {"spec": changed, "parent_id": r1["revision_id"]}).get_json()

    # 两个修订的 route_id 恰好同形，但拿 r1 的 id 去 r2 查结局必须仍能解析
    # （同形路线）——关键是否定异步错贴：删除场景后旧 route 必须查不到。
    old_route = r1["proof"]["routes"]["a"][0]["route_id"]
    detail = client.post(
        f"/api/revisions/{r2['revision_id']}/outcomes/lookup",
        json={"ra": old_route, "rb": old_route},
    )
    assert detail.status_code == 200  # 同形路线在两修订中分别独立重算

    # 真正的跨修订错贴：插入中间场景后图结构变化，旧路线标识在新修订中不存在。
    restructured = copy.deepcopy(VALID_SPEC)
    restructured["scenes"].append(
        {"id": "z", "label": "新插入的中转", "location": "L", "durations": [1],
         "choices": [{"to": "m"}]}
    )
    restructured["scenes"][0]["choices"] = [{"to": "z"}]
    r3_resp = _post(client, "/api/revisions",
                    {"spec": restructured, "parent_id": r2["revision_id"]})
    assert r3_resp.status_code == 201
    r3 = r3_resp.get_json()
    stale = client.post(
        f"/api/revisions/{r3['revision_id']}/outcomes/lookup",
        json={"ra": old_route, "rb": old_route},
    )
    assert stale.status_code == 422
    assert "路线不存在" in stale.get_json()["message"]


def test_prove_preview_does_not_persist(client):
    resp = _post(client, "/api/prove", {"spec": VALID_SPEC})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "valid"
    assert client.get("/api/revisions").get_json()["revisions"] == []


def test_missing_parent_is_404(client):
    resp = _post(client, "/api/revisions",
                 {"spec": VALID_SPEC, "parent_id": 999})
    assert resp.status_code == 404


def test_outcome_detail_by_index_and_events(client):
    r1 = _post(client, "/api/revisions", {"spec": VALID_SPEC}).get_json()
    detail = client.get(
        f"/api/revisions/{r1['revision_id']}/outcomes/0"
    ).get_json()
    assert detail["i"] == 0
    kinds = {e["kind"] for e in detail["events"]}
    assert {"arrival", "departure", "meeting"} <= kinds
    assert detail["first"] is None


def test_blast_preview_over_http(client):
    r1 = _post(client, "/api/revisions", {"spec": VALID_SPEC}).get_json()
    changed = copy.deepcopy(VALID_SPEC)
    changed["scenes"][1]["durations"] = [2]
    resp = client.post(
        f"/api/revisions/{r1['revision_id']}/blast-preview",
        json={"spec": changed},
    )
    assert resp.status_code == 200
    scope = resp.get_json()
    # 会面终点时长不影响到达，但仍是编辑落点：两条路线都经过 m，全 4 结局重算。
    assert scope["recompute_indices"] == [0]
    assert "m" in scope["dirty_scenes"]

    # 结构非法的预演同样 422，且不落库。
    bad = copy.deepcopy(VALID_SPEC)
    bad["scenes"][0]["choices"][0]["to"] = "ghost"
    rejected = client.post(
        f"/api/revisions/{r1['revision_id']}/blast-preview",
        json={"spec": bad},
    )
    assert rejected.status_code == 422
    assert len(client.get("/api/revisions").get_json()["revisions"]) == 1
