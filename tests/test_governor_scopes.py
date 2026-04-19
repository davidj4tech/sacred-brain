from __future__ import annotations

from pathlib import Path

import pytest

from memory_governor.config import _parse_consolidate_scopes
from memory_governor.schemas import ObserveRequest, Scope
from memory_governor.scopes import (
    ancestor_paths,
    matches_filter,
    parse_scope_path,
    scope_path,
)
from memory_governor.store import WorkingStore


def test_scope_path_roundtrip_single() -> None:
    s = Scope(kind="user", id="sam")
    assert scope_path(s) == "user:sam"
    assert scope_path(parse_scope_path("user:sam")) == "user:sam"


def test_scope_path_roundtrip_deep() -> None:
    s = Scope(
        kind="project",
        id="sacred-brain",
        parent=Scope(kind="user", id="sam", parent=Scope(kind="global", id="root")),
    )
    path = scope_path(s)
    assert path == "project:sacred-brain/user:sam/global:root"
    s2 = parse_scope_path(path)
    assert scope_path(s2) == path
    assert s2.kind == "project"
    assert s2.parent.kind == "user"
    assert s2.parent.parent.kind == "global"


def test_scope_path_room_id_with_colon() -> None:
    s = Scope(kind="room", id="!abc:server.name")
    path = scope_path(s)
    assert scope_path(parse_scope_path(path)) == path


def test_parse_scope_path_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        parse_scope_path("bogus:x")


def test_ancestor_paths() -> None:
    paths = ancestor_paths("project:foo/user:sam/global:root")
    assert paths == [
        "project:foo/user:sam/global:root",
        "user:sam/global:root",
        "global:root",
    ]


def test_matches_filter_ancestor() -> None:
    # memory at global:root matches filter project:foo/user:sam/global:root
    assert matches_filter("global:root", "project:foo/user:sam/global:root")
    # exact match
    assert matches_filter("project:foo", "project:foo")
    # descendants do NOT match ancestors
    assert not matches_filter("project:foo/user:sam/global:root", "global:root")
    # unrelated paths
    assert not matches_filter("user:mel", "user:sam")


@pytest.fixture
def store(tmp_path: Path) -> WorkingStore:
    return WorkingStore(tmp_path / "state.db", ttl_hours=24)


def test_scope_backcompat_flat_scope(store: WorkingStore) -> None:
    # flat scope (no parent) continues to work
    req = ObserveRequest(
        source="test", user_id="sam", text="hello world",
        scope=Scope(kind="user", id="sam"), metadata={"event_id": "e1"},
    )
    assert store.add_working(req) is True
    rows = store.recent_for_scope(Scope(kind="user", id="sam"))
    assert len(rows) == 1


def test_recent_for_scope_ancestor(store: WorkingStore) -> None:
    narrow = Scope(
        kind="project", id="sacred-brain",
        parent=Scope(kind="user", id="sam"),
    )
    broad = Scope(kind="user", id="sam")
    store.add_working(ObserveRequest(
        source="t", user_id="sam", text="narrow note", scope=narrow,
        metadata={"event_id": "n1"},
    ))
    store.add_working(ObserveRequest(
        source="t", user_id="sam", text="broad note", scope=broad,
        metadata={"event_id": "b1"},
    ))
    # From narrow scope with ancestors, we see both
    rows_all = store.recent_for_scope(narrow, include_ancestors=True)
    texts = {r["text"] for r in rows_all}
    assert texts == {"narrow note", "broad note"}
    # From narrow scope without ancestors, only narrow
    rows_exact = store.recent_for_scope(narrow, include_ancestors=False)
    assert {r["text"] for r in rows_exact} == {"narrow note"}
    # From broad scope, we only see broad (descendants don't leak up)
    rows_broad = store.recent_for_scope(broad, include_ancestors=True)
    assert {r["text"] for r in rows_broad} == {"broad note"}


def test_distinct_scopes(store: WorkingStore) -> None:
    for i, scope in enumerate([
        Scope(kind="user", id="sam"),
        Scope(kind="user", id="mel"),
        Scope(kind="project", id="sb", parent=Scope(kind="user", id="sam")),
    ]):
        store.add_working(ObserveRequest(
            source="t", user_id="u", text=f"note {i}", scope=scope,
            metadata={"event_id": f"e{i}"},
        ))
    scopes = store.distinct_scopes()
    paths = {s["path"] for s in scopes}
    assert paths == {"user:sam", "user:mel", "project:sb/user:sam"}
    for s in scopes:
        assert s["count"] == 1


def test_parse_consolidate_scopes_flat() -> None:
    assert _parse_consolidate_scopes("user:sam,room:!a:srv") == ["user:sam", "room:!a:srv"]


def test_parse_consolidate_scopes_chained() -> None:
    assert _parse_consolidate_scopes("project:sb@user:sam,user:mel") == [
        "project:sb/user:sam",
        "user:mel",
    ]


def test_parse_consolidate_scopes_rejects_bad() -> None:
    with pytest.raises(ValueError):
        _parse_consolidate_scopes("bogus:x")
