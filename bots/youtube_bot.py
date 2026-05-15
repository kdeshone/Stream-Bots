"""YouTube bot — polls live chat, handles commands, fires go-live alerts."""
from __future__ import annotations

import asyncio

import aiohttp

import config
from features import commands as cmd_feature
from features import welcome
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("youtube")

_CHAT_POLL_INTERVAL = 10   # YouTube live chat poll interval (seconds)
_STREAM_POLL_INTERVAL = 60  # go-live detection poll interval (seconds)
_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeBot:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._live_chat_id: str | None = None
        self._next_page_token: str | None = None
        self._was_live = False
        self._known_message_ids: set[str] = set()

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        log.info("YouTube bot started, polling channel %s", config.YOUTUBE_CHANNEL_ID)
        await asyncio.gather(
            self._poll_live_status(),
            self._poll_chat(),
        )

    async def close(self) -> None:
        if self._session:
            await self._session.close()

    # ── go-live detection ─────────────────────────────────────────────────────

    async def _poll_live_status(self) -> None:
        while True:
            try:
                broadcast = await self._fetch_active_broadcast()
                if broadcast and not self._was_live:
                    self._was_live = True
                    self._live_chat_id = (
                        broadcast.get("snippet", {})
                        .get("liveChatId")
                    )
                    snippet = broadcast.get("snippet", {})
                    title = snippet.get("title", "")
                    vid_id = broadcast.get("id", "")
                    await alert_manager.send_live_alert(
                        platform="youtube",
                        title=title,
                        streamer=snippet.get("channelTitle", config.YOUTUBE_CHANNEL_ID),
                        url=f"https://www.youtube.com/watch?v={vid_id}",
                        thumbnail_url=(
                            broadcast.get("snippet", {})
                            .get("thumbnails", {})
                            .get("maxres", {})
                            .get("url", "")
                        ),
                    )
                elif not broadcast:
                    self._was_live = False
                    self._live_chat_id = None
            except Exception as exc:
                log.error("YouTube stream poll error: %s", exc)
            await asyncio.sleep(_STREAM_POLL_INTERVAL)

    async def _fetch_active_broadcast(self) -> dict | None:
        if not self._session:
            return None
        params = {
            "part": "snippet",
            "broadcastStatus": "active",
            "broadcastType": "all",
            "key": config.YOUTUBE_API_KEY,
        }
        async with self._session.get(f"{_BASE}/liveBroadcasts", params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            items = data.get("items", [])
            return items[0] if items else None

    # ── live chat polling ─────────────────────────────────────────────────────

    async def _poll_chat(self) -> None:
        while True:
            if self._live_chat_id and self._session:
                try:
                    await self._process_chat_messages()
                except Exception as exc:
                    log.error("YouTube chat poll error: %s", exc)
            await asyncio.sleep(_CHAT_POLL_INTERVAL)

    async def _process_chat_messages(self) -> None:
        params: dict = {
            "part": "snippet,authorDetails",
            "liveChatId": self._live_chat_id,
            "key": config.YOUTUBE_API_KEY,
            "maxResults": 200,
        }
        if self._next_page_token:
            params["pageToken"] = self._next_page_token

        assert self._session is not None
        async with self._session.get(f"{_BASE}/liveChat/messages", params=params) as resp:
            if resp.status != 200:
                return
            data = await resp.json()

        self._next_page_token = data.get("nextPageToken")

        for item in data.get("items", []):
            msg_id = item.get("id", "")
            if msg_id in self._known_message_ids:
                continue
            self._known_message_ids.add(msg_id)

            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            text: str = snippet.get("displayMessage", "")
            username: str = author.get("displayName", "anonymous")
            msg_type: str = snippet.get("type", "")

            if msg_type == "newSponsorEvent":
                log.info("New YouTube member: %s", username)
                # Chat reply via YouTube API requires OAuth — log only here.
                continue

            if text.startswith(config.COMMAND_PREFIX):
                parts = text[len(config.COMMAND_PREFIX):].split()
                if parts:
                    ctx = cmd_feature.CommandContext(
                        platform="youtube",
                        user=username,
                        channel=config.YOUTUBE_CHANNEL_ID,
                        args=parts[1:],
                        raw_message=item,
                    )
                    response = await cmd_feature.registry.execute(parts[0], ctx)
                    if response:
                        await self._send_chat_message(response)

    async def _send_chat_message(self, text: str) -> None:
        # Sending messages to YouTube live chat requires OAuth2, not just an
        # API key. Log the response so the streamer can manually paste it,
        # or wire up OAuth credentials for full write access.
        log.info("[YouTube chat reply] %s", text)


def create() -> "YouTubeBot":
    return YouTubeBot()


async def run(bot: "YouTubeBot") -> None:
    await bot.start()
