"""Cross-platform go-live alert manager.

Platform bots call AlertManager.send_live_alert() when a stream starts.
The alert is posted as a Discord embed in the configured alerts channel.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
import discord
from utils.logger import get_logger
import config

if TYPE_CHECKING:
    from bots.discord_bot import DiscordBot

log = get_logger("alerts")

_PLATFORM_COLORS = {
    "twitch": 0x9146FF,
    "youtube": 0xFF0000,
    "tiktok": 0x010101,
}

_PLATFORM_EMOJIS = {
    "twitch": "🟣",
    "youtube": "🔴",
    "tiktok": "🎵",
}


class AlertManager:
    def __init__(self) -> None:
        self._discord_bot: "DiscordBot | None" = None

    def set_discord_bot(self, bot: "DiscordBot") -> None:
        self._discord_bot = bot

    async def send_live_alert(
        self,
        platform: str,
        title: str,
        streamer: str,
        url: str,
        game: str = "",
        thumbnail_url: str = "",
    ) -> None:
        if self._discord_bot is None:
            log.warning("AlertManager: Discord bot not set — skipping alert")
            return

        channel = self._discord_bot.get_channel(config.DISCORD_ALERTS_CHANNEL_ID)
        if channel is None:
            log.warning("AlertManager: alerts channel %d not found", config.DISCORD_ALERTS_CHANNEL_ID)
            return

        emoji = _PLATFORM_EMOJIS.get(platform.lower(), "🔴")
        color = _PLATFORM_COLORS.get(platform.lower(), 0xFF0000)

        embed = discord.Embed(
            title=f"{emoji} {streamer} is live on {platform.title()}!",
            description=title,
            url=url,
            color=color,
        )
        if game:
            embed.add_field(name="Playing", value=game, inline=True)
        embed.add_field(name="Watch now", value=f"[Click here]({url})", inline=True)
        if thumbnail_url:
            embed.set_image(url=thumbnail_url)
        embed.set_footer(text=f"Stream alert • {platform.title()}")

        try:
            await channel.send(
                content=f"@here {emoji} **{streamer}** just went live!",
                embed=embed,
            )
            log.info("Sent live alert for %s on %s", streamer, platform)
        except discord.DiscordException as exc:
            log.error("Failed to send alert: %s", exc)


# Singleton shared across all bots.
alert_manager = AlertManager()
