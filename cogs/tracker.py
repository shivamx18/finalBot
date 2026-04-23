"""
cogs/tracker.py — Automatic CF rating & rank role updater.

Runs every 24 hours. For every verified user, fetches their current
rating from the CF API and updates their Discord rank role if it changed.
Users never need to re-run /verify just to get a new role.

Commands
--------
/forceupdate    Admin: trigger an immediate update for all users
/mystats        Show your current CF rating and rank stored in the DB
"""

import asyncio
import datetime
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.database import users_collection, guilds_collection
from utils.discord_helpers import assign_cf_rank_role
from utils.cf_api import is_rank_up


RANK_UP_QUOTES = [
    "Hard work beats talent when talent doesn't work hard.",
    "Keep grinding — the rating will follow. 🚀",
    "Your growth is showing. Keep pushing! 💪",
    "Small steps each day lead to big achievements!",
]


async def _fetch_cf_info(handle: str) -> Optional[dict]:
    """Fetch user info from CF API. Returns None on failure."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://codeforces.com/api/user.info?handles={handle}",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        if data["status"] == "OK":
            return data["result"][0]
    except Exception as e:
        print(f"[Tracker] Failed to fetch {handle}: {e}")
    return None


class TrackerCog(commands.Cog, name="Tracker"):
    """Auto-updates CF rank roles every 24 hours."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(hours=24)
    async def update_ratings(self) -> None:
        """Runs every 24h. Updates rank roles for all verified users."""
        print("[Tracker] Starting daily rating update...")
        updated = 0
        ranked_up = 0

        all_users = list(users_collection.find({"handle_verified": True}))

        for user_doc in all_users:
            discord_id = user_doc.get("discord_id")
            handle     = user_doc.get("cfid")
            guild_id   = user_doc.get("guild_id")

            if not discord_id or not handle or not guild_id:
                continue

            # Fetch latest CF data
            info = await _fetch_cf_info(handle)
            if not info:
                continue

            new_rank   = info.get("rank", "newbie").lower()
            new_rating = info.get("rating", 0)
            old_rank   = user_doc.get("rank", "newbie")
            old_rating = user_doc.get("rating", 0)

            # Only update if something changed
            if new_rank == old_rank and new_rating == old_rating:
                await asyncio.sleep(0.5)  # rate limit protection
                continue

            # Update DB
            users_collection.update_one(
                {"discord_id": discord_id},
                {"$set": {"rank": new_rank, "rating": new_rating}},
            )
            updated += 1

            # Update Discord role
            guild = self.bot.get_guild(guild_id)
            if not guild:
                await asyncio.sleep(0.5)
                continue

            member = guild.get_member(int(discord_id))
            if not member:
                await asyncio.sleep(0.5)
                continue

            await assign_cf_rank_role(member, guild, new_rank)

            # Send rank-up celebration if applicable
            if is_rank_up(new_rank, old_rank):
                ranked_up += 1
                guild_data = guilds_collection.find_one({"guild_id": guild_id})
                channel_id = guild_data.get("cf_celebration_channel") if guild_data else None
                if channel_id:
                    channel = guild.get_channel(channel_id)
                    if channel:
                        from random import choice
                        embed = discord.Embed(
                            title="🎉 Rank Up!",
                            description=f"{member.mention} just ranked up on Codeforces!",
                            color=discord.Color.gold(),
                        )
                        embed.add_field(name="📉 Before", value=old_rank.title(),  inline=True)
                        embed.add_field(name="📈 Now",    value=new_rank.title(),  inline=True)
                        embed.add_field(name="📊 Rating", value=str(new_rating),   inline=True)
                        embed.set_footer(text=choice(RANK_UP_QUOTES))
                        await channel.send(embed=embed)

            await asyncio.sleep(0.5)  # stay within CF API rate limits

        print(f"[Tracker] Done. {updated} users updated, {ranked_up} ranked up.")

    # ── /forceupdate ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="forceupdate",
        description="Admin only: Force an immediate rating update for all users",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def force_update(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(
            "🔄 Starting rating update for all users... This may take a minute.",
            ephemeral=True,
        )
        await self.update_ratings()
        await interaction.followup.send("✅ Rating update complete!", ephemeral=True)

    # ── /mystats ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="mystats",
        description="Check your current CF rating and rank",
    )
    async def my_stats(self, interaction: discord.Interaction) -> None:
        user = users_collection.find_one({"discord_id": str(interaction.user.id)})
        if not user or "cfid" not in user:
            return await interaction.response.send_message(
                "❌ You are not verified. Use `/verify` first.", ephemeral=True
            )

        embed = discord.Embed(
            title=f"{user['cfid']}'s Stats",
            color=discord.Color.blue(),
        )
        embed.add_field(name="🏅 Rank",   value=user.get("rank", "unrated").title(), inline=True)
        embed.add_field(name="📊 Rating", value=str(user.get("rating", 0)),          inline=True)
        embed.add_field(
            name="🔗 Profile",
            value=f"[View on Codeforces](https://codeforces.com/profile/{user['cfid']})",
            inline=False,
        )
        embed.set_footer(text="Ratings auto-update every 24h. Use /forceupdate to refresh now.")
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TrackerCog(bot))
