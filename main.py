"""Entry point — starts all platform bots concurrently."""
import asyncio
import logging

from utils.logger import get_logger

log = get_logger("main")
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("twitchio").setLevel(logging.WARNING)


async def main() -> None:
    from bots import discord_bot, twitch_bot, youtube_bot, tiktok_bot

    discord = discord_bot.create()
    twitch = twitch_bot.create()
    youtube = youtube_bot.create()
    tiktok = tiktok_bot.create()

    log.info("Starting all platform bots…")

    await asyncio.gather(
        discord_bot.run(discord),
        twitch_bot.run(twitch),
        youtube_bot.run(youtube),
        tiktok_bot.run(tiktok),
        return_exceptions=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
