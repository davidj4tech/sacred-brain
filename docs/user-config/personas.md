# Personas

Sacred Brain distinguishes the human operator from the bot personas. All memories are scoped by a `user_id` that names either a human or a persona — never both.

## The split

| `user_id` | Kind | Represents | Primary use |
|-----------|------|------------|-------------|
| `david` | human | David-the-human | ChatGPT-extracted memories, cross-persona facts, anything a human would later want to reclaim as their own |
| `sam` | persona | Sam bot persona | Default for homer / sp4r / p8ar coding agents; Clawdbot / OpenClaw workspace bots |
| `mel` | persona | Mel bot persona | Default for melr |

## Rule of thumb

- If a **human might later want to attribute the memory to themselves**, write under a human `user_id`.
- If the memory is clearly the **bot's voice or state**, use a persona `user_id`.
- Don't conflate them. Retrofitting later means re-tagging, which is painful.

## Future multi-human pressure

David has flagged multi-human access as a likely v2 concern. Don't build ACLs or auth yet, but **don't architect anything that forecloses them** either — e.g., keep scope paths open-ended enough to allow a `human:<name>` layer above `user:<persona>` later.

Concretely: scope paths like `project:foo/user:sam` currently mean "project foo as seen by the sam persona". A future form `human:david/project:foo/user:sam` would let another human with their own persona share the same project without cross-contaminating memories.

## Device → persona defaults

See [`machines.md`](machines.md) for the authoritative per-machine defaults (which persona `$GOVERNOR_USER_ID` gets on each host).
