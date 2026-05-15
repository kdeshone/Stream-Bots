"""Auto-moderation helpers and strike tracking shared across all platforms."""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

import config
from utils.logger import get_logger

log = get_logger("moderation")

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_CAPS_THRESHOLD = 0.7
_SPAM_REPEAT_RE = re.compile(r"(.)\1{6,}")


@dataclass
class ModerationResult:
    should_remove: bool = False
    reason: str = ""


def check(message: str, username: str) -> ModerationResult:
    if username.lower() in config.TRUSTED_USERS:
        return ModerationResult()

    text = message.strip()
    text_lower = text.lower()

    for word in config.BANNED_WORDS:
        if word and word in text_lower:
            log.info("Banned word from %s", username)
            return ModerationResult(True, f"banned word: {word}")

    if _URL_RE.search(text):
        log.info("Link detected from %s", username)
        return ModerationResult(True, "unsolicited link")

    if len(text) > 10:
        alpha = [c for c in text if c.isalpha()]
        if alpha and sum(1 for c in alpha if c.isupper()) / len(alpha) > _CAPS_THRESHOLD:
            return ModerationResult(True, "excessive caps")

    if _SPAM_REPEAT_RE.search(text):
        return ModerationResult(True, "character spam")

    return ModerationResult()


# ── Strike tracker ────────────────────────────────────────────────────────────

# Escalation thresholds: strikes -> action label
_ESCALATION = {1: "warn", 2: "timeout", 3: "ban"}
_DEFAULT_TIMEOUT_SECONDS = 600   # 10 minutes


class StrikeTracker:
    """Tracks per-platform strike counts and returns the escalated action."""

    def __init__(self) -> None:
        # platform -> username_lower -> strike count
        self._strikes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record(self, platform: str, username: str) -> str:
        """Add a strike and return the action to take: 'warn', 'timeout', or 'ban'."""
        key = username.lower()
        self._strikes[platform][key] += 1
        count = self._strikes[platform][key]
        action = _ESCALATION.get(count, "ban")
        log.info("Strike %d for %s on %s → %s", count, username, platform, action)
        return action

    def count(self, platform: str, username: str) -> int:
        return self._strikes[platform][username.lower()]

    def clear(self, platform: str, username: str) -> None:
        self._strikes[platform].pop(username.lower(), None)
        log.info("Cleared strikes for %s on %s", username, platform)

    def default_timeout(self) -> int:
        return _DEFAULT_TIMEOUT_SECONDS


# Singleton shared across all bots.
strike_tracker = StrikeTracker()
