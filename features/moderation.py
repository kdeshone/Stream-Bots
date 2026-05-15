"""Auto-moderation helpers shared across all platforms."""
from __future__ import annotations

import re
import config
from utils.logger import get_logger

log = get_logger("moderation")

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CAPS_THRESHOLD = 0.7   # fraction of alpha chars that are uppercase
_SPAM_REPEAT_RE = re.compile(r"(.)\1{6,}")  # 7+ repeated chars


class ModerationResult:
    __slots__ = ("should_remove", "reason")

    def __init__(self, should_remove: bool = False, reason: str = "") -> None:
        self.should_remove = should_remove
        self.reason = reason


def check(message: str, username: str) -> ModerationResult:
    """Return a ModerationResult for the given message and sender."""
    username_lower = username.lower()

    if username_lower in config.TRUSTED_USERS:
        return ModerationResult()

    text = message.strip()

    # Banned words
    text_lower = text.lower()
    for word in config.BANNED_WORDS:
        if word and word in text_lower:
            log.info("Banned word detected from %s", username)
            return ModerationResult(True, f"banned word: {word}")

    # Unsolicited links
    if _URL_RE.search(text):
        log.info("Link detected from %s", username)
        return ModerationResult(True, "unsolicited link")

    # Excessive caps (only flag messages longer than 10 chars)
    if len(text) > 10:
        alpha = [c for c in text if c.isalpha()]
        if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > _CAPS_THRESHOLD:
            return ModerationResult(True, "excessive caps")

    # Spam (repeated characters)
    if _SPAM_REPEAT_RE.search(text):
        return ModerationResult(True, "character spam")

    return ModerationResult()
