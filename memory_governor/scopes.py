from __future__ import annotations

from memory_governor.schemas import Scope

VALID_KINDS = {"user", "room", "global", "project", "topic"}


def scope_path(scope: Scope) -> str:
    """Serialize a scope (and its parent chain) as a newest-first path.

    Example: project:sacred-brain/user:sam/global:root
    """
    parts: list[str] = []
    cur: Scope | None = scope
    while cur is not None:
        parts.append(f"{cur.kind}:{cur.id}")
        cur = cur.parent
    return "/".join(parts)


def parse_scope_path(path: str) -> Scope:
    """Parse a scope path back into a nested Scope. Inverse of `scope_path`.

    Splits on `/` (not permitted in ids), then splits each segment on the
    first `:` to separate kind from id (room ids may contain `:`).
    """
    if not path:
        raise ValueError("empty scope path")
    segments = path.split("/")
    parsed: list[tuple[str, str]] = []
    for seg in segments:
        if ":" not in seg:
            raise ValueError(f"invalid scope segment (missing ':'): {seg!r}")
        kind, sid = seg.split(":", 1)
        if kind not in VALID_KINDS:
            raise ValueError(f"unknown scope kind: {kind!r}")
        parsed.append((kind, sid))
    scope: Scope | None = None
    for kind, sid in reversed(parsed):
        scope = Scope(kind=kind, id=sid, parent=scope)
    assert scope is not None
    return scope


def ancestor_paths(path: str) -> list[str]:
    """Return [path, parent, grandparent, ...] by trimming from the left.

    Each entry is a valid scope path. `project:foo/user:sam/global:root`
    yields `[project:foo/user:sam/global:root, user:sam/global:root, global:root]`.
    """
    parts = path.split("/")
    return ["/".join(parts[i:]) for i in range(len(parts))]


def matches_filter(stored_path: str, filter_path: str) -> bool:
    """Memory at `stored_path` matches filter `filter_path` if stored is
    the filter itself or an ancestor (suffix match on `/` boundaries).
    Descendants do NOT match.
    """
    if stored_path == filter_path:
        return True
    return filter_path.endswith("/" + stored_path)
