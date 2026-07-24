"""Claude API wrapper for Loop 3 (content fission).

Loads the starter prompt from prompts/generate.txt, fills in the article
variables and returns the model's raw output. Parsing the 12 units out of that
output lives in loops/generate_loop.py.
"""
from __future__ import annotations

import logging
from typing import Optional

from config import settings

try:
    import anthropic
except ImportError:  # pragma: no cover - surfaced at runtime
    anthropic = None


class ClaudeService:
    def __init__(self, logger: Optional[logging.Logger] = None, client=None, model: Optional[str] = None):
        self.log = logger or logging.getLogger("loop.claude")
        self.model = model or settings.CLAUDE_MODEL
        if client is not None:
            self.client = client
        else:
            if anthropic is None:
                raise RuntimeError("anthropic is not installed. `pip install -r requirements.txt`")
            if not settings.ANTHROPIC_API_KEY:
                raise RuntimeError("ANTHROPIC_API_KEY is not set.")
            self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    @staticmethod
    def load_prompt() -> str:
        path = settings.PROMPTS_DIR / "generate.txt"
        return path.read_text(encoding="utf-8")

    def build_prompt(self, issue_number, cta_url: str, article_text: str) -> str:
        return (
            self.load_prompt()
            .replace("{ISSUE_NUMBER}", str(issue_number))
            .replace("{CTA_URL}", cta_url or "")
            .replace("{ARTICLE_FULL_TEXT}", article_text or "")
        )

    def generate_units(self, issue_number, cta_url: str, article_text: str, max_tokens: int = 8000) -> str:
        """Run the fission prompt and return Claude's full text response."""
        prompt = self.build_prompt(issue_number, cta_url, article_text)
        self.log.info("Calling Claude (%s) to fission article %s", self.model, issue_number)
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")
