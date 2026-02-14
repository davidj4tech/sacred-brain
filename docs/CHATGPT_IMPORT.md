# Importing ChatGPT History into Hippocampus

This script reads a ChatGPT data export, uses an LLM to extract durable personal memories from each conversation, and stores them in Hippocampus.

## Prerequisites

- A ChatGPT data export (request from https://chat.openai.com → Settings → Data controls → Export data)
- Extract the zip — you need the folder containing `conversations.json`
- Hippocampus running on port 54321 (`just health` to verify)
- LiteLLM gateway running on port 4000

## Quick Start

```bash
cd /opt/sacred-brain

# 1. Preview what will be extracted (dry run)
.venv/bin/python scripts/import_chatgpt.py \
  --export /path/to/extracted-export-folder \
  --user david \
  --dry-run

# 2. Import for real
.venv/bin/python scripts/import_chatgpt.py \
  --export /path/to/extracted-export-folder \
  --user david
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--export` | *(required)* | Path to extracted export folder containing `conversations.json` |
| `--user` | `david` | Hippocampus user_id to store memories under |
| `--limit` | `0` (all) | Max conversations to process |
| `--offset` | `0` | Start from this conversation index (for resuming) |
| `--dry-run` | off | Print extracted memories without storing |
| `--llm-url` | `http://127.0.0.1:4000` | LiteLLM gateway URL |
| `--llm-model` | `gpt-4o-mini` | Model for memory extraction |
| `--hippo-url` | `http://127.0.0.1:54321` | Hippocampus API URL |
| `--hippo-key` | *(empty)* | Hippocampus API key (if auth enabled) |
| `--sleep` | `0.25` | Seconds to wait between conversations (rate limiting) |

## How It Works

1. Reads each conversation from `conversations.json`
2. Builds a compact transcript (first 12 + last 18 messages, max 14k chars)
3. Sends the transcript to the LLM with a prompt to extract high-signal memories
4. Each memory gets a kind (`preference`, `project`, `decision`, `fact`, `todo`, `identity`, `setup`) and a confidence score
5. Stores extracted memories in Hippocampus with metadata linking back to the source conversation

The LLM is instructed to:
- Extract only durable, high-signal items (max 5 per conversation)
- Skip generic advice
- Filter out secrets (API keys, passwords, tokens)

## Examples

Import a specific batch of conversations:
```bash
# Process conversations 100-199
.venv/bin/python scripts/import_chatgpt.py \
  --export ~/exports/chatgpt-20260128 \
  --user david \
  --offset 100 \
  --limit 100
```

Use a different model for extraction:
```bash
.venv/bin/python scripts/import_chatgpt.py \
  --export ~/exports/chatgpt-20260128 \
  --user david \
  --llm-model sam-deep
```

With Hippocampus API key:
```bash
.venv/bin/python scripts/import_chatgpt.py \
  --export ~/exports/chatgpt-20260128 \
  --user david \
  --hippo-key hippo_local_a58b583f7a844f0eb3bc02e58d56f5bd
```

## Metadata

Each stored memory includes this metadata for traceability:

```json
{
  "source": "chatgpt-export",
  "conversation_id": "abc-123",
  "title": "Planning my garden layout",
  "create_time": 1706000000,
  "update_time": 1706100000,
  "kind": "preference",
  "confidence": 0.85
}
```
