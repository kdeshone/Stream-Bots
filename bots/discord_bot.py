"""Discord bot — welcome, moderation, mod commands, and cross-platform alert receiver."""
from __future__ import annotations

import datetime

import discord
from discord.ext import commands

import config
from features import commands as cmd_feature
from features import moderation, welcome
from features.moderation import strike_tracker
from features.alerts import alert_manager
from utils.logger import get_logger

log = get_logger("discord")

_INTENTS = discord.Intents.default()
_INTENTS.message_content = True
_INTENTS.members = True

_DEFAULT_TIMEOUT_MINUTES = 10

# Mod commands only usable by members with Manage Messages or Administrator.
_MOD_COMMANDS = {"warn", "timeout", "kick", "ban", "unban", "pardon"}


class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(command_prefix=config.COMMAND_PREFIX, intents=_INTENTS)
        alert_manager.set_discord_bot(self)
        self._seen_chatters: set[int] = set()   # member IDs seen in chat this session

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

        # First-time chatter welcome
        if message.author.id not in self._seen_chatters:
            self._seen_chatters.add(message.author.id)
            await message.channel.send(
                f"Welcome to the chat, {message.author.mention}! Glad you're here!"
            )

        # Auto-moderation with strike escalation
        result = moderation.check(message.content, message.author.name)
        if result.should_remove:
            await self._handle_auto_mod(message, result.reason)
            return

        # Commands
        if message.content.startswith(config.COMMAND_PREFIX):
            parts = message.content[len(config.COMMAND_PREFIX):].split()
            if parts:
                cmd_name = parts[0].lower()

                # Mod commands — check permissions first
                if cmd_name in _MOD_COMMANDS:
                    if not self._is_mod(message.author):
                        await message.channel.send(
                            f"{message.author.mention} You don't have permission to use that command.",
                            delete_after=6,
                        )
                        return
                    await self._handle_mod_command(cmd_name, parts[1:], message)
                    return

                ctx = cmd_feature.CommandContext(
                    platform="discord",
                    user=message.author.display_name,
                    channel=str(message.channel),
                    args=parts[1:],
                    raw_message=message,
                )
                response = await cmd_feature.registry.execute(cmd_name, ctx)
                if response:
                    await message.channel.send(response)
                    return

        await self.process_commands(message)

    # ── mod command dispatch ──────────────────────────────────────────────────

    async def _handle_mod_command(
        self, cmd: str, args: list[str], message: discord.Message
    ) -> None:
        guild = message.guild
        if guild is None:
            return

        target_member = self._resolve_member(args, message)

        if cmd == "pardon":
            if not target_member:
                await message.channel.send("Usage: `!pardon @user`")
                return
            strike_tracker.clear("discord", target_member.name)
            await message.channel.send(f"Strikes cleared for {target_member.mention}.")
            return

        if cmd == "unban":
            name = args[0].lstrip("@") if args else None
            if not name:
                await message.channel.send("Usage: `!unban username`")
                return
            async for ban_entry in guild.bans():
                if ban_entry.user.name.lower() == name.lower():
                    await guild.unban(ban_entry.user)
                    await message.channel.send(f"Unbanned **{ban_entry.user}**.")
                    return
            await message.channel.send(f"No ban found for **{name}**.")
            return

        if not target_member:
            await message.channel.send("Could not find that user. Mention them or use their username.")
            return

        reason = " ".join(args[1:]) if len(args) > 1 else "No reason given"

        if cmd == "warn":
            await self._warn_member(target_member, message.channel, reason)

        elif cmd == "timeout":
            minutes = int(args[1]) if len(args) > 1 and args[1].isdigit() else _DEFAULT_TIMEOUT_MINUTES
            reason_text = " ".join(args[2:]) if len(args) > 2 else "No reason given"
            await self._timeout_member(target_member, message.channel, minutes, reason_text)

        elif cmd == "kick":
            try:
                await target_member.kick(reason=reason)
                await message.channel.send(f"Kicked {target_member.mention}. Reason: {reason}")
                await self._log_mod_action(message.author, target_member, "kick", reason)
            except discord.Forbidden:
                await message.channel.send("I don't have permission to kick that member.")

        elif cmd == "ban":
            try:
                await target_member.ban(reason=reason, delete_message_days=1)
                await message.channel.send(f"Banned {target_member.mention}. Reason: {reason}")
                await self._log_mod_action(message.author, target_member, "ban", reason)
            except discord.Forbidden:
                await message.channel.send("I don't have permission to ban that member.")

    async def _warn_member(
        self, member: discord.Member, channel: discord.TextChannel, reason: str
    ) -> None:
        action = strike_tracker.record("discord", member.name)
        strikes = strike_tracker.count("discord", member.name)
        await channel.send(
            f"{member.mention} Warning ({strikes} strike(s)): {reason}"
        )
        try:
            await member.send(
                f"You received a warning in **{channel.guild.name}**: {reason}\n"
                f"Strike count: {strikes}"
            )
        except discord.Forbidden:
            pass  # DMs closed

        if action == "timeout":
            await self._timeout_member(member, channel, _DEFAULT_TIMEOUT_MINUTES, reason)
        elif action == "ban":
            await member.ban(reason=f"Auto-ban after {strikes} strikes: {reason}")
            await channel.send(f"{member.mention} has been banned after {strikes} strikes.")

        await self._log_mod_action(None, member, f"warn ({action})", reason)

    async def _timeout_member(
        self,
        member: discord.Member,
        channel: discord.TextChannel,
        minutes: int,
        reason: str,
    ) -> None:
        duration = datetime.timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=reason)
            await channel.send(
                f"{member.mention} has been timed out for {minutes} minute(s). Reason: {reason}"
            )
            await self._log_mod_action(None, member, f"timeout {minutes}m", reason)
        except discord.Forbidden:
            await channel.send("I don't have permission to timeout that member.")

    # ── auto-mod with escalation ──────────────────────────────────────────────

    async def _handle_auto_mod(self, message: discord.Message, reason: str) -> None:
        try:
            await message.delete()
        except discord.Forbidden:
            log.warning("Cannot delete message in %s", message.channel)
            return

        member = message.author
        action = strike_tracker.record("discord", member.name)
        strikes = strike_tracker.count("discord", member.name)

        if action == "warn":
            await message.channel.send(
                f"{member.mention} Your message was removed ({reason}). Strike 1 — further violations will result in a timeout.",
                delete_after=10,
            )
        elif action == "timeout":
            await message.channel.send(
                f"{member.mention} Timed out for {_DEFAULT_TIMEOUT_MINUTES} minutes ({reason}). Strike {strikes}.",
                delete_after=10,
            )
            await self._timeout_member(member, message.channel, _DEFAULT_TIMEOUT_MINUTES, reason)
        elif action == "ban":
            await message.channel.send(
                f"{member.mention} has been banned after {strikes} violations.",
                delete_after=10,
            )
            try:
                await member.ban(reason=f"Auto-ban after {strikes} violations: {reason}")
            except discord.Forbidden:
                log.warning("Cannot ban %s", member)

        await self._log_mod_action(None, member, f"auto-mod ({action})", reason)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _is_mod(self, member: discord.Member) -> bool:
        if member.name.lower() in config.TRUSTED_USERS:
            return True
        return member.guild_permissions.manage_messages or member.guild_permissions.administrator

    def _resolve_member(
        self, args: list[str], message: discord.Message
    ) -> discord.Member | None:
        if message.mentions:
            return message.mentions[0]
        if args:
            name = args[0].lstrip("@").lower()
            for m in message.guild.members:
                if m.name.lower() == name or m.display_name.lower() == name:
                    return m
        return None

    async def _log_mod_action(
        self,
        moderator: discord.Member | None,
        target: discord.Member,
        action: str,
        reason: str,
    ) -> None:
        if not config.DISCORD_LOG_CHANNEL_ID:
            return
        channel = self.get_channel(config.DISCORD_LOG_CHANNEL_ID)
        if channel is None:
            return
        embed = discord.Embed(title=f"Mod Action: {action}", color=0xFF6600)
        if moderator:
            embed.add_field(name="Moderator", value=str(moderator), inline=True)
        embed.add_field(name="Target", value=str(target), inline=True)
        embed.add_field(name="Action", value=action, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(
            name="Strikes",
            value=str(strike_tracker.count("discord", target.name)),
            inline=True,
        )
        await channel.send(embed=embed)


def create() -> DiscordBot:
    return DiscordBot()


async def run(bot: DiscordBot) -> None:
    await bot.start(config.DISCORD_TOKEN)
