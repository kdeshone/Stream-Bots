"""TikTok LIVE bot — comments, follows, subs, go-live alerts."""
from __future__ import annotations

from TikTokLive import TikTokLiveClient
from TikTokLive.events import (
    CommentEvent,
    FollowEvent,
    SubscribeEvent,
    ConnectEvent,
    DisconnectEvent,
    LiveEndEvent,
)

import config
from features import commands as cmd_feature
from features import welcome
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("tiktok")


class TikTokBot:
    def __init__(self) -> None:
        self._client = TikTokLiveClient(unique_id=f"@{config.TIKTOK_USERNAME}")
        self._register_events()

    def _register_events(self) -> None:
        self._client.on(ConnectEvent)(self._on_connect)
        self._client.on(DisconnectEvent)(self._on_disconnect)
        self._client.on(LiveEndEvent)(self._on_live_end)
        self._client.on(CommentEvent)(self._on_comment)
        self._client.on(FollowEvent)(self._on_follow)
        self._client.on(SubscribeEvent)(self._on_subscribe)

    # ── events ────────────────────────────────────────────────────────────────

    async def _on_connect(self, event: ConnectEvent) -> None:
        log.info("Connected to TikTok LIVE for @%s", config.TIKTOK_USERNAME)
        room_url = f"https://www.tiktok.com/@{config.TIKTOK_USERNAME}/live"
        await alert_manager.send_live_alert(
            platform="tiktok",
            title=f"@{config.TIKTOK_USERNAME} is live on TikTok!",
            streamer=config.TIKTOK_USERNAME,
            url=room_url,
        )

    async def _on_disconnect(self, event: DisconnectEvent) -> None:
        log.info("Disconnected from TikTok LIVE")

    async def _on_live_end(self, event: LiveEndEvent) -> None:
        log.info("TikTok LIVE ended")

    async def _on_comment(self, event: CommentEvent) -> None:
        username = event.user.unique_id if event.user else "unknown"
        text = event.comment

        if text.startswith(config.COMMAND_PREFIX):
            parts = text[len(config.COMMAND_PREFIX):].split()
            if parts:
                ctx = cmd_feature.CommandContext(
                    platform="tiktok",
                    user=username,
                    channel=config.TIKTOK_USERNAME,
                    args=parts[1:],
                    raw_message=event,
                )
                response = await cmd_feature.registry.execute(parts[0], ctx)
                if response:
                    # TikTokLive read-only SDK — log reply for manual use.
                    log.info("[TikTok chat reply to %s] %s", username, response)

    async def _on_follow(self, event: FollowEvent) -> None:
        username = event.user.unique_id if event.user else "unknown"
        msg = welcome.tiktok_follower(username)
        log.info("[TikTok welcome] %s", msg)

    async def _on_subscribe(self, event: SubscribeEvent) -> None:
        username = event.user.unique_id if event.user else "unknown"
        msg = welcome.tiktok_subscriber(username)
        log.info("[TikTok sub welcome] %s", msg)


def create() -> TikTokBot:
    return TikTokBot()


async def run(bot: TikTokBot) -> None:
    await bot._client.start()
