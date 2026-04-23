"""
cogs/broadcast.py — Broadcast announcements to all guild mod channels.

Commands
--------
/announce   Admin only: send a message to every guild's mod channel
"""

import datetime

import discord
from discord import app_commands
from discord.ext import commands

from config.database import guilds_collection


class BroadcastCog(commands.Cog, name="Broadcast"):
    """Send announcements to every server the bot is in."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="announce",
        description="Admin only: Broadcast a message to all guild mod channels",
    )
    @app_commands.describe(
        title="Announcement title",
        message="Announcement body",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        title: str,
        message: str,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        embed = discord.Embed(
            title=f"📢 {title}",
            description=message,
            color=discord.Color.blurple(),
        )
        embed.set_footer(
            text=f"Sent by {interaction.user.display_name} • {interaction.guild.name}",
        )
        embed.timestamp = datetime.datetime.now(datetime.UTC)

        sent    = 0
        failed  = 0

        for guild_doc in guilds_collection.find({"mod_channel": {"$exists": True}}):
            guild = self.bot.get_guild(guild_doc["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(guild_doc["mod_channel"])
            if not channel:
                continue
            try:
                await channel.send(embed=embed)
                sent += 1
            except Exception as e:
                print(f"[Broadcast] Failed to send to {guild.name}: {e}")
                failed += 1

        await interaction.followup.send(
            f"✅ Announcement sent to `{sent}` guilds. Failed: `{failed}`.",
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(BroadcastCog(bot))
