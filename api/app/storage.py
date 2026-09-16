# -*- coding: utf-8 -*-
"""SQLite 只追加修订存储。

每行修订一经写入永不修改、永不删除：旧冻结校样不会因新编辑漂移。
校样 JSON 用 gzip 压缩保存；结构问题由引擎的 StoryboardError 表达。
"""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
from datetime import datetime, timezone

from .engine import canonical_json, content_hash, parse_storyboard
from .engine.model import StoryboardError
from .engine.proof import pair_detail, prove_revision
from .engine.revisions import affected_outcomes, diff_affected
from .sample_storyboards import SAMPLES


SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    spec_hash   TEXT NOT NULL,
    spec        BLOB NOT NULL,
    proof       BLOB NOT NULL,
    edit_note   TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS lineage (
    revision_id   INTEGER PRIMARY KEY REFERENCES revisions(id),
    parent_id     INTEGER REFERENCES revisions(id),
    changes_json  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str) -> None:
        self.path = path
        db_dir = os.path.dirname(os.path.abspath(path))
        os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------------ #

    def _get_revision_row(self, revision_id: int) -> sqlite3.Row:
        row = self.conn.execute(
            "SELECT * FROM revisions WHERE id = ?", (revision_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"修订不存在：{revision_id}")
        return row

    def get_revision(self, revision_id: int) -> dict:
        row = self._get_revision_row(revision_id)
        return self._row_json(row)

    def latest_revision(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM revisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return self._row_json(row) if row else None

    def list_revisions(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, created_at, title, spec_hash, edit_note FROM revisions ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def _row_json(self, row: sqlite3.Row) -> dict:
        spec = json.loads(gzip.decompress(row["spec"]).decode("utf-8"))
        proof = json.loads(gzip.decompress(row["proof"]).decode("utf-8"))
        lineage = self.conn.execute(
            "SELECT parent_id, changes_json FROM lineage WHERE revision_id = ?",
            (row["id"],),
        ).fetchone()
        changes = json.loads(lineage["changes_json"]) if lineage else None
        return {
            "revision_id": row["id"],
            "created_at": row["created_at"],
            "title": row["title"],
            "spec_hash": row["spec_hash"],
            "spec": spec,
            "proof": proof,
            "edit_note": row["edit_note"],
            "changes_from_parent": changes,
        }

    # ------------------------------------------------------------------ #

    def create_revision(self, raw_spec: dict, parent_id: int | None,
                        edit_note: str = "") -> dict:
        """运行校样后写入新修订（同一结构复用哈希提示，但行依旧独立追加）。"""
        story = parse_storyboard(raw_spec)  # 结构错误抛 StoryboardError
        proof = prove_revision(raw_spec)

        changes = None
        if parent_id is not None:
            parent_row = self._get_revision_row(parent_id)
            parent_spec = json.loads(gzip.decompress(parent_row["spec"]).decode("utf-8"))
            changes = self._compute_changes(parent_spec, raw_spec)

        spec_bytes = gzip.compress(canonical_json(raw_spec).encode("utf-8"))
        proof_bytes = gzip.compress(
            json.dumps(proof, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        cur = self.conn.execute(
            "INSERT INTO revisions (created_at, title, spec_hash, spec, proof, edit_note)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), story.title, content_hash(raw_spec), spec_bytes,
             proof_bytes, edit_note),
        )
        revision_id = cur.lastrowid
        self.conn.execute(
            "INSERT INTO lineage (revision_id, parent_id, changes_json)"
            " VALUES (?, ?, ?)",
            (revision_id, parent_id,
             json.dumps(changes, ensure_ascii=False, separators=(",", ":"))),
        )
        self.conn.commit()
        return self.get_revision(revision_id)

    def _compute_changes(self, old_raw: dict, new_raw: dict) -> dict:
        """图依赖影响域；新结构若不成立，结构错误向上抛。"""
        try:
            affected = diff_affected(old_raw, new_raw)
            old_story = parse_storyboard(old_raw)
            scope = affected_outcomes(old_story, affected)
        except StoryboardError:
            raise
        return scope

    def outcome_detail(self, revision_id: int, route_a: str, route_b: str) -> dict:
        """结局详情按当前冻结校样的结构重算，结果与冻结证明一致。"""
        rev = self.get_revision(revision_id)
        return pair_detail(rev["spec"], route_a, route_b)

    # ------------------------------------------------------------------ #

    def seed_samples(self) -> list[int]:
        """首次启动时把内置故事板播种成一条修订链，返回修订号。"""
        existing = self.conn.execute("SELECT COUNT(*) AS n FROM revisions").fetchone()["n"]
        if existing:
            return []
        ids: list[int] = []
        parent: int | None = None
        for key in ("sample_valid", "sample_bad", "sample_unreachable",
                    "sample_crossbranch"):
            rev = self.create_revision(
                SAMPLES[key], parent, f"内置示例：{key}"
            )
            ids.append(rev["revision_id"])
            parent = rev["revision_id"]
        return ids
