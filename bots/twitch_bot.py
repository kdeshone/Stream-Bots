"""Twitch bot — chat commands, moderation, mod commands, follow/sub welcomes, go-live alerts."""
from __future__ import annotations

import asyncio

import aiohttp
import twitchio
from twitchio.ext import commands

import config
from features import commands as cmd_feature
from features import moderation, welcome
from features.moderation import strike_tracker
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("twitch")

_POLL_INTERVAL = 60
_DEFAULT_TIMEOUT_SECONDS = 600   # 10 minutes

_MOD_COMMANDS = {
    "warn", "timeout", "ban", "unban", "pardon",
    "slow", "slowoff", "subonly", "sunonlyoff", "emoteonly", "emoteonlyoff",
}


class TwitchBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            token=config.TWITCH_BOT_TOKEN,
            prefix=config.COMMAND_PREFIX,
            initial_channels=[config.TWITCH_CHANNEL],
        )
        self._was_live = False
        self._http_session: aiohttp.ClientSession | None = None
        self._seen_chatters: set[str] = set()   # usernames seen this session

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def event_ready(self) -> None:
        log.info("Twitch bot ready as %s", self.nick)
        self._http_session = aiohttp.ClientSession()
        asyncio.create_task(self._poll_live_status())

    async def close(self) -> None:
        if self._http_session:
            await self._http_session.close()
        await super().close()

    # ── events ────────────────────────────────────────────────────────────────

    async def event_message(self, message: twitchio.Message) -> None:
        if message.echo:
            return

        author = message.author
        username = author.name if author else "unknown"
        content = message.content
        channel = message.channel

        # First-time chatter welcome
        if username not in self._seen_chatters:
            self._seen_chatters.add(username)
            await channel.send(f"Welcome to the stream, @{username}! Glad you're here! PogChamp")

        # Auto-moderation with escalation
        result = moderation.check(content, username)
        if result.should_remove:
            await self._handle_auto_mod(message, result.reason)
            return

        # Commands
        if content.startswith(config.COMMAND_PREFIX):
            parts = content[len(config.COMMAND_PREFIX):].split()
            if parts:
                cmd_name = parts[0].lower()

                # Mod commands — check permissions first
                if cmd_name in _MOD_COMMANDS:
                    if not self._is_mod(author):
                        await channel.send(
                            f"@{username} You don't have permission to use that command."
                        )
                        return
                    await self._handle_mod_command(cmd_name, parts[1:], message)
                    return

                ctx = cmd_feature.CommandContext(
                    platform="twitch",
                    user=username,
                    channel=channel.name,
                    args=parts[1:],
                    raw_message=message,
                )
                response = await cmd_feature.registry.execute(cmd_name, ctx)
                if response:
                    await channel.send(response)
                    return

        await self.handle_commands(message)

    async def event_follow(self, follower: twitchio.User, channel: twitchio.Channel) -> None:  # type: ignore[override]
        ch = self.get_channel(config.TWITCH_CHANNEL)
        if ch:
            await ch.send(welcome.twitch_follower(follower.name))

    # ── mod command dispatch ──────────────────────────────────────────────────

    async def _handle_mod_command(
        self, cmd: str, args: list[str], message: twitchio.Message
    ) -> None:
        channel = message.channel
        target = args[0].lstrip("@").lower() if args else None

        # Chat-mode commands (no target needed)
        if cmd == "slow":
            seconds = args[0] if args and args[0].isdigit() else "5"
            await channel.send(f"/slow {seconds}")
            await channel.send(f"Slow mode enabled ({seconds}s).")
            return
        if cmd == "slowoff":
            await channel.send("/slowoff")
            await channel.send("Slow mode disabled.")
            return
        if cmd == "subonly":
            await channel.send("/subscribers")
            await channel.send("Subscriber-only mode enabled.")
            return
        if cmd == "sunonlyoff":
            await channel.send("/subscribersoff")
            await channel.send("Subscriber-only mode disabled.")
            return
        if cmd == "emoteonly":
            await channel.send("/emoteonly")
            await channel.send("Emote-only mode enabled.")
            return
        if cmd == "emoteonlyoff":
            await channel.send("/emoteonlyoff")
            await channel.send("Emote-only mode disabled.")
            return

        # Target required below this point
        if not target:
            await channel.send(f"Usage: {config.COMMAND_PREFIX}{cmd} @username [reason/seconds]")
            return

        reason = " ".join(args[1:]) if len(args) > 1 else "No reason given"

        if cmd == "pardon":
            strike_tracker.clear("twitch", target)
            await channel.send(f"Strikes cleared for @{target}.")

        elif cmd == "warn":
            await self._warn_user(target, channel, reason)

        elif cmd == "timeout":
            seconds = int(args[1]) if len(args) > 1 and args[1].isdigit() else _DEFAULT_TIMEOUT_SECONDS
            reason_text = " ".join(args[2:]) if len(args) > 2 else "No reason given"
            await channel.send(f"/timeout {target} {seconds}")
            await channel.send(f"@{target} has been timed out for {seconds}s. Reason: {reason_text}")

        elif cmd == "ban":
            await channel.send(f"/ban {target}")
            await channel.send(f"@{target} has been banned. Reason: {reason}")

        elif cmd == "unban":
            await channel.send(f"/unban {target}")
            await channel.send(f"@{target} has been unbanned.")

    async def _warn_user(
        self, username: str, channel: twitchio.Channel, reason: str
    ) -> None:
        action = strike_tracker.record("twitch", username)
        strikes = strike_tracker.count("twitch", username)

        if action == "warn":
            await channel.send(
                f"@{username} Warning (strike {strikes}): {reason}. "
                "Further violations will result in a timeout."
            )
        elif action == "timeout":
            await channel.send(
                f"@{username} has been timed out ({reason}). Strike {strikes}."
            )
            await channel.send(f"/timeout {username} {_DEFAULT_TIMEOUT_SECONDS}")
        elif action == "ban":
            await channel.send(
                f"@{username} has been banned after {strikes} violations."
            )
            await channel.send(f"/ban {username}")

    # ── auto-mod with escalation ──────────────────────────────────────────────

    async def _handle_auto_mod(
        self, message: twitchio.Message, reason: str
    ) -> None:
        username = message.author.name if message.author else "unknown"
        channel = message.channel

        try:
            await channel.send(f"/delete {message.id}")
        except Exception as exc:
            log.warning("Could not delete Twitch message: %s", exc)

        action = strike_tracker.record("twitch", username)
        strikes = strike_tracker.count("twitch", username)

        if action == "warn":
            await channel.send(
                f"@{username} Message removed ({reason}). "
                "Strike 1 — next violation will result in a timeout."
            )
        elif action == "timeout":
            await channel.send(
                f"@{username} Timed out for {_DEFAULT_TIMEOUT_SECONDS // 60} minutes ({reason}). Strike {strikes}."
            )
            await channel.send(f"/timeout {username} {_DEFAULT_TIMEOUT_SECONDS}")
        elif action == "ban":
            await channel.send(f"@{username} Banned after {strikes} violations.")
            await channel.send(f"/ban {username}")

    # ── go-live polling ───────────────────────────────────────────────────────

    async def _poll_live_status(self) -> None:
        while True:
            await asyncio.sleep(_POLL_INTERVAL)
            try:
                stream = await self._fetch_stream()
                if stream and not self._was_live:
                    self._was_live = True
                    await alert_manager.send_live_alert(
                        platform="twitch",
                        title=stream.get("title", ""),
                        streamer=stream.get("user_name", config.TWITCH_CHANNEL),
                        url=f"https://twitch.tv/{config.TWITCH_CHANNEL}",
                        game=stream.get("game_name", ""),
                        thumbnail_url=stream.get("thumbnail_url", "").replace(
                            "{width}", "1280"
                        ).replace("{height}", "720"),
                    )
                elif not stream:
                    self._was_live = False
            except Exception as exc:
                log.error("Twitch stream poll error: %s", exc)

    async def _fetch_stream(self) -> dict | None:
        if not self._http_session:
            return None
        token = await self._get_app_token()
        if not token:
            return None
        headers = {
            "Client-ID": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {token}",
        }
        url = f"https://api.twitch.tv/helix/streams?user_login={config.TWITCH_CHANNEL}"
        async with self._http_session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            streams = data.get("data", [])
            return streams[0] if streams else None

    async def _get_app_token(self) -> str | None:
        if not self._http_session:
            return None
        data = {
            "client_id": config.TWITCH_CLIENT_ID,
            "client_secret": config.TWITCH_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        async with self._http_session.post(
            "https://id.twitch.tv/oauth2/token", data=data
        ) as resp:
            if resp.status != 200:
                return None
            return (await resp.json()).get("access_token")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _is_mod(self, author: twitchio.Chatter | None) -> bool:
        if author is None:
            return False
        if author.name.lower() in config.TRUSTED_USERS:
            return True
        return bool(author.is_mod or author.is_broadcaster)


def create() -> TwitchBot:
    return TwitchBot()


async def run(bot: TwitchBot) -> None:
    await bot.start()
