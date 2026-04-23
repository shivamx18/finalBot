"""
cogs/streaks.py — Daily solving streaks and milestone badges.

Checks every day whether each verified user solved at least one CF problem.
Awards Discord roles for streak milestones: 7, 30, and 100 days.

Commands
--------
/mystreak       See your current and longest streak
/streakboard    Top 10 active streaks in the server
"""

import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.database import users_collection, guilds_collection
from config.settings import TZ_IST
from utils.cf_api import fetch_ac_submissions


# Streak milestone roles — created automatically if they don't exist
STREAK_MILESTONES = {
    7:   {"name": "7-Day Streak 🔥",   "color": 0xFF9500},
    30:  {"name": "30-Day Streak 💎",  "color": 0x00BFFF},
    100: {"name": "100-Day Streak 👑", "color": 0xFFD700},
}


async def _get_or_create_role(guild: discord.Guild, name: str, color: int) -> discord.Role:
    """Find a role by name or create it."""
    role = discord.utils.get(guild.roles, name=name)
    if not role:
        role = await guild.create_role(
            name=name,
            colour=discord.Colour(color),
            reason="Streak milestone role auto-created",
        )
    return role


def _calculate_streak(solved_dates: dict) -> tuple[int, int]:
    """
    Given a dict of {date: count}, calculate:
    - current_streak: consecutive days ending today (or yesterday)
    - longest_streak: all-time best
    """
    today   = datetime.date.today()
    streak  = 0
    current = 0
    longest = 0
    active  = False

    for i in range(730, -1, -1):  # look back 2 years
        date = today - datetime.timedelta(days=i)
        if solved_dates.get(date, 0) > 0:
            streak += 1
            longest = max(longest, streak)
            if i <= 1:  # today or yesterday
                active = True
                current = streak
        else:
            if not active:
                current = 0
            streak = 0

    return current, longest


class StreaksCog(commands.Cog, name="Streaks"):
    """Daily solving streaks with milestone role rewards."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=1, minute=0, tzinfo=TZ_IST))
    async def update_streaks(self) -> None:
        """Runs at 1am IST daily. Updates streaks for all verified users."""
        print("[Streaks] Updating streaks...")

        for user_doc in users_collection.find({"handle_verified": True}):
            discord_id = user_doc.get("discord_id")
            handle     = user_doc.get("cfid")
            guild_id   = user_doc.get("guild_id")
            if not discord_id or not handle or not guild_id:
                continue

            solved_dates = await fetch_ac_submissions(handle)
            if not solved_dates:
                continue

            current, longest = _calculate_streak(solved_dates)

            users_collection.update_one(
                {"discord_id": discord_id},
                {"$set": {
                    "current_streak": current,
                    "longest_streak": max(longest, user_doc.get("longest_streak", 0)),
                }},
            )

            # Assign milestone roles
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(int(discord_id))
            if not member:
                continue

            for days, info in STREAK_MILESTONES.items():
                role = await _get_or_create_role(guild, info["name"], info["color"])
                if current >= days and role not in member.roles:
                    await member.add_roles(role)
                    # Announce in celebration channel
                    guild_data = guilds_collection.find_one({"guild_id": guild_id})
                    channel_id = guild_data.get("cf_celebration_channel") if guild_data else None
                    if channel_id:
                        channel = guild.get_channel(channel_id)
                        if channel:
                            await channel.send(
                                f"🔥 {member.mention} just hit a **{days}-day solving streak** "
                                f"on Codeforces! Keep it up! 💪"
                            )
                elif current < days and role in member.roles:
                    # Streak broken — remove role
                    await member.remove_roles(role)

        print("[Streaks] Done.")

    # ── /mystreak ─────────────────────────────────────────────────────────────

    @app_commands.command(
        name="mystreak",
        description="See your current and longest CF solving streak",
    )
    async def my_streak(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user = users_collection.find_one({"discord_id": str(interaction.user.id)})
        if not user or "cfid" not in user:
            return await interaction.followup.send(
                "❌ You must be verified first. Use `/verify`.", ephemeral=True
            )

        # Fetch live streak data
        solved_dates = await fetch_ac_submissions(user["cfid"])
        if not solved_dates:
            return await interaction.followup.send(
                "⚠️ Could not fetch submission data.", ephemeral=True
            )

        current, longest = _calculate_streak(solved_dates)

        # Determine next milestone
        next_milestone = None
        for days in sorted(STREAK_MILESTONES.keys()):
            if current < days:
                next_milestone = days
                break

        embed = discord.Embed(
            title=f"🔥 {user['cfid']}'s Streak",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Current Streak",  value=f"`{current}` days",  inline=True)
        embed.add_field(name="Longest Streak",  value=f"`{longest}` days",  inline=True)
        if next_milestone:
            embed.add_field(
                name="Next Milestone",
                value=f"`{next_milestone - current}` days to **{next_milestone}-day** badge",
                inline=False,
            )
        else:
            embed.add_field(name="🏆 Status", value="All milestones unlocked!", inline=False)

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── /streakboard ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="streakboard",
        description="Top 10 active solving streaks in this server",
    )
    async def streak_board(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        users = list(
            users_collection
            .find({"guild_id": interaction.guild_id, "current_streak": {"$gt": 0}})
            .sort("current_streak", -1)
            .limit(10)
        )

        embed = discord.Embed(
            title="🔥 Solving Streak Leaderboard",
            description="Users with active daily solving streaks",
            color=discord.Color.orange(),
        )

        if not users:
            embed.description = "No active streaks yet. Start solving daily!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, u in enumerate(users):
                medal = medals[i] if i < 3 else f"#{i+1}"
                embed.add_field(
                    name=f"{medal} {u.get('cfid', 'Unknown')}",
                    value=f"🔥 {u['current_streak']} days (best: {u.get('longest_streak', u['current_streak'])})",
                    inline=False,
                )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StreaksCog(bot))
