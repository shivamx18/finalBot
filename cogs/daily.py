"""
cogs/daily.py — Daily CF challenge posted at 9am IST.

Admin sets a rating range and the bot picks a random problem every day.
Users can claim it as solved. No POTD complexity — just one problem a day.

Commands
--------
/setdailychannel    Admin: set channel + role for daily challenge
/setdailyrating     Admin: set the rating range for daily problems (default 1200-1600)
/todayschallenge    View today's problem
/claimdaily         Mark today's problem as solved
/dailystats         See who solved today's challenge
"""

import datetime
import random
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands, tasks

from config.database import guilds_collection, users_collection
from config.settings import TZ_IST


async def _pick_daily_problem(min_r: int, max_r: int) -> Optional[dict]:
    """Fetch a random CF problem within the rating range."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://codeforces.com/api/problemset.problems",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
        problems = [
            p for p in data["result"]["problems"]
            if "rating" in p
            and min_r <= p["rating"] <= max_r
            and "contestId" in p
        ]
        return random.choice(problems) if problems else None
    except Exception as e:
        print(f"[Daily] Failed to fetch problem: {e}")
        return None


def _today_key() -> str:
    return datetime.datetime.now(TZ_IST).strftime("%Y-%m-%d")


class DailyCog(commands.Cog, name="Daily"):
    """Posts one CF challenge problem every day at 9am IST."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Background task ───────────────────────────────────────────────────────

    @tasks.loop(time=datetime.time(hour=9, minute=0, tzinfo=TZ_IST))
    async def post_daily(self) -> None:
        """Posts the daily challenge to all configured guilds."""
        today = _today_key()

        for guild_doc in guilds_collection.find({"daily_channel": {"$exists": True}}):
            guild = self.bot.get_guild(guild_doc["guild_id"])
            if not guild:
                continue

            channel = guild.get_channel(guild_doc["daily_channel"])
            role    = guild.get_role(guild_doc.get("daily_role"))
            if not channel:
                continue

            min_r = guild_doc.get("daily_min_rating", 1200)
            max_r = guild_doc.get("daily_max_rating", 1600)

            problem = await _pick_daily_problem(min_r, max_r)
            if not problem:
                continue

            url = (
                f"https://codeforces.com/problemset/problem/"
                f"{problem['contestId']}/{problem['index']}"
            )

            # Save today's problem for this guild
            guilds_collection.update_one(
                {"guild_id": guild_doc["guild_id"]},
                {"$set": {f"daily_problems.{today}": {
                    "name":       problem["name"],
                    "url":        url,
                    "rating":     problem["rating"],
                    "tags":       problem.get("tags", []),
                    "claims":     [],
                }}},
            )

            tag_str = ", ".join(problem.get("tags", [])[:3])
            embed = discord.Embed(
                title=f"☀️ Daily Challenge — {datetime.datetime.now(TZ_IST).strftime('%d %b %Y')}",
                description=f"**[{problem['name']}]({url})**",
                color=discord.Color.orange(),
            )
            embed.add_field(name="⭐ Rating", value=str(problem["rating"]), inline=True)
            embed.add_field(name="🏷️ Tags",   value=tag_str or "N/A",       inline=True)
            embed.set_footer(text="Solve it and use /claimdaily to mark it done!")

            mention = role.mention if role else ""
            await channel.send(content=mention, embed=embed,
                                allowed_mentions=discord.AllowedMentions(roles=True))

    # ── /setdailychannel ──────────────────────────────────────────────────────

    @app_commands.command(
        name="setdailychannel",
        description="Admin only: Set channel and role for daily CF challenge",
    )
    @app_commands.describe(channel="Channel to post daily problem", role="Role to mention (optional)")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_daily_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: Optional[discord.Role] = None,
    ) -> None:
        update = {"daily_channel": channel.id}
        if role:
            update["daily_role"] = role.id
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": update},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Daily challenge will post in {channel.mention} at 9am IST.", ephemeral=True
        )

    # ── /setdailyrating ───────────────────────────────────────────────────────

    @app_commands.command(
        name="setdailyrating",
        description="Admin only: Set the rating range for daily problems",
    )
    @app_commands.describe(min_rating="Minimum rating", max_rating="Maximum rating")
    @app_commands.checks.has_permissions(administrator=True)
    async def set_daily_rating(
        self,
        interaction: discord.Interaction,
        min_rating: int = 1200,
        max_rating: int = 1600,
    ) -> None:
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": {"daily_min_rating": min_rating, "daily_max_rating": max_rating}},
            upsert=True,
        )
        await interaction.response.send_message(
            f"✅ Daily rating range set to `{min_rating}–{max_rating}`.", ephemeral=True
        )

    # ── /todayschallenge ──────────────────────────────────────────────────────

    @app_commands.command(
        name="todayschallenge",
        description="View today's daily CF challenge",
    )
    async def todays_challenge(self, interaction: discord.Interaction) -> None:
        today     = _today_key()
        guild_doc = guilds_collection.find_one({"guild_id": interaction.guild_id})
        problem   = guild_doc.get("daily_problems", {}).get(today) if guild_doc else None

        if not problem:
            return await interaction.response.send_message(
                "❌ No daily challenge set yet today. Check back later!", ephemeral=True
            )

        claims  = problem.get("claims", [])
        tag_str = ", ".join(problem.get("tags", [])[:3])

        embed = discord.Embed(
            title=f"☀️ Today's Challenge — {today}",
            description=f"**[{problem['name']}]({problem['url']})**",
            color=discord.Color.orange(),
        )
        embed.add_field(name="⭐ Rating",  value=str(problem["rating"]), inline=True)
        embed.add_field(name="🏷️ Tags",    value=tag_str or "N/A",       inline=True)
        embed.add_field(name="✅ Claimed", value=str(len(claims)),        inline=True)
        await interaction.response.send_message(embed=embed)

    # ── /claimdaily ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="claimdaily",
        description="Mark today's daily challenge as solved",
    )
    async def claim_daily(self, interaction: discord.Interaction) -> None:
        today   = _today_key()
        user_id = str(interaction.user.id)

        guild_doc = guilds_collection.find_one({"guild_id": interaction.guild_id})
        problem   = guild_doc.get("daily_problems", {}).get(today) if guild_doc else None

        if not problem:
            return await interaction.response.send_message(
                "❌ No daily challenge posted yet today.", ephemeral=True
            )

        if user_id in problem.get("claims", []):
            return await interaction.response.send_message(
                "✅ You already claimed today's challenge!", ephemeral=True
            )

        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$addToSet": {f"daily_problems.{today}.claims": user_id}},
        )
        await interaction.response.send_message(
            "🎉 Marked as solved! Great work!", ephemeral=True
        )

    # ── /dailystats ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="dailystats",
        description="See how many people solved today's challenge",
    )
    async def daily_stats(self, interaction: discord.Interaction) -> None:
        today     = _today_key()
        guild_doc = guilds_collection.find_one({"guild_id": interaction.guild_id})
        problem   = guild_doc.get("daily_problems", {}).get(today) if guild_doc else None

        if not problem:
            return await interaction.response.send_message(
                "❌ No challenge posted today.", ephemeral=True
            )

        claims = problem.get("claims", [])
        embed = discord.Embed(
            title=f"📊 Daily Challenge Stats — {today}",
            description=f"**{problem['name']}** | Rating: `{problem['rating']}`",
            color=discord.Color.green(),
        )
        embed.add_field(name="✅ Solved by", value=str(len(claims)), inline=True)

        if claims:
            names = []
            for uid in claims[:10]:
                try:
                    user = await self.bot.fetch_user(int(uid))
                    names.append(user.display_name)
                except Exception:
                    names.append(f"User {uid}")
            embed.add_field(name="🏆 Solvers", value="\n".join(names), inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyCog(bot))
