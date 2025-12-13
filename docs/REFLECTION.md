# Sam Reflection

Sam can add a short reflective sentence after an assistant reply.

Behavior
- Queries up to 3 memories with the current user message + draft reply.
- Only `kind=thread` or `kind=preference` (or `sticky=true`) are eligible.
- Skips sensitive/logistics unless currently discussed.
- If no relevant memory, no reflection; otherwise max 1 sentence (~25 words), prefixed `Sam:`.

Tuning
- Thresholds live in `brain/hippocampus/reflection.py` (`_overlap_score` cutoff 0.1, token/keyword filters).
- Rerank is optional and separate (LiteLLM) for general recall; reflection itself is deterministic.
- To adjust reflection strictness, tweak the overlap cutoff or eligible kinds in `reflection_pass`.

Notes
- Memories should include `metadata.kind` (thread | fact | task | preference) and optional `sticky`.
- Avoid storing sensitive data without `sensitive=true` metadata; reflection will skip unless in current context.
