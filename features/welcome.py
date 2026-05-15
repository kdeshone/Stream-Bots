"""Welcome message templates for new followers/members across platforms."""
from __future__ import annotations

import config


def discord_member(username: str) -> str:
    return (
        f"Welcome to the community, **{username}**! "
        f"Check out our socials and say hi: {config.SOCIAL_DISCORD}"
    )


def twitch_follower(username: str) -> str:
    return f"Welcome {username}! Thanks for the follow — stick around and enjoy the stream! <3"


def twitch_subscriber(username: str, months: int = 1) -> str:
    if months > 1:
        return f"HUGE shoutout to {username} for {months} months of sub love! PogChamp"
    return f"Welcome to the sub club, {username}! Thank you so much for the support! <3"


def youtube_member(username: str) -> str:
    return f"Welcome {username}! Thanks for joining — glad you're here!"


def tiktok_follower(username: str) -> str:
    return f"Welcome {username}! Thanks for the follow on TikTok!"


def tiktok_subscriber(username: str) -> str:
    return f"Thank you {username} for subscribing! You're amazing!"
