# API Reference

Base URL defaults to `http://localhost:54321` when running locally.

If the summarizer is enabled (see `[summarizer]` in the config), the `/summaries` endpoint uses your configured LLM (via Litellm) to produce higher-quality output; otherwise it falls back to a naive concatenation. Include the auth header (`X-API-Key`) on all non-health endpoints.

If API-key authentication is enabled (see `[auth]` in the config), include the configured header (default `X-API-Key`) with a valid key for every endpoint except `/health`.

## `GET /health`

Returns `{ "status": "ok" }` and can be used for probes.

## `POST /memories`

Create a new memory record.

**Request body**

```json
{
  "user_id": "alice",
  "text": "Met Bob at the café",
  "metadata": { "mood": "happy" }
}
```

**Response**

```json
{
  "memory": {
    "id": "<uuid>",
    "user_id": "alice",
    "text": "Met Bob at the café",
    "metadata": { "mood": "happy" },
    "score": 1.0
  }
}
```

## `GET /memories/{user_id}?query=...&limit=5`

Query stored memories for a user. The `query` parameter is required.
`limit` defaults to the config value (`mem0.query_limit`).

**Response**

```json
{
  "memories": [
    {
      "id": "<uuid>",
      "user_id": "alice",
      "text": "Met Bob at the café",
      "metadata": { "mood": "happy" },
      "score": 0.91
    }
  ]
}
```

## `DELETE /memories/{memory_id}`

Delete a memory by its identifier.

**Response**

```json
{ "deleted": true }
```

When the memory does not exist, the API returns a `404` error.

## `POST /summaries`

Summarise one or more texts. Falls back to a simple concatenation when a real
Mem0 summariser is not configured.

**Request body**

```json
{
  "texts": ["Met Bob at the café", "Discussed weekend plans"]
}
```

**Response**

```json
{ "summary": "Met Bob at the café Discussed weekend plans" }
```
