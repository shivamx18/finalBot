"""
cogs/stats.py — Codeforces statistics, graphs, and problem recommendations.

Commands
--------
/statscf            CF profile stats + rating history graph
/comparecf          Compare two CF handles
/comparediscord     Compare two verified Discord users' CF handles
/comparemulti       Compare 2-5 CF handles on one graph
/cfheatmap          GitHub-style AC heatmap for your handle
/trainingplan       5 CF problems in a given rating/tag range
/recommendcf        5 recommended problems based on your current rating
"""

import datetime
import random

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from config.database import users_collection
from utils.cf_api import (
    fetch_cf_rating_history,
    fetch_ac_submissions,
    fetch_problems_from_cf,
)
from utils.charts import (
    generate_cf_stats_graph,
    generate_comparison_graph,
    generate_cf_heatmap,
)
from utils.discord_helpers import get_user_handle


class StatsCog(commands.Cog, name="Stats"):
    """Codeforces statistics, rating graphs, and problem recommendations."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /statscf ──────────────────────────────────────────────────────────────

    @app_commands.command(
        name="statscf",
        description="Show Codeforces profile stats and rating history graph",
    )
    @app_commands.describe(handle="Codeforces handle")
    async def stats_cf(self, interaction: discord.Interaction, handle: str) -> None:
        await interaction.response.defer()

        async with aiohttp.ClientSession() as session:
            # User info
            async with session.get(
                f"https://codeforces.com/api/user.info?handles={handle}"
            ) as resp:
                info = await resp.json()
            if info["status"] != "OK":
                return await interaction.followup.send("❌ Invalid Codeforces handle.")
            user = info["result"][0]

            # Rating history
            async with session.get(
                f"https://codeforces.com/api/user.rating?handle={handle}"
            ) as resp:
                hist = await resp.json()
            if hist["status"] != "OK" or not hist.get("result"):
                return await interaction.followup.send("⚠️ No contest data available.")
            history = hist["result"]

        buf  = generate_cf_stats_graph(history, handle)
        file = discord.File(buf, filename="cf_rating.png")

        embed = discord.Embed(
            title=f"{handle}'s Codeforces Stats",
            description=(
                f"🏅 **Rank**: `{user.get('rank', 'Unrated').title()}`\n"
                f"📊 **Rating**: `{user.get('rating', 'Unrated')}`\n"
                f"📈 **Max Rating**: `{user.get('maxRating', 'N/A')}`"
            ),
            color=discord.Color.blue(),
        )
        embed.set_thumbnail(url=user.get("avatar", ""))
        embed.set_image(url="attachment://cf_rating.png")
        await interaction.followup.send(embed=embed, file=file)

    # ── /comparecf ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="comparecf",
        description="Compare rating histories of two Codeforces handles",
    )
    @app_commands.describe(user1="First CF handle", user2="Second CF handle")
    async def compare_cf(
        self, interaction: discord.Interaction, user1: str, user2: str
    ) -> None:
        await interaction.response.defer()
        try:
            h1 = await fetch_cf_rating_history(user1)
            h2 = await fetch_cf_rating_history(user2)
            if not h1 or not h2:
                return await interaction.followup.send(
                    "❌ One or both users have no rating history."
                )
            await self._send_comparison(interaction, [(user1, h1), (user2, h2)],
                                        f"{user1} vs {user2} Rating Comparison")
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}")

    # ── /comparediscord ───────────────────────────────────────────────────────

    @app_commands.command(
        name="comparediscord",
        description="Compare CF ratings of two verified Discord users",
    )
    @app_commands.describe(user1="First Discord user", user2="Second Discord user")
    async def compare_discord(
        self,
        interaction: discord.Interaction,
        user1: discord.User,
        user2: discord.User,
    ) -> None:
        await interaction.response.defer()

        cf1 = get_user_handle(user1.id)
        cf2 = get_user_handle(user2.id)
        if not cf1 or not cf2:
            return await interaction.followup.send(
                "❌ Both users must be verified with `/verify`."
            )

        try:
            h1 = await fetch_cf_rating_history(cf1)
            h2 = await fetch_cf_rating_history(cf2)
            if not h1 or not h2:
                return await interaction.followup.send(
                    "❌ One or both users have no rating history."
                )
            await self._send_comparison(interaction, [(cf1, h1), (cf2, h2)],
                                        f"{cf1} vs {cf2} Rating Comparison",
                                        color=discord.Color.green())
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}")

    # ── /comparemulti ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="comparemulti",
        description="Compare 2 to 5 Codeforces handles on one graph",
    )
    @app_commands.describe(handles="Space-separated CF handles (2–5)")
    async def compare_multi(self, interaction: discord.Interaction, handles: str) -> None:
        handle_list = handles.strip().split()
        if not 2 <= len(handle_list) <= 5:
            return await interaction.response.send_message(
                "❌ Provide 2 to 5 handles only.", ephemeral=True
            )

        await interaction.response.defer()
        histories = []
        try:
            for handle in handle_list:
                hist = await fetch_cf_rating_history(handle)
                if not hist:
                    return await interaction.followup.send(
                        f"⚠️ `{handle}` has no contest history."
                    )
                histories.append((handle, hist))

            await self._send_comparison(
                interaction, histories,
                "Multi-User Rating Comparison",
                filename="multi_compare.png",
                color=discord.Color.orange(),
            )
        except Exception as e:
            await interaction.followup.send(f"⚠️ Error: {e}")

    # ── /cfheatmap ────────────────────────────────────────────────────────────

    @app_commands.command(
        name="cfheatmap",
        description="View your Codeforces AC heatmap (GitHub-style)",
    )
    async def cf_heatmap(self, interaction: discord.Interaction) -> None:
        user = users_collection.find_one({"discord_id": str(interaction.user.id)})
        if not user or "cfid" not in user:
            return await interaction.response.send_message(
                "❌ You must be verified first."
            )

        await interaction.response.defer()
        cfid = user["cfid"]

        solved_dates = await fetch_ac_submissions(cfid)
        if solved_dates is None:
            return await interaction.followup.send("⚠️ Failed to fetch submissions.")

        buf       = generate_cf_heatmap(solved_dates, cfid)
        total_ac  = sum(solved_dates.values())

        # Calculate streaks
        today          = datetime.date.today()
        current_streak = 0
        max_streak     = 0
        streak         = 0

        for i in range(364, -1, -1):
            date = today - datetime.timedelta(days=i)
            if solved_dates.get(date, 0):
                streak += 1
                if i == 0:
                    current_streak = streak
            else:
                max_streak = max(max_streak, streak)
                streak     = 0
        max_streak = max(max_streak, streak)

        file  = discord.File(buf, filename="heatmap.png")
        embed = discord.Embed(
            title=f"{cfid}'s Solve Heatmap",
            description=(
                f"🧩 Total Solved: `{total_ac}`\n"
                f"🔥 Current Streak: `{current_streak}` days\n"
                f"📈 Max Streak: `{max_streak}` days"
            ),
            color=discord.Color.red(),
        )
        embed.set_image(url="attachment://heatmap.png")
        await interaction.followup.send(embed=embed, file=file)

    # ── /trainingplan ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="trainingplan",
        description="Get 5 CF problems in a given rating range and optional tag filter",
    )
    @app_commands.describe(
        min_rating="Minimum problem rating",
        max_rating="Maximum problem rating",
        tags="Comma-separated tags (e.g. dp, graphs, binary search)",
    )
    async def training_plan(
        self,
        interaction: discord.Interaction,
        min_rating: int = 800,
        max_rating: int = 1600,
        tags: str = "",
    ) -> None:
        await interaction.response.defer()

        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]
        problems = await fetch_problems_from_cf(
            tag_filter=tag_list or None,
            min_rating=min_rating,
            max_rating=max_rating,
        )

        if not problems:
            return await interaction.followup.send(
                "❌ No problems found for the specified criteria."
            )

        embed = discord.Embed(
            title="📘 Training Plan",
            description=f"5 problems between `{min_rating}` and `{max_rating}` rating.",
            color=discord.Color.blurple(),
        )
        for i, p in enumerate(problems, 1):
            url     = f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}"
            tag_str = ", ".join(p.get("tags", []))
            embed.add_field(
                name=f"{i}. {p['name']}",
                value=f"[Solve]({url}) • Tags: `{tag_str}` • Rating: `{p['rating']}`",
                inline=False,
            )
        await interaction.followup.send(embed=embed)

    # ── /recommendcf ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="recommendcf",
        description="Get 5 recommended CF problems based on your current rating",
    )
    async def recommend_cf(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        user = users_collection.find_one({"discord_id": str(interaction.user.id)})
        if not user or "cfid" not in user:
            return await interaction.followup.send(
                "❌ You must be verified to use this command.", ephemeral=True
            )

        rating = user.get("rating", 1200)

        async with aiohttp.ClientSession() as session:
            async with session.get("https://codeforces.com/api/problemset.problems") as resp:
                data = await resp.json()
        if data["status"] != "OK":
            return await interaction.followup.send("⚠️ Failed to fetch problems.")

        problems = [
            p for p in data["result"]["problems"]
            if "rating" in p
            and abs(p["rating"] - rating) <= 300
            and "contestId" in p
        ]

        if not problems:
            return await interaction.followup.send("No suitable problems found.")

        chosen = random.sample(problems, min(5, len(problems)))
        msg    = "**🧠 Recommended Problems:**\n"
        for p in chosen:
            link = f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}"
            msg += f"- [{p['name']}]({link}) — Rating: `{p['rating']}`\n"

        await interaction.followup.send(msg)

    # ── Internal helper ───────────────────────────────────────────────────────

    async def _send_comparison(
        self,
        interaction: discord.Interaction,
        histories: list,
        title: str,
        filename: str = "compare.png",
        color: discord.Color = discord.Color.blue(),
    ) -> None:
        """Render a comparison graph and send it as an embed."""
        buf  = generate_comparison_graph(histories, title)
        file = discord.File(buf, filename=filename)
        embed = discord.Embed(title=title, color=color)
        embed.set_image(url=f"attachment://{filename}")
        await interaction.followup.send(embed=embed, file=file)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StatsCog(bot))
