"""Discord bot — welcome, moderation, commands, and cross-platform alert receiver."""
from __future__ import annotations

import discord
from discord.ext import commands

import config
from features import commands as cmd_feature
from features import moderation, welcome
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("discord")

_INTENTS = discord.Intents.default()
_INTENTS.message_content = True
_INTENTS.members = True


class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=_INTENTS)
        alert_manager.set_discord_bot(self)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def on_ready(self) -> None:
        log.info("Discord bot ready as %s", self.user)

    async def on_member_join(self, member: discord.Member) -> None:
        channel = self.get_channel(config.DISCORD_WELCOME_CHANNEL_ID)
        if channel:
            await channel.send(welcome.discord_member(member.display_name))
        log.info("Welcomed Discord member: %s", member.display_name)

    # ── messages ──────────────────────────────────────────────────────────────

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Moderation
        result = moderation.check(message.content, message.author.name)
        if result.should_remove:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} Your message was removed: {result.reason}.",
                    delete_after=8,
                )
                await self._log_mod_action(message.author, message.content, result.reason)
            except discord.Forbidden:
                log.warning("Missing permissions to delete message in %s", message.channel)
            return

        # Commands
        if message.content.startswith(config.COMMAND_PREFIX):
            parts = message.content[len(config.COMMAND_PREFIX):].split()
            if parts:
                ctx = cmd_feature.CommandContext(
                    platform="discord",
                    user=message.author.display_name,
                    channel=str(message.channel),
                    args=parts[1:],
                    raw_message=message,
                )
                response = await cmd_feature.registry.execute(parts[0], ctx)
                if response:
                    await message.channel.send(response)
                    return

        await self.process_commands(message)

    # ── helpers ───────────────────────────────────────────────────────────────

    async def _log_mod_action(
        self, member: discord.Member, content: str, reason: str
    ) -> None:
        if not config.DISCORD_LOG_CHANNEL_ID:
            return
        channel = self.get_channel(config.DISCORD_LOG_CHANNEL_ID)
        if channel is None:
            return
        embed = discord.Embed(title="Message Removed", color=0xFF6600)
        embed.add_field(name="User", value=str(member), inline=True)
        embed.add_field(name="Reason", value=reason, inline=True)
        embed.add_field(name="Content", value=content[:1024], inline=False)
        await channel.send(embed=embed)


def create() -> DiscordBot:
    return DiscordBot()


async def run(bot: DiscordBot) -> None:
    await bot.start(config.DISCORD_TOKEN)
