"""Shared command registry used by all platform bots."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
import config

# Normalized context passed to every command handler.
@dataclass
class CommandContext:
    platform: str          # "discord" | "twitch" | "youtube" | "tiktok"
    user: str              # display name of the sender
    channel: str           # channel / room name
    args: list[str] = field(default_factory=list)
    raw_message: Any = None  # original platform message object

CommandHandler = Callable[[CommandContext], Awaitable[str | None]]


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandHandler] = {}
        self._register_defaults()

    def register(self, name: str, handler: CommandHandler) -> None:
        self._commands[name.lower()] = handler

    async def execute(self, name: str, ctx: CommandContext) -> str | None:
        handler = self._commands.get(name.lower())
        if handler is None:
            return None
        return await handler(ctx)

    def names(self) -> list[str]:
        return sorted(self._commands.keys())

    # ── built-in commands ─────────────────────────────────────────────────────

    def _register_defaults(self) -> None:
        self.register("commands", self._cmd_commands)
        self.register("socials", self._cmd_socials)
        self.register("discord", self._cmd_discord)
        self.register("twitch", self._cmd_twitch)
        self.register("youtube", self._cmd_youtube)
        self.register("tiktok", self._cmd_tiktok)
        self.register("so", self._cmd_so)
        self.register("lurk", self._cmd_lurk)
        self.register("schedule", self._cmd_schedule)

    async def _cmd_commands(self, ctx: CommandContext) -> str:
        names = " | ".join(f"{config.COMMAND_PREFIX}{n}" for n in self.names())
        return f"Available commands: {names}"

    async def _cmd_socials(self, ctx: CommandContext) -> str:
        parts = []
        if config.SOCIAL_DISCORD:
            parts.append(f"Discord: {config.SOCIAL_DISCORD}")
        if config.SOCIAL_TWITCH:
            parts.append(f"Twitch: {config.SOCIAL_TWITCH}")
        if config.SOCIAL_YOUTUBE:
            parts.append(f"YouTube: {config.SOCIAL_YOUTUBE}")
        if config.SOCIAL_TIKTOK:
            parts.append(f"TikTok: {config.SOCIAL_TIKTOK}")
        return " | ".join(parts) if parts else "No social links configured."

    async def _cmd_discord(self, _ctx: CommandContext) -> str:
        link = config.SOCIAL_DISCORD or "No Discord link configured."
        return f"Join the Discord community: {link}"

    async def _cmd_twitch(self, _ctx: CommandContext) -> str:
        link = config.SOCIAL_TWITCH or "No Twitch link configured."
        return f"Watch live on Twitch: {link}"

    async def _cmd_youtube(self, _ctx: CommandContext) -> str:
        link = config.SOCIAL_YOUTUBE or "No YouTube link configured."
        return f"Subscribe on YouTube: {link}"

    async def _cmd_tiktok(self, _ctx: CommandContext) -> str:
        link = config.SOCIAL_TIKTOK or "No TikTok link configured."
        return f"Follow on TikTok: {link}"

    async def _cmd_so(self, ctx: CommandContext) -> str:
        target = ctx.args[0].lstrip("@") if ctx.args else "someone"
        return f"Shoutout to @{target}! Go check them out!"

    async def _cmd_lurk(self, ctx: CommandContext) -> str:
        return f"Thanks for the lurk, {ctx.user}! We see you PogChamp"

    async def _cmd_schedule(self, ctx: CommandContext) -> str:
        return (
            "Stream schedule: "
            "Mon/Wed/Fri @ 7 PM ET | "
            "Sat @ 2 PM ET — "
            f"Follow on Twitch so you never miss it: {config.SOCIAL_TWITCH}"
        )


# Single shared instance used by all bots.
registry = CommandRegistry()
