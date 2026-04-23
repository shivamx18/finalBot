"""
cogs/hunt.py — Timed problem hunt events.

Admin creates a hunt with 5 problems of increasing difficulty.
Users earn points per problem solved within the time limit.
A leaderboard is posted at the end.

Points: Problem 1=1pt, 2=2pt, 3=3pt, 4=4pt, 5=5pt

Commands
--------
/starthunt      Admin: start a hunt (picks 5 problems automatically)
/huntsolve      Claim a solved problem during an active hunt
/huntleader     See the current hunt leaderboard
/endhunt        Admin: end the hunt early and post final results
"""

import asyncio
import datetime
import random
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config.database import guilds_collection, users_collection


HUNT_RATINGS = [800, 1000, 1200, 1400, 1600]  # difficulties for problems 1-5
HUNT_POINTS  = [1, 2, 3, 4, 5]


async def _fetch_hunt_problems() -> Optional[list]:
    """Fetch 5 problems at increasing difficulty for a hunt."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://codeforces.com/api/problemset.problems",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()

        all_problems = data["result"]["problems"]
        selected = []
        for rating in HUNT_RATINGS:
            pool = [
                p for p in all_problems
                if p.get("rating") == rating and "contestId" in p
            ]
            if not pool:
                return None
            selected.append(random.choice(pool))
        return selected
    except Exception as e:
        print(f"[Hunt] Error fetching problems: {e}")
        return None


class HuntCog(commands.Cog, name="Hunt"):
    """Timed problem hunt events with a leaderboard."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /starthunt ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="starthunt",
        description="Admin only: Start a timed problem hunt (5 problems, increasing difficulty)",
    )
    @app_commands.describe(
        duration_hours="Hunt duration in hours (default 2)",
        channel="Channel to post the hunt in",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def start_hunt(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        duration_hours: int = 2,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        # Check no hunt already running
        existing = guilds_collection.find_one({
            "guild_id": interaction.guild_id,
            "hunt_active": True,
        })
        if existing:
            return await interaction.followup.send(
                "❌ A hunt is already running. Use `/endhunt` to end it first.",
                ephemeral=True,
            )

        problems = await _fetch_hunt_problems()
        if not problems:
            return await interaction.followup.send(
                "❌ Failed to fetch problems from Codeforces.", ephemeral=True
            )

        end_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=duration_hours)

        hunt_data = {
            "guild_id":    interaction.guild_id,
            "hunt_active": True,
            "hunt_channel": channel.id,
            "hunt_end":    end_time.isoformat(),
            "hunt_problems": [
                {
                    "num":    i + 1,
                    "name":   p["name"],
                    "url":    f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
                    "rating": p["rating"],
                    "points": HUNT_POINTS[i],
                    "solvers": [],
                }
                for i, p in enumerate(problems)
            ],
        }

        guilds_collection.update_one(
            {"guild_id": interaction.guild_id},
            {"$set": hunt_data},
            upsert=True,
        )

        # Build announcement embed
        embed = discord.Embed(
            title="🏹 Problem Hunt Started!",
            description=(
                f"Solve as many problems as you can in **{duration_hours} hour(s)**!\n"
                f"Use `/huntsolve <problem_number>` after submitting on Codeforces."
            ),
            color=discord.Color.gold(),
        )
        for p in hunt_data["hunt_problems"]:
            embed.add_field(
                name=f"Problem {p['num']} — {p['points']} pt{'s' if p['points'] > 1 else ''}",
                value=f"[{p['name']}]({p['url']}) | Rating: `{p['rating']}`",
                inline=False,
            )
        embed.set_footer(text=f"Hunt ends at {end_time.strftime('%H:%M UTC')}")

        await channel.send(embed=embed)
        await interaction.followup.send("✅ Hunt started!", ephemeral=True)

        # Schedule auto-end
        await asyncio.sleep(duration_hours * 3600)
        await self._end_hunt(interaction.guild_id)

    # ── /huntsolve ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="huntsolve",
        description="Claim a solved problem during an active hunt",
    )
    @app_commands.describe(problem_number="Which problem did you solve? (1-5)")
    async def hunt_solve(self, interaction: discord.Interaction, problem_number: int) -> None:
        if problem_number not in range(1, 6):
            return await interaction.response.send_message(
                "❌ Problem number must be 1 to 5.", ephemeral=True
            )

        guild_doc = guilds_collection.find_one({
            "guild_id":    interaction.guild_id,
            "hunt_active": True,
        })
        if not guild_doc:
            return await interaction.response.send_message(
                "❌ No hunt is currently running.", ephemeral=True
            )

        user_id  = str(interaction.user.id)
        problems = guild_doc.get("hunt_problems", [])
        prob     = next((p for p in problems if p["num"] == problem_number), None)

        if not prob:
            return await interaction.response.send_message("❌ Problem not found.", ephemeral=True)

        if user_id in prob.get("solvers", []):
            return await interaction.response.send_message(
                f"✅ You already claimed Problem {problem_number}!", ephemeral=True
            )

        # Record the solve
        guilds_collection.update_one(
            {"guild_id": interaction.guild_id, "hunt_problems.num": problem_number},
            {"$addToSet": {"hunt_problems.$.solvers": user_id}},
        )

        # Update user points in the hunt
        users_collection.update_one(
            {"discord_id": user_id},
            {"$inc": {f"hunt_points.{guild_doc.get('hunt_end', 'current')}": prob["points"]}},
            upsert=True,
        )

        await interaction.response.send_message(
            f"🎯 Problem {problem_number} claimed! +**{prob['points']} point(s)**", ephemeral=True
        )

    # ── /huntleader ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="huntleader",
        description="View the current hunt leaderboard",
    )
    async def hunt_leader(self, interaction: discord.Interaction) -> None:
        guild_doc = guilds_collection.find_one({
            "guild_id":    interaction.guild_id,
            "hunt_active": True,
        })
        if not guild_doc:
            return await interaction.response.send_message(
                "❌ No active hunt right now.", ephemeral=True
            )

        # Tally scores from problem solvers
        scores: dict[str, int] = {}
        for prob in guild_doc.get("hunt_problems", []):
            for uid in prob.get("solvers", []):
                scores[uid] = scores.get(uid, 0) + prob["points"]

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        embed = discord.Embed(
            title="🏹 Hunt Leaderboard",
            color=discord.Color.gold(),
        )
        if not sorted_scores:
            embed.description = "No solves yet — get coding!"
        else:
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, pts) in enumerate(sorted_scores[:10]):
                medal = medals[i] if i < 3 else f"#{i+1}"
                try:
                    user = await self.bot.fetch_user(int(uid))
                    name = user.display_name
                except Exception:
                    name = f"User {uid}"
                embed.add_field(
                    name=f"{medal} {name}",
                    value=f"**{pts}** point(s)",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    # ── /endhunt ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="endhunt",
        description="Admin only: End the current hunt and post final results",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def end_hunt(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        ended = await self._end_hunt(interaction.guild_id)
        if ended:
            await interaction.followup.send("✅ Hunt ended and results posted.", ephemeral=True)
        else:
            await interaction.followup.send("❌ No active hunt found.", ephemeral=True)

    async def _end_hunt(self, guild_id: int) -> bool:
        """Internal: end hunt, post results, clear hunt state."""
        guild_doc = guilds_collection.find_one({"guild_id": guild_id, "hunt_active": True})
        if not guild_doc:
            return False

        guild   = self.bot.get_guild(guild_id)
        channel = guild.get_channel(guild_doc.get("hunt_channel")) if guild else None

        if channel:
            scores: dict[str, int] = {}
            for prob in guild_doc.get("hunt_problems", []):
                for uid in prob.get("solvers", []):
                    scores[uid] = scores.get(uid, 0) + prob["points"]

            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

            embed = discord.Embed(
                title="🏁 Hunt Over — Final Results!",
                color=discord.Color.gold(),
            )
            if not sorted_scores:
                embed.description = "No problems were solved. Better luck next hunt!"
            else:
                medals = ["🥇", "🥈", "🥉"]
                for i, (uid, pts) in enumerate(sorted_scores[:10]):
                    medal = medals[i] if i < 3 else f"#{i+1}"
                    try:
                        user = await self.bot.fetch_user(int(uid))
                        name = user.mention
                    except Exception:
                        name = f"<@{uid}>"
                    embed.add_field(
                        name=f"{medal} {name}",
                        value=f"**{pts}** point(s)",
                        inline=False,
                    )

            await channel.send(embed=embed)

        guilds_collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"hunt_active": False}},
        )
        return True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HuntCog(bot))
