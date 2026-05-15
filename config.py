import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise EnvironmentError(f"Missing required env var: {key}")
    return val


def _list(key: str) -> list[str]:
    raw = os.getenv(key, "")
    return [v.strip().lower() for v in raw.split(",") if v.strip()]


# Discord
DISCORD_TOKEN = _require("DISCORD_TOKEN")
DISCORD_GUILD_ID = int(_require("DISCORD_GUILD_ID"))
DISCORD_WELCOME_CHANNEL_ID = int(_require("DISCORD_WELCOME_CHANNEL_ID"))
DISCORD_ALERTS_CHANNEL_ID = int(_require("DISCORD_ALERTS_CHANNEL_ID"))
DISCORD_LOG_CHANNEL_ID = int(os.getenv("DISCORD_LOG_CHANNEL_ID", "0"))

# Twitch
TWITCH_BOT_TOKEN = _require("TWITCH_BOT_TOKEN")
TWITCH_BOT_NICK = _require("TWITCH_BOT_NICK")
TWITCH_CHANNEL = _require("TWITCH_CHANNEL")
TWITCH_CLIENT_ID = _require("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = _require("TWITCH_CLIENT_SECRET")

# YouTube
YOUTUBE_API_KEY = _require("YOUTUBE_API_KEY")
YOUTUBE_CHANNEL_ID = _require("YOUTUBE_CHANNEL_ID")
YOUTUBE_CLIENT_SECRETS_FILE = os.getenv("YOUTUBE_CLIENT_SECRETS_FILE", "client_secrets.json")

# TikTok
TIKTOK_USERNAME = _require("TIKTOK_USERNAME")

# Shared
COMMAND_PREFIX = os.getenv("COMMAND_PREFIX", "!")
TRUSTED_USERS: set[str] = set(_list("TRUSTED_USERS"))
BANNED_WORDS: list[str] = _list("BANNED_WORDS")

SOCIAL_DISCORD = os.getenv("SOCIAL_DISCORD", "")
SOCIAL_TWITCH = os.getenv("SOCIAL_TWITCH", "")
SOCIAL_YOUTUBE = os.getenv("SOCIAL_YOUTUBE", "")
SOCIAL_TIKTOK = os.getenv("SOCIAL_TIKTOK", "")
