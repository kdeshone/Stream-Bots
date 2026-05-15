# Stream-Bots

A single unified bot that connects Discord, Twitch, YouTube, and TikTok to streamline engagement across all your platforms simultaneously.

## Features

| Feature | Discord | Twitch | YouTube | TikTok |
|---|---|---|---|---|
| Chat commands | ✅ | ✅ | ✅ | ✅ |
| Auto-moderation | ✅ | ✅ | — | — |
| Welcome new followers/members | ✅ | ✅ | ✅ | ✅ |
| Go-live alerts → Discord | — | ✅ | ✅ | ✅ |

## Built-in commands

| Command | Description |
|---|---|
| `!commands` | List all available commands |
| `!socials` | Post all social links |
| `!discord` | Post Discord invite link |
| `!twitch` | Post Twitch channel link |
| `!youtube` | Post YouTube channel link |
| `!tiktok` | Post TikTok profile link |
| `!so @user` | Shoutout a user |
| `!lurk` | Acknowledge a lurker |

## Auto-moderation

Messages are automatically removed if they contain:
- URLs / links (unless sender is in `TRUSTED_USERS`)
- Banned words (configured via `BANNED_WORDS`)
- Excessive caps (>70% uppercase in messages longer than 10 chars)
- Character spam (7+ repeated characters)

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your tokens and channel IDs
```

### Platform credentials

**Discord**
- Create a bot at https://discord.com/developers/applications
- Enable `Message Content`, `Server Members` intents
- Copy the bot token → `DISCORD_TOKEN`

**Twitch**
- Get an OAuth token at https://twitchapps.com/tmi/ → `TWITCH_BOT_TOKEN`
- Create an app at https://dev.twitch.tv → `TWITCH_CLIENT_ID` + `TWITCH_CLIENT_SECRET`

**YouTube**
- Enable YouTube Data API v3 in Google Cloud Console
- Copy the API key → `YOUTUBE_API_KEY`
- Find your channel ID at https://www.youtube.com/account_advanced → `YOUTUBE_CHANNEL_ID`

**TikTok**
- No credentials needed — just set `TIKTOK_USERNAME` to your TikTok handle

### 3. Run

```bash
python main.py
```

## Adding custom commands

Register commands in any module by importing the shared registry:

```python
from features.commands import registry, CommandContext

async def my_command(ctx: CommandContext) -> str:
    return f"Hello {ctx.user}!"

registry.register("hello", my_command)
```

## Architecture

```
main.py                  # asyncio.gather() runs all bots concurrently
├── bots/
│   ├── discord_bot.py   # discord.py — welcome, mod, commands, alert receiver
│   ├── twitch_bot.py    # twitchio — chat, mod, follow welcome, go-live poll
│   ├── youtube_bot.py   # aiohttp + YouTube API — live chat poll, go-live alert
│   └── tiktok_bot.py    # TikTokLive — comments, follow/sub welcome, go-live alert
└── features/
    ├── commands.py      # Shared command registry (all platforms route here)
    ├── moderation.py    # Link/caps/spam/banned-word detection
    ├── welcome.py       # Welcome message templates
    └── alerts.py        # Discord embed alerts when any platform goes live
```

## Notes

- **YouTube chat replies** require OAuth2 credentials (not just an API key). The bot logs replies to stdout; wire up `client_secrets.json` for full write access.
- **TikTok** — the `TikTokLive` library is read-only. Command responses are logged to stdout.
- The go-live poller for Twitch and YouTube runs every 60 seconds.
