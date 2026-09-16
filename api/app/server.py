# -*- coding: utf-8 -*-
"""Flask API：不可变修订、冻结校样、结局详情、影响域。

并发安全约定（防“异步旧响应贴到新修订”）：
* 每个响应都带 ``revision_id``；提交编辑时必须通过 ``parent_id``
  声明基于哪一修订，服务端按该父修订计算影响域后再追加新行；
* 结局详情必须带 ``revision_id``，跨修订的路线标识一律拒绝。
"""

from __future__ import annotations

import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from .engine.model import StoryboardError
from .sample_storyboards import SAMPLES
from .storage import Store


def _default_db_path() -> str:
    env = os.environ.get("PROOF_DB")
    if env:
        return env
    if os.path.isdir("/data"):
        return "/data/proofs.sqlite3"
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data",
        "proofs.sqlite3",
    )


def create_app(db_path: str | None = None, seed: bool = True) -> Flask:
    app = Flask(__name__)
    CORS(app)
    store = Store(db_path or _default_db_path())
    app.config["STORE"] = store
    if seed and os.environ.get("SEED_SAMPLES", "1") == "1":
        store.seed_samples()

    @app.errorhandler(StoryboardError)
    def _structure_error(err: StoryboardError):
        return jsonify({"error": "structure", "message": str(err)}), 422

    @app.errorhandler(KeyError)
    def _not_found(err: KeyError):
        return jsonify({"error": "not-found", "message": str(err).strip("'")}), 404

    # ---------------------------------------------------------------- #

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True})

    @app.get("/api/samples")
    def samples():
        return jsonify({
            key: {"title": spec.get("title", ""), "spec": spec}
            for key, spec in SAMPLES.items()
        })

    @app.get("/api/revisions")
    def list_revisions():
        return jsonify({"revisions": store.list_revisions()})

    @app.get("/api/revisions/latest")
    def latest_revision():
        rev = store.latest_revision()
        if rev is None:
            return jsonify({"error": "not-found", "message": "尚无修订"}), 404
        return jsonify(rev)

    @app.get("/api/revisions/<int:revision_id>")
    def get_revision(revision_id: int):
        return jsonify(store.get_revision(revision_id))

    @app.post("/api/revisions")
    def create_revision():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "spec" not in payload:
            return jsonify({"error": "request",
                            "message": "请求体需要 { spec, parent_id?, note? }"}), 400
        parent_id = payload.get("parent_id")
        if parent_id is not None and not isinstance(parent_id, int):
            return jsonify({"error": "request",
                            "message": "parent_id 必须是整数修订号或 null"}), 400
        if parent_id is not None:
            store.get_revision(parent_id)  # 父修订不存在 → 404
        note = payload.get("note", "")
        if not isinstance(note, str):
            return jsonify({"error": "request", "message": "note 必须是字符串"}), 400
        rev = store.create_revision(payload["spec"], parent_id, note)
        return jsonify(rev), 201

    @app.get("/api/revisions/<int:revision_id>/outcomes/<int:outcome_index>")
    def outcome_by_index(revision_id: int, outcome_index: int):
        rev = store.get_revision(revision_id)
        compact = next(
            (o for o in rev["proof"]["outcomes"] if o["i"] == outcome_index), None
        )
        if compact is None:
            return jsonify({"error": "not-found",
                            "message": f"结局 {outcome_index} 不存在"}), 404
        detail = store.outcome_detail(revision_id, compact["ra"], compact["rb"])
        return jsonify(detail)

    @app.post("/api/revisions/<int:revision_id>/outcomes/lookup")
    def outcome_lookup(revision_id: int):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "ra" not in payload or "rb" not in payload:
            return jsonify({"error": "request",
                            "message": "请求体需要 { ra, rb }"}), 400
        detail = store.outcome_detail(revision_id, payload["ra"], payload["rb"])
        return jsonify(detail)

    @app.post("/api/prove")
    def prove_without_save():
        """临时校样（不落库），供编辑过程中即时检查。"""
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "spec" not in payload:
            return jsonify({"error": "request", "message": "请求体需要 { spec }"}), 400
        from .engine import parse_storyboard
        from .engine.proof import prove_revision
        spec = payload["spec"]
        parse_storyboard(spec)  # 结构错误 → 422
        return jsonify(prove_revision(spec))

    @app.post("/api/revisions/<int:revision_id>/blast-preview")
    def blast_preview(revision_id: int):
        """基于某已冻结修订预演一次编辑的图依赖影响域（不落库）。"""
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or "spec" not in payload:
            return jsonify({"error": "request",
                            "message": "请求体需要 { spec }"}), 400
        parent = store.get_revision(revision_id)
        from .engine import parse_storyboard
        from .engine.revisions import affected_outcomes, diff_affected
        old_story = parse_storyboard(parent["spec"])
        affected = diff_affected(parent["spec"], payload["spec"])  # 结构错误 → 422
        return jsonify(affected_outcomes(old_story, affected))

    return app


app = create_app()
