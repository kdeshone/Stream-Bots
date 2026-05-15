"""Twitch bot — chat commands, moderation, follow/sub welcomes, go-live alerts."""
from __future__ import annotations

import asyncio

import aiohttp
import twitchio
from twitchio.ext import commands, pubsub

import config
from features import commands as cmd_feature
from features import moderation, welcome
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("twitch")

_POLL_INTERVAL = 60   # seconds between stream-status polls


class TwitchBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            token=config.TWITCH_BOT_TOKEN,
            prefix=config.COMMAND_PREFIX,
            initial_channels=[config.TWITCH_CHANNEL],
        )
        self._was_live = False
        self._http_session: aiohttp.ClientSession | None = None

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

        username = message.author.name if message.author else "unknown"
        content = message.content

        # Moderation
        result = moderation.check(content, username)
        if result.should_remove:
            try:
                await message.channel.send(
                    f"/delete {message.id}"  # Twitch delete-message command
                )
                await message.channel.send(
                    f"@{username} Your message was removed: {result.reason}."
                )
            except Exception as exc:
                log.warning("Could not delete Twitch message: %s", exc)
            return

        # Commands
        if content.startswith(config.COMMAND_PREFIX):
            parts = content[len(config.COMMAND_PREFIX):].split()
            if parts:
                ctx = cmd_feature.CommandContext(
                    platform="twitch",
                    user=username,
                    channel=message.channel.name,
                    args=parts[1:],
                    raw_message=message,
                )
                response = await cmd_feature.registry.execute(parts[0], ctx)
                if response:
                    await message.channel.send(response)
                    return

        await self.handle_commands(message)

    async def event_follow(self, follower: twitchio.User, channel: twitchio.Channel) -> None:  # type: ignore[override]
        ch = self.get_channel(config.TWITCH_CHANNEL)
        if ch:
            await ch.send(welcome.twitch_follower(follower.name))

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


def create() -> TwitchBot:
    return TwitchBot()


async def run(bot: TwitchBot) -> None:
    await bot.start()
