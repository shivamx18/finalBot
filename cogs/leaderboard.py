"""
cogs/leaderboard.py — Weekly CF rating gain leaderboard.

Every Monday at 9am IST, posts the top 10 users who gained the most
rating in the past week to the configured leaderboard channel.

Commands
--------
/setleaderboardchannel  Admin: set the channel for weekly leaderboard posts
/weeklyleaderboard      View this week's leaderboard right now
"""

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.database import users_collection, guilds_collection
from config.settings import TZ_IST


def _snapshot_key() -> str:
    """Returns a key like 'snap_2025-18' (year-week) for storing snapshots."""
    now = datetime.datetime.now(TZ_IST)
    return f"snap_{now.year}-{now.isocalendar()[1]}"


def _last_week_key() -> str:
    last = datetime.datetime.now(TZ_IST) - datetime.timedelta(weeks=1)
    return f"snap_{last.year}-{last.isocalendar()[1]}"


class LeaderboardCog(commands.Cog, name="Leaderboard"):
    """Weekly rating-gain leaderboard posted every Monday."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Background tasks ──────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=8, minute=55, tzinfo=TZ_IST))
    async def snapshot_ratings(self) -> None:
        """Runs just before 9am IST daily. Saves current rating snapshot."""
        key = _snapshot_key()
        for user in users_collection.find({"handle_verified": True}):
            users_collection.update_one(
                {"discord_id": user["discord_id"]},
                {"$set": {f"rating_snapshots.{key}": user.get("rating", 0)}},
            )
        print(f"[Leaderboard] Saved rating snapshots for {key}.")

    @tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=TZ_IST))
    async def post_weekly_leaderboard(self) -> None:
        """Runs every day at 9am IST. On Mondays, posts the weekly leaderboard."""
        now = datetime.datetime.now(TZ_IST)
        if now.weekday() != 0:  # 0 = Monday
            return

        last_key = _last_week_key()
        gains    = []

        for user in users_collection.find({"handle_verified": True}):
            snapshots  = user.get("rating_snapshots", {})
            last_snap  = snapshots.get(last_key)
            current    = user.get("rating", 0)
            if last_snap is None:
                continue
            gain = current - last_snap
            if gain != 0:
                gains.append({
                    "cfid":       user.get("cfid", "Unknown"),
                    "discord_id": user.get("discord_id"),
                    "guild_id":   user.get("guild_id"),
                    "gain":       gain,
                    "rating":     current,
                })

        gains.sort(key=lambda x: x["gain"], reverse=True)

        # Post to each guild that has a leaderboard channel configured
        for guild_doc in guilds_collection.find({"leaderboard_channel": {"$exists": True}}):
            guild = self.bot.get_guild(guild_doc["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(guild_doc["leaderboard_channel"])
            if not channel:
                continue

            # Filter to this guild's users only
            guild_gains = [g for g in gains if g["guild_id"] == guild_doc["guild_id"]]

            embed = await self._build_embed(guild_gains, guild)
            await channel.send(embed=embed)

    async def _build_embed(self, gains: list, guild: discord.Guild) -> discord.Embed:
        """Build the leaderboard embed."""
        now = datetime.datetime.now(TZ_IST)
        embed = discord.Embed(
            title="📈 Weekly Rating Leaderboard",
            description=f"Week ending {now.strftime('%d %b %Y')}",
            color=discord.Color.gold(),
        )

        medals = ["🥇", "🥈", "🥉"]
        top    = gains[:10]

        if not top:
            embed.description = "No rating changes recorded this week."
            return embed

        for i, entry in enumerate(top):
            medal = medals[i] if i < 3 else f"#{i+1}"
            sign  = "+" if entry["gain"] > 0 else ""
            embed.add_field(
                name=f"{medal} {entry['cfid']}",
                value=f"Rating: **{entry['rating']}** ({sign}{entry['gain']})",
                inline=False,
            )

        embed.set_footer(text="Rankings based on rating change from last Monday to today.")
        return embed

    # ── /setleaderboardchannel ────────────────────────────────────────────────

    @app_commands.command(
        name="setleaderboardchannel",
        description="Admin only: Set the channel for weekly leaderboard posts",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def set_leaderboard_channel(self, interaction: discord.Interaction) -> None:
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"leaderboard_channel": interaction.channel_id}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Weekly leaderboard will be posted in {interaction.channel.mention} every Monday.",
            ephemeral=True,
        )

    # ── /weeklyleaderboard ────────────────────────────────────────────────────

    @app_commands.command(
        name="weeklyleaderboard",
        description="View this week's CF rating gain leaderboard",
    )
    async def weekly_leaderboard(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        last_key = _last_week_key()
        gains    = []

        for user in users_collection.find({"guild_id": interaction.guild_id, "handle_verified": True}):
            snapshots = user.get("rating_snapshots", {})
            last_snap = snapshots.get(last_key)
            current   = user.get("rating", 0)
            if last_snap is None:
                continue
            gain = current - last_snap
            gains.append({
                "cfid":       user.get("cfid", "Unknown"),
                "discord_id": user.get("discord_id"),
                "guild_id":   user.get("guild_id"),
                "gain":       gain,
                "rating":     current,
            })

        gains.sort(key=lambda x: x["gain"], reverse=True)
        embed = await self._build_embed(gains, interaction.guild)
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeaderboardCog(bot))
