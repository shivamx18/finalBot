"""
cogs/contests.py — CF contest reminders (every 30 min) and /nextround command.
LC and CC reminders removed — CF only.
"""

import datetime
import aiohttp
import discord
import pytz
from discord import app_commands
from discord.ext import commands, tasks
from config.database import guilds_collection


async def _fetch_cf_upcoming(now: datetime.datetime) -> list:
    """Fetch all upcoming Codeforces contests."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://codeforces.com/api/contest.list",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()

        results = []
        for c in data.get("result", []):
            if c["phase"] != "BEFORE":
                continue
            start = datetime.datetime.utcfromtimestamp(c["startTimeSeconds"]).replace(tzinfo=pytz.utc)
            if start > now:
                results.append({
                    "name":  c["name"],
                    "url":   f"https://codeforces.com/contest/{c['id']}",
                    "start": start,
                })
        return results
    except Exception as e:
        print(f"[Contests] Error fetching CF: {e}")
        return []


class ContestsCog(commands.Cog, name="Contests"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @tasks.loop(minutes=30)
    async def check_contests(self) -> None:
        """Send reminders for CF contests starting within 24 hours."""
        now      = datetime.datetime.now(datetime.UTC)
        upcoming = await _fetch_cf_upcoming(now)

        within_24h = [
            c for c in upcoming
            if 0 < (c["start"] - now).total_seconds() <= 86_400
        ]
        if not within_24h:
            return

        for guild_data in guilds_collection.find():
            if not guild_data.get("reminder_enable_cf", True):
                continue

            channel_id       = guild_data.get("reminder_channel")
            role_id          = guild_data.get("reminder_role")
            message_template = guild_data.get(
                "reminder_message",
                "📢 CONTEST TODAY: {name}\nREGISTER HERE: {url}\n{role}"
            )

            guild = self.bot.get_guild(guild_data["guild_id"])
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            role    = guild.get_role(role_id)
            if not channel or not role:
                continue

            for contest in within_24h:
                time_left = contest["start"] - now
                hours   = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)

                embed = discord.Embed(
                    title="📢 Codeforces Contest Reminder!",
                    description=f"**[{contest['name']}]({contest['url']})**",
                    color=discord.Color.blurple(),
                )
                embed.add_field(name="🕒 Starts In", value=f"`{hours}h {minutes}m`", inline=True)
                embed.set_footer(text="Good luck! Don't forget to register.")

                try:
                    await channel.send(
                        content=message_template.format(
                            name=contest["name"],
                            url=contest["url"],
                            platform="Codeforces",
                            role=role.mention,
                        ),
                        embed=embed,
                        allowed_mentions=discord.AllowedMentions(roles=True),
                    )
                except Exception as e:
                    print(f"[Contests] Failed to send reminder in {guild.name}: {e}")

    @app_commands.command(
        name="nextround",
        description="See upcoming Codeforces contests",
    )
    async def next_round(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()

        now      = datetime.datetime.now(datetime.UTC)
        upcoming = await _fetch_cf_upcoming(now)
        upcoming.sort(key=lambda c: c["start"])

        if not upcoming:
            return await interaction.followup.send("❌ No upcoming Codeforces contests found.")

        embed = discord.Embed(
            title="📅 Upcoming Codeforces Contests",
            color=discord.Color.green()
        )
        for contest in upcoming[:5]:
            time_left = contest["start"] - now
            hours   = int(time_left.total_seconds() // 3600)
            minutes = int((time_left.total_seconds() % 3600) // 60)
            embed.add_field(
                name=contest["name"],
                value=f"⏰ Starts in `{hours}h {minutes}m`\n🔗 [Register]({contest['url']})",
                inline=False,
            )

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ContestsCog(bot))
