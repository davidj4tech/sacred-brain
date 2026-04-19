from __future__ import annotations

from memory_governor.mem_policy import classify_observation
from memory_governor.schemas import ObserveRequest, Scope


def test_classify_claude_precompact_source_capped() -> None:
    text = " ".join([
        "Please remember always prefer never todo task tomorrow next week",
        "important note remember prefer always"
    ] * 200)
    req = ObserveRequest(
        source="claude-code:precompact",
        user_id="sam",
        text=text,
        scope=Scope(kind="user", id="sam"),
    )
    salience, kind = classify_observation(req)
    assert salience <= 0.35
    # Still lands in working memory, not candidates
    assert kind in ("working", "ignore")


def test_classify_opencode_precompact_source_capped() -> None:
    text = " ".join(["please remember always prefer"] * 100)
    req = ObserveRequest(
        source="opencode:precompact",
        user_id="sam",
        text=text,
        scope=Scope(kind="user", id="sam"),
    )
    salience, _ = classify_observation(req)
    assert salience <= 0.35


def test_classify_regular_source_not_capped() -> None:
    # Same text from a normal source should not be capped
    text = " ".join(["please remember always prefer"] * 100)
    req = ObserveRequest(
        source="matrix:!room:srv",
        user_id="sam",
        text=text,
        scope=Scope(kind="user", id="sam"),
    )
    salience, _ = classify_observation(req)
    assert salience > 0.35
