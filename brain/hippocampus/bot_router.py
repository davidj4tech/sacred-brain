"Routing logic for handling Matrix mentions and deciding which 'brain' responds."
from __future__ import annotations

import logging
import re
from pathlib import Path

from sacred_brain.prompts import SYSTEM_PROMPT
from sacred_brain.sam_pipeline import sam_generate_reply

from .config import HippocampusSettings
from .mem0_adapter import Mem0Adapter
from .summarizers import SummarizerConfig, summarize_texts as summarize_via_llm

LOGGER = logging.getLogger(__name__)

_DOC_CMD_RE = re.compile(
    r"(?is)^(?:\s*(?:sam\s*[:,])\s*)?(?:!doc|doc)\s+([A-Z0-9_\-]+)(?:\s*[:\-]\s*(.*))?$"
)
_DOC_NAME_RE = re.compile(r"^[A-Z0-9_\-]+$")


def _docs_dir() -> Path:
    # Canonical Sacred Brain docs directory
    return Path("/opt/sacred-brain/docs")


def _load_doc_text(doc_name: str, max_chars: int = 20000) -> str | None:
    """Allowlisted doc loader.

    Only reads files under /opt/sacred-brain/docs and only by base name.
    Example: MEMORY_GOVERNOR -> /opt/sacred-brain/docs/MEMORY_GOVERNOR.md
    """
    name = (doc_name or "").strip().upper()
    if not _DOC_NAME_RE.match(name):
        return None
    path = _docs_dir() / f"{name}.md"
    if not path.exists() or not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        LOGGER.warning("Failed to read doc %s: %s", path, exc)
        return None
    return text[:max_chars]


class BotRouter:
    def __init__(
        self,
        settings: HippocampusSettings,
        adapter: Mem0Adapter,
        agno_agent: object | None,
        summarizer_config: SummarizerConfig,
        sam_bias_note: str = "",
    ):
        self.settings = settings
        self.adapter = adapter
        self.agno_agent = agno_agent
        self.summarizer_config = summarizer_config
        self.sam_bias_note = sam_bias_note

    def generate_response(
        self,
        sender: str,
        body: str,
        context: list[str],
        room_id: str,
    ) -> str | None:
        """
        Decide which backend (Sam, Agno, or Summarizer) should answer.
        Returns the raw reply string, or None if no valid response could be generated.
        """
        reply: str | None = None

        # 0) Doc lookup (safe allowlist):
        # Usage: "Sam: doc MEMORY_GOVERNOR" or "doc MEMORY_GOVERNOR: <question>".
        cmd = (body or "").strip()
        m = _DOC_CMD_RE.match(cmd)
        if m:
            doc_name = m.group(1)
            question = (m.group(2) or "").strip()
            doc_text = _load_doc_text(doc_name)
            if not doc_text:
                return f"I couldn't find docs/{doc_name.upper()}.md"
            doc_prompt = (
                f"You are answering based ONLY on the provided repository document excerpt. "
                f"If the answer isn't in the excerpt, say you can't find it there.\n\n"
                f"Document: {doc_name.upper()}.md\n\n"
                f"--- BEGIN DOC EXCERPT ---\n{doc_text}\n--- END DOC EXCERPT ---\n\n"
            )
            if question:
                user_msg = f"Question: {question}\n\nAnswer with specific references to the excerpt."  # noqa: E501
            else:
                user_msg = (
                    "Summarize this document for a technical user in 8 bullet points. "
                    "Include 2 direct quotes (short lines) from the excerpt."
                )
            if self.settings.sam.enabled:
                return sam_generate_reply(
                    user_msg,
                    [],
                    SYSTEM_PROMPT + "\n\n" + doc_prompt,
                    memory_context_max=0,
                    bias_note=self.sam_bias_note if self.settings.sam_astrology.enabled else "",
                )
            # If Sam is disabled, just return the start of the doc.
            return doc_text[:2000]

        # 1. Sam (Astrology/LLM) Strategy
        if self.settings.sam.enabled:
            # Fetch memories relevant to the user's query
            mems = self.adapter.query_memories(
                user_id=sender,
                query=body,
                limit=self.settings.sam.memory_candidates_max,
            )
            # Bias note is pre-calculated in app state
            reply = sam_generate_reply(
                body,
                mems,
                SYSTEM_PROMPT,
                memory_context_max=self.settings.sam.memory_context_max,
                bias_note=self.sam_bias_note if self.settings.sam_astrology.enabled else "",
            )
            if reply:
                return reply

        # 2. Agno Agent Strategy
        if self.settings.agno.enabled and self.agno_agent:
            prompt = self._format_matrix_prompt(sender, body, context)
            try:
                # Agno agent .run() returns a RunResponse or similar object
                run = self.agno_agent.run(prompt, user_id=sender, session_id=room_id)
                content = getattr(run, "content", None)
                reply = content if isinstance(content, str) else getattr(run, "get_content_as_string", lambda: "")()
                if reply:
                    return reply
            except Exception as exc:
                LOGGER.warning("Agno agent failed; falling back: %s", exc, exc_info=True)
                # Fall through to summarizer

        # 3. Fallback: Summarizer
        full_context = list(context) + [f"{sender}: {body}"]
        reply = (
            summarize_via_llm(full_context, self.summarizer_config)
            if self.summarizer_config.enabled
            else self.adapter.summarize_texts(full_context)
        )

        return reply if reply else "I need more context before I can help."

    def _format_matrix_prompt(self, sender: str, body: str, context: list[str]) -> str:
        context_lines = "\n".join(f"- {line}" for line in context) if context else "No prior context."
        return (
            "You are responding to a Matrix mention. "
            "Use the tools to fetch or store memories for this sender as needed. "
            f"Sender: {sender}\n"
            f"Message: {body}\n"
            f"Context:\n{context_lines}"
        )
