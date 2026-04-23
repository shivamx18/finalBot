"""
cogs/community.py — Community engagement commands.

Commands
--------
/thank          Publicly thank a server member with an embed
/suggestions    Send feedback or bug reports to the mod team
"""

import datetime
import random

import discord
from discord import app_commands
from discord.ext import commands

from config.database import guilds_collection, users_collection


# ── Positivity quotes for /thank ─────────────────────────────────────────────
THANK_QUOTES = [
    "Kindness is free, sprinkle that stuff everywhere.",
    "One kind word can change someone's entire day.",
    "Gratitude turns what we have into enough.",
    "Appreciation is a wonderful thing. It makes what is excellent in others belong to us as well.",
    "Every act of kindness creates a ripple with no logical end.",
]


class CommunityCog(commands.Cog, name="Community"):
    """Community features: thanking members and submitting suggestions."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /thank ────────────────────────────────────────────────────────────────

    @app_commands.command(
        name="thank",
        description="Publicly thank someone for helping you",
    )
    @app_commands.describe(
        user="The helpful person you want to thank",
        reason="Why are you thanking them?",
    )
    async def thank(
        self, interaction: discord.Interaction, user: discord.User, reason: str
    ) -> None:
        if user.id == interaction.user.id:
            return await interaction.response.send_message(
                "❌ You can't thank yourself!", ephemeral=True
            )

        # Increment thanks counter in DB
        users_collection.update_one(
            {"discord_id": str(user.id)},
            {"$inc": {"thanks": 1}},
            upsert=True,
        )

        embed = discord.Embed(
            title="💛 Heartfelt Thanks!",
            description=(
                f"**{user.mention}** has been thanked by **{interaction.user.mention}**!\n\n"
                f"**Why?**\n> *{reason}*"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=user.display_avatar.url if user.avatar else None)
        embed.set_footer(text=f"✨ {random.choice(THANK_QUOTES)}")

        await interaction.response.send_message(embed=embed)

    # ── /suggestions ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="suggestions",
        description="Send feedback or report bugs to the mod team",
    )
    @app_commands.describe(message="Your feedback, suggestion, or bug report")
    async def suggestions(
        self, interaction: discord.Interaction, message: str
    ) -> None:
        config         = guilds_collection.find_one({"guild_id": interaction.guild_id})
        mod_channel_id = config.get("mod_channel") if config else None

        if not mod_channel_id:
            return await interaction.response.send_message(
                "❌ No mod channel is configured on this server.", ephemeral=True
            )

        mod_channel = interaction.guild.get_channel(mod_channel_id)
        if not mod_channel:
            return await interaction.response.send_message(
                "❌ The configured mod channel was not found.", ephemeral=True
            )

        embed = discord.Embed(
            title="📬 New Feedback",
            description=message,
            color=discord.Color.blurple(),
        )
        embed.set_author(
            name=interaction.user.display_name,
            icon_url=interaction.user.display_avatar.url,
        )
        embed.timestamp = datetime.datetime.now(datetime.UTC)

        await mod_channel.send(embed=embed)
        await interaction.response.send_message(
            "✅ Your suggestion has been sent to the moderators!", ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CommunityCog(bot))
