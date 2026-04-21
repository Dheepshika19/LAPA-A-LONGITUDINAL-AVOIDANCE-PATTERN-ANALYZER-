"""
OpenAI-compatible chat completions with safe local fallback.
"""

from __future__ import annotations

import json
import logging
import os
import random
import urllib.error
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_LOCAL_FALLBACKS: List[str] = [
    "I hear you. It takes courage to open up. What feelings come up when you think about that?",
    "That makes sense. You are not alone in feeling this way. Would a short journal entry help you sort through it?",
    "Thank you for sharing. If patterns in your writing feel confusing, a clinician can help you interpret them safely.",
    "It is okay to feel that way. Your feelings are valid. Would you like to try a brief breathing pause together?",
    "I am here with you. Writing sometimes helps us see our thoughts more clearly. Want to jot down one sentence?",
]


def local_fallback_reply() -> str:
    """Return a deterministic-style supportive line without external services."""
    return random.choice(_LOCAL_FALLBACKS)


def compose_chat_reply(user_message: str, cfg: Dict[str, Any]) -> str:
    """
    Call a remote OpenAI-compatible ``/chat/completions`` endpoint when configured.

    Args:
        user_message: Latest user utterance.
        cfg: Global configuration containing a ``chat`` block.

    Returns:
        Assistant text, or an empty string when remote generation is unavailable.
    """
    chat = cfg.get("chat", {}) or {}
    provider = str(chat.get("provider", "none")).lower()
    if provider in ("none", "", "disabled", "off"):
        return ""
    api_key_env = str(chat.get("api_key_env", "LAPA_OPENAI_API_KEY"))
    api_key = os.environ.get(api_key_env, "").strip()
    api_base = os.environ.get("LAPA_CHAT_API_BASE", str(chat.get("api_base", "") or "")).strip()
    if not api_key or not api_base:
        return ""
    model = str(chat.get("model", "gpt-4o-mini"))
    max_tokens = int(chat.get("max_tokens", 400))
    timeout = int(chat.get("timeout_sec", 60))
    system_prompt = str(
        chat.get(
            "system_prompt",
            "You are LAPA, a supportive mental wellness assistant. You do not diagnose.",
        )
    )
    url = api_base.rstrip("/") + "/chat/completions"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": max_tokens,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return str(payload["choices"][0]["message"]["content"]).strip()
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, IndexError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Remote chat failed (%s); falling back locally.", exc)
        return ""
