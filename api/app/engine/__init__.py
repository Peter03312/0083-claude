# -*- coding: utf-8 -*-
"""双角色声音漫游校样引擎。

只核验作者给出的结构，不续写台词、不推荐剧情。
所有时刻都是整数分钟上的*离散*可达时刻，路线在合流处也保持独立状态。
"""

from .model import (
    Edge,
    Meeting,
    Message,
    Scene,
    Storyboard,
    Transition,
    Window,
    canonical_json,
    content_hash,
    parse_storyboard,
)
from .proof import prove_revision
from .revisions import AffectedGraph, diff_affected, revision_graph

__all__ = [
    "Edge",
    "Meeting",
    "Message",
    "Scene",
    "Storyboard",
    "Transition",
    "Window",
    "canonical_json",
    "content_hash",
    "parse_storyboard",
    "prove_revision",
    "AffectedGraph",
    "diff_affected",
    "revision_graph",
]
