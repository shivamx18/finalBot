import os
import random
import asyncio
import discord
import aiohttp
import datetime
from discord.ext import commands
import calendar
import pytz
import matplotlib.pyplot as plt
import numpy as np
from discord import app_commands
from dotenv import load_dotenv
from typing import List, Dict
from pymongo import MongoClient
from typing import Optional
from discord.ext import tasks
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from matplotlib import pyplot as plt
from io import BytesIO
from discord.ui import Modal, TextInput, View
from discord import TextStyle
from collections import defaultdict
scheduler = AsyncIOScheduler()



# ------------------ Load ENV Variables ------------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# ------------------ Discord Bot Setup ------------------
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ------------------ MongoDB Setup ------------------
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["codeforces_bot"]

# Collections
users_collection = db["users"]           # Stores verified users
guilds_collection = db["guilds"]         # Stores guild config (duel/command channels)

# ------------------ Role Colors by CF Rank ------------------
role_colors = {
    "newbie": 0xCCCCCC,
    "pupil": 0x77FF77,
    "specialist": 0x77DDBB,
    "expert": 0xAAAAFF,
    "candidate master": 0xFF88FF,
    "master": 0xFFCC88,
    "international master": 0xFFBB55,
    "grandmaster": 0xFF7777,
    "international grandmaster": 0xFF3333,
    "legendary grandmaster": 0xAA0000,
}

# ------------------ Utility: CF API Helper ------------------
async def get_user_rating_and_rank(handle: str):
    url = f"https://codeforces.com/api/user.info?handles={handle}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if data["status"] != "OK":
                raise ValueError("Invalid handle or API error")
            user = data["result"][0]
            rank = user.get("rank", "newbie").lower()
            rating = user.get("rating", 800)
            return rank, rating

# ------------------ Utility: Guild Channel Check ------------------
async def check_and_warn(interaction: discord.Interaction) -> bool:
    """Checks if the command is used in the allowed channel. Warns if not."""
    guild_id = interaction.guild_id
    guild_config = guilds_collection.find_one({"guild_id": guild_id})

    if guild_config and "command_channel_id" in guild_config:
        allowed_id = guild_config["command_channel_id"]
        if interaction.channel_id != allowed_id:
            channel = bot.get_channel(allowed_id)
            await interaction.response.send_message(
                f"❌ Please use bot commands in {channel.mention}.",
                ephemeral=True
            )
            return False
    return True

async def fetch_ac_submissions(cfid):
    """Fetch accepted submissions from CF and return date-wise count"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://codeforces.com/api/user.status?handle={cfid}") as r:
            data = await r.json()

    if data["status"] != "OK":
        return None

    solved_dates = defaultdict(int)
    for sub in data["result"]:
        if sub["verdict"] == "OK":
            dt = datetime.datetime.utcfromtimestamp(sub["creationTimeSeconds"]).date()
            solved_dates[dt] += 1
    return solved_dates


# ------------------ Slash Command: /setcommandchannel ------------------
@tree.command(name="setcommandchannel", description="Set the bot command channel (admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def set_command_channel(interaction: discord.Interaction):
    """Stores the command channel ID in MongoDB"""
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"command_channel_id": interaction.channel_id}},
        upsert=True
    )
    await interaction.response.send_message("✅ Bot command channel has been set.", ephemeral=True)

# ------------------ Slash Command: /setreminderchannel ------------------
@tree.command(name="setreminderchannel", description="Admin only: Set contest reminder channel and mention role")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel where reminders will be sent",
                       role="Role to mention in reminders",
                       enable_cf="Enable Codeforces reminders?",
                       enable_cc="Enable CodeChef reminders?",
                       enable_lc="Enable LeetCode reminders?",
                       custom_message="Customize reminder message. Use {name}, {url}, {platform}, {role}")
async def setreminderchannel(interaction: discord.Interaction,
                             channel: discord.TextChannel,
                             role: discord.Role,
                             enable_cf: bool = True,
                             enable_cc: bool = True,
                             enable_lc: bool = True,
                             custom_message: str = "CONTEST TODAY: {name}\nREGISTER HERE: {url}\n{role}"):
    guilds_collection.update_one(
        {"guild_id": interaction.guild.id},
        {"$set": {
            "reminder_channel": channel.id,
            "reminder_role": role.id,
            "reminder_message": custom_message,
            "reminder_enable_cf": enable_cf,
            "reminder_enable_cc": enable_cc,
            "reminder_enable_lc": enable_lc
        }},
        upsert=True
    )
    await interaction.response.send_message("✅ Reminder settings updated!", ephemeral=True)

# ------------------ Slash Command: /setduelchannel ------------------
@tree.command(name="setduelchannel", description="Set the duel challenge channel (admin only)")
@app_commands.checks.has_permissions(administrator=True)
async def set_duel_channel(interaction: discord.Interaction):
    """Stores the duel channel ID in MongoDB"""
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"duel_channel_id": interaction.channel_id}},
        upsert=True
    )
    await interaction.response.send_message("✅ Duel challenge channel has been set.", ephemeral=True)

# ------------------ Slash Command: /setmodchannel ------------------
@tree.command(name="setmodchannel", description="Set the mod feedback channel (Admin only)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="The channel where suggestions should go")
async def setmodchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"mod_channel": channel.id}},
        upsert=True
    )
    await interaction.response.send_message(f"✅ Mod feedback channel set to {channel.mention}", ephemeral=True)


# ------------------ Helper: Get user's Codeforces handle from MongoDB ------------------
def get_user_handle(discord_id: int) -> str | None:
    user = users_collection.find_one({"discord_id": str(discord_id)})
    if user:
        return user.get("cfid")
    return None

@tree.command(name="setpotd1channel", description="Admin only: Set channel and role for POTD Level 1")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel for POTD Level 1", role="Role to mention")
async def set_potd1_channel(interaction: discord.Interaction,
                            channel: discord.TextChannel,
                            role: discord.Role):
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"potd1_channel": channel.id, "potd1_role": role.id}},
        upsert=True
    )
    await interaction.response.send_message("✅ POTD Level 1 channel and role set!", ephemeral=True)

@tree.command(name="setpotd2channel", description="Admin only: Set channel and role for POTD Level 2")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="Channel for POTD Level 2", role="Role to mention")
async def set_potd2_channel(interaction: discord.Interaction,
                            channel: discord.TextChannel,
                            role: discord.Role):
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"potd2_channel": channel.id, "potd2_role": role.id}},
        upsert=True
    )
    await interaction.response.send_message("✅ POTD Level 2 channel and role set!", ephemeral=True)


# ------------------ /disablereminder ------------------
@tree.command(name="disablereminder", description="Admin only: Disable contest reminders for a platform")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(platform="Choose platform to disable (cf / cc / lc)")
async def disablereminder(interaction: discord.Interaction, platform: str):
    platform = platform.lower()
    if platform not in ("cf", "cc", "lc"):
        return await interaction.response.send_message("❌ Valid platforms: `cf`, `cc`, `lc`", ephemeral=True)

    field_map = {"cf": "reminder_enable_cf", "cc": "reminder_enable_cc", "lc": "reminder_enable_lc"}
    guilds_collection.update_one(
        {"guild_id": interaction.guild.id},
        {"$set": {field_map[platform]: False}},
        upsert=True
    )
    await interaction.response.send_message(f"🔕 Reminders for **{platform.upper()}** disabled.", ephemeral=True)

# Create a new command for setting the Solve Hunt channel
@tree.command(name="setsolvehuntchannel", description="Admin only: Set Solve Hunt challenge channel")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(channel="The channel where Solve Hunt problems will be posted")
async def setsolvehuntchannel(interaction: discord.Interaction, channel: discord.TextChannel):
    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"solvehunt_channel": channel.id}},
        upsert=True
    )
    await interaction.response.send_message(f"✅ Solve Hunt channel set to {channel.mention}", ephemeral=True)


# Scheduled Job (add to your scheduler setup):
async def post_solvehunt_problems():
    now = datetime.datetime.now(pytz.timezone("Asia/Kolkata"))
    if now.weekday() != 0:  # Monday
        return

    problems_by_rating = [1100, 1300, 1500, 1700, 1900]
    all_guilds = guilds_collection.find({"solvehunt_channel": {"$exists": True}})

    for guild_config in all_guilds:
        channel_id = guild_config["solvehunt_channel"]
        guild_id = guild_config["guild_id"]

        channel = bot.get_channel(channel_id)
        if not channel:
            continue

        embed = discord.Embed(
            title="🏹 Solve Hunt Challenge - Week Start!",
            description="Solve any 3 of the 5 problems below as fast as you can to earn the **Hunt3** role!",
            color=discord.Color.orange()
        )

        async with aiohttp.ClientSession() as session:
            for rating in problems_by_rating:
                problem = await get_random_problem(session, rating)
                if problem:
                    name = problem['name']
                    url = f"https://codeforces.com/problemset/problem/{problem['contestId']}/{problem['index']}"
                    embed.add_field(name=f"{rating} - {name}", value=f"[Solve Now]({url})", inline=False)

        await channel.send(embed=embed)

        # Remove old Hunt3 roles
        guild = bot.get_guild(guild_id)
        hunt_role = discord.utils.get(guild.roles, name="Hunt3")
        if not hunt_role:
            hunt_role = await guild.create_role(name="Hunt3", colour=discord.Colour.from_str("#FFA500"))

        for member in guild.members:
            if hunt_role in member.roles:
                await member.remove_roles(hunt_role)

# Dummy function you must already have or implement
async def get_random_problem(session, rating):
    async with session.get(f"https://codeforces.com/api/problemset.problems") as resp:
        data = await resp.json()
        if data['status'] != 'OK':
            return None

        problems = [p for p in data['result']['problems']
                    if p.get("rating") == rating and 'contestId' in p]
        if not problems:
            return None
        return random.choice(problems)


# Scheduler Setup — call this in your start_scheduler or on_ready
@scheduler.scheduled_job("cron", day_of_week="mon", hour=0, minute=0, timezone="Asia/Kolkata")
async def scheduled_solvehunt():
    await post_solvehunt_problems()


# ------------------ /enablereminder ------------------
@tree.command(name="enablereminder", description="Admin only: Enable contest reminders for a platform")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(platform="Choose platform to enable (cf / cc / lc)")
async def enablereminder(interaction: discord.Interaction, platform: str):
    platform = platform.lower()
    if platform not in ("cf", "cc", "lc"):
        return await interaction.response.send_message("❌ Valid platforms: `cf`, `cc`, `lc`", ephemeral=True)

    field_map = {"cf": "reminder_enable_cf", "cc": "reminder_enable_cc", "lc": "reminder_enable_lc"}
    guilds_collection.update_one(
        {"guild_id": interaction.guild.id},
        {"$set": {field_map[platform]: True}},
        upsert=True
    )
    await interaction.response.send_message(f"🔔 Reminders for **{platform.upper()}** enabled.", ephemeral=True)

async def fetch_problems_from_cf(tag_filter: List[str] = None, min_rating: int = 800, max_rating: int = 1600) -> List[Dict]:
    async with aiohttp.ClientSession() as session:
        async with session.get("https://codeforces.com/api/problemset.problems") as resp:
            data = await resp.json()
            all_problems = data["result"]["problems"]
            problems = []

            for p in all_problems:
                if "rating" in p and min_rating <= p["rating"] <= max_rating:
                    if tag_filter and not any(tag in p["tags"] for tag in tag_filter):
                        continue
                    problems.append(p)

            return random.sample(problems, min(5, len(problems)))

@tree.command(name="thank", description="Publicly thank someone for helping you")
@app_commands.describe(user="The helpful person you want to thank", reason="Why are you thanking them?")
async def thank(interaction: discord.Interaction, user: discord.User, reason: str):
    if user.id == interaction.user.id:
        return await interaction.response.send_message("❌ You can't thank yourself!", ephemeral=True)

    # Save thanks to DB
    users_collection.update_one(
        {"discord_id": str(user.id)},
        {"$inc": {"thanks": 1}},
        upsert=True
    )

    # Build embed
    embed = discord.Embed(
        title="🎉 You've Been Thanked!",
        description=f"**{user.mention}** was thanked by **{interaction.user.mention}**",
        color=discord.Color.gold()
    )
    embed.add_field(name="💬 Reason", value=reason, inline=False)
    embed.set_thumbnail(url=user.avatar.url if user.avatar else discord.Embed.Empty)
    embed.set_footer(text="Spread positivity 🤝")

    await interaction.response.send_message(embed=embed)


# ✅ Error handler at the bottom
# ------------------ Global Error Handler for App Commands ------------------
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error):
    try:
        if interaction.response.is_done():
            # Already responded, use followup
            await interaction.followup.send("⚠️ Unexpected error occurred while handling the command.", ephemeral=True)
        elif isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message("❌ This command is for **admins only**.", ephemeral=True)
        else:
            await interaction.response.send_message(f"⚠️ Unexpected error: `{error}`", ephemeral=True)
    except Exception as e:
        print(f"Error in error handler: {e}")

#POTD-1
# Temp: You can place this near the top
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat"]

# ------------------ Slash Command: /setpotd1week ------------------
@tree.command(name="setpotd1week", description="Admin only: Set POTD Level 1 problems for the week")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    mon="Problem for Monday",
    tue="Problem for Tuesday",
    wed="Problem for Wednesday",
    thu="Problem for Thursday",
    fri="Problem for Friday",
    sat="Problem for Saturday"
)
async def setpotd1week(interaction: discord.Interaction,
                       mon: str,
                       tue: str,
                       wed: str,
                       thu: str,
                       fri: str,
                       sat: str):
    problems = {
        "mon": mon,
        "tue": tue,
        "wed": wed,
        "thu": thu,
        "fri": fri,
        "sat": sat
    }

    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"potd1_problems": problems}},
        upsert=True
    )
    await interaction.response.send_message("✅ POTD Level 1 problems saved for the week!", ephemeral=True)

#potd2
@tree.command(name="setpotd2week", description="Admin only: Set POTD Level 2 problems for the week")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    mon="Problem for Monday",
    tue="Problem for Tuesday",
    wed="Problem for Wednesday",
    thu="Problem for Thursday",
    fri="Problem for Friday",
    sat="Problem for Saturday"
)
async def setpotd2week(interaction: discord.Interaction,
                       mon: str,
                       tue: str,
                       wed: str,
                       thu: str,
                       fri: str,
                       sat: str):
    problems = {
        "mon": mon,
        "tue": tue,
        "wed": wed,
        "thu": thu,
        "fri": fri,
        "sat": sat
    }

    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {"potd2_problems": problems}},
        upsert=True
    )
    await interaction.response.send_message("✅ POTD Level 2 problems saved for the week!", ephemeral=True)


# ------------------ Slash Command: /verify ------------------
@tree.command(name="verify", description="Verify your Codeforces handle")
@app_commands.describe(cfid="Your Codeforces handle")
async def verify(interaction: discord.Interaction, cfid: str):
    """Creates a thread, verifies the user via CF API, and assigns rank role"""

    if not await check_and_warn(interaction):
        return

    # Defer the response early to avoid 3-second timeout
    await interaction.response.defer(ephemeral=True)

    verification_code = str(random.randint(1000, 9999))

    # Create a private thread
    thread = await interaction.channel.create_thread(
        name=f"verify-{interaction.user.name}",
        type=discord.ChannelType.private_thread
    )

    # Button view for confirmation
    class ConfirmView(discord.ui.View):
        @discord.ui.button(label="✅ Verify", style=discord.ButtonStyle.success)
        async def confirm(self, button_interaction: discord.Interaction, _):
            if button_interaction.user.id != interaction.user.id:
                await button_interaction.response.send_message(
                    "❌ Only the user who initiated verification can confirm.",
                    ephemeral=True
                )
                return

            try:
                rank, rating = await get_user_rating_and_rank(cfid)
            except Exception:
                await button_interaction.response.send_message("❌ Invalid Codeforces handle.", ephemeral=True)
                return

            # Create or find role based on CF rank
            role_name = rank.title()
            guild = interaction.guild
            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                role = await guild.create_role(
                    name=role_name,
                    colour=discord.Colour(role_colors.get(rank, 0xCCCCCC))
                )

            # Add role to user
            await interaction.user.add_roles(role)

            # Save to MongoDB
            users_collection.update_one(
                {"discord_id": str(interaction.user.id)},
                {"$set": {
                    "cfid": cfid,
                    "rank": rank,
                    "rating": rating,
                    "guild_id": interaction.guild_id
                }},
                upsert=True
            )

            await thread.send(f"✅ Verified as `{cfid}` with role **{role_name}**! 🎉")
            await thread.delete()

    # Instruction message inside thread
    await thread.send(
        f"{interaction.user.mention}, to verify:\n"
        f"1. Go to your [Codeforces settings](https://codeforces.com/settings)\n"
        f"2. Temporarily change your **first name** to: `{verification_code}`\n"
        f"3. Then click the ✅ button below to confirm.",
        view=ConfirmView()
    )

    # Confirmation in original interaction
    await interaction.followup.send("🔐 A private verification thread has been created for you.", ephemeral=True)

#view-potd
# ------------------ /viewpotd1 ------------------
@tree.command(name="viewpotd1", description="Admin only: View POTD Level 1 problems")
@app_commands.checks.has_permissions(administrator=True)
async def view_potd1(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild_id}) or {}
    potds = guild_data.get("potd1_problems", {})
    if not potds:
        return await interaction.response.send_message("❌ No POTD1 problems set.", ephemeral=True)

    msg = "**📘 POTD Level 1 – Current Week**\n"
    for day in ["mon", "tue", "wed", "thu", "fri", "sat"]:
        label = day.capitalize()
        msg += f"**{label}**: {potds.get(day, '❌ Not Set')}\n"

    await interaction.response.send_message(msg, ephemeral=True)

# ------------------ /viewpotd2 ------------------
@tree.command(name="viewpotd2", description="Admin only: View POTD Level 2 problems")
@app_commands.checks.has_permissions(administrator=True)
async def view_potd2(interaction: discord.Interaction):
    guild_data = guilds_collection.find_one({"guild_id": interaction.guild_id}) or {}
    potds = guild_data.get("potd2_problems", {})
    if not potds:
        return await interaction.response.send_message("❌ No POTD2 problems set.", ephemeral=True)

    msg = "**📙 POTD Level 2 – Current Week**\n"
    for day in ["mon", "tue", "wed", "thu", "fri", "sat"]:
        label = day.capitalize()
        msg += f"**{label}**: {potds.get(day, '❌ Not Set')}\n"

    await interaction.response.send_message(msg, ephemeral=True)

# ------------------ /editpotd1 ------------------
@tree.command(name="editpotd1", description="Admin only: Edit one day of POTD Level 1")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(day="Day to edit (e.g., mon, tue...)", problem="New problem link or text")
async def edit_potd1(interaction: discord.Interaction, day: str, problem: str):
    day = day.lower()
    if day not in ["mon", "tue", "wed", "thu", "fri", "sat"]:
        return await interaction.response.send_message("❌ Invalid day. Use: mon, tue, wed, thu, fri, sat", ephemeral=True)

    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {f"potd1_problems.{day}": problem}},
        upsert=True
    )
    await interaction.response.send_message(f"✅ POTD1 updated for **{day.capitalize()}**!", ephemeral=True)

# ------------------ /editpotd2 ------------------
@tree.command(name="editpotd2", description="Admin only: Edit one day of POTD Level 2")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(day="Day to edit (e.g., mon, tue...)", problem="New problem link or text")
async def edit_potd2(interaction: discord.Interaction, day: str, problem: str):
    day = day.lower()
    if day not in ["mon", "tue", "wed", "thu", "fri", "sat"]:
        return await interaction.response.send_message("❌ Invalid day. Use: mon, tue, wed, thu, fri, sat", ephemeral=True)

    guilds_collection.update_one(
        {"guild_id": interaction.guild_id},
        {"$set": {f"potd2_problems.{day}": problem}},
        upsert=True
    )
    await interaction.response.send_message(f"✅ POTD2 updated for **{day.capitalize()}**!", ephemeral=True)

#helper for unsolved problem
async def get_unsolved_problem(min_rating, max_rating, handle1, handle2):
    url = "https://codeforces.com/api/problemset.problems"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            if data["status"] != "OK":
                raise Exception("Failed to fetch problems")

            problems = data["result"]["problems"]

        # Fetch solved problems by both users
        async def get_solved(handle):
            async with session.get(f"https://codeforces.com/api/user.status?handle={handle}") as resp:
                submissions = await resp.json()
                return {
                    f"{s['problem']['contestId']}-{s['problem']['index']}"
                    for s in submissions.get("result", [])
                    if s.get("verdict") == "OK"
                }

        solved1 = await get_solved(handle1)
        solved2 = await get_solved(handle2)
        combined_solved = solved1.union(solved2)

        unsolved = [
            p for p in problems
            if "contestId" in p and "index" in p and "rating" in p
            and min_rating <= p["rating"] <= max_rating
            and f"{p['contestId']}-{p['index']}" not in combined_solved
        ]

        if not unsolved:
            return None

        return random.choice(unsolved)


# ------------------ Slash Command: /cfid ------------------
@tree.command(name="cfid", description="Get a user's Codeforces handle")
@app_commands.describe(user="Discord user")
async def cfid(interaction: discord.Interaction, user: discord.User):
    record = users_collection.find_one({"discord_id": str(user.id)})
    if record:
        await interaction.response.send_message(f"✅ `{user.display_name}` is linked to `{record['cfid']}`.")
    else:
        await interaction.response.send_message("❌ That user is not verified.")

# ------------------ Slash Command: /discordid ------------------
@tree.command(name="discordid", description="Get Discord user linked to CF ID")
@app_commands.describe(cfid="Codeforces handle")
async def discordid(interaction: discord.Interaction, cfid: str):
    record = users_collection.find_one({"cfid": cfid})
    if record:
        user = await bot.fetch_user(int(record['discord_id']))
        await interaction.response.send_message(f"✅ `{cfid}` is linked to {user.mention}.")
    else:
        await interaction.response.send_message("❌ CF handle not found.")

# ------------------ Slash Command: /unverify (admin) ------------------
@tree.command(name="unverify", description="Admin only: Unverify a user")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(user="User to unverify")
async def unverify(interaction: discord.Interaction, user: discord.User):
    users_collection.delete_one({"discord_id": str(user.id)})

    for role in user.roles:
        if role.name.lower() in role_colors:
            await user.remove_roles(role)
    await interaction.response.send_message("✅ User unverified and roles removed.")

# ------------------ Slash Command: /verified ------------------
@tree.command(name="verified", description="List all verified users")
async def verified(interaction: discord.Interaction):
    users = users_collection.find({"guild_id": interaction.guild_id})
    text = "**Verified Users:**\n"
    for user in users:
        member = await bot.fetch_user(int(user["discord_id"]))
        text += f"- {member.mention} → `{user['cfid']}`\n"
    await interaction.response.send_message(text or "No verified users yet.")

#duel 
# Helper: Record duel result in DB
def record_duel_result(winner_cfid, loser_cfid):
    # Update points
    users_collection.update_one({"cfid": winner_cfid}, {"$inc": {"duel_points": 1}})
    users_collection.update_one({"cfid": loser_cfid}, {"$inc": {"duel_points": -1}})

    # Log history
    timestamp = int(datetime.datetime.utcnow().timestamp())
    for cfid, won in [(winner_cfid, True), (loser_cfid, False)]:
        users_collection.update_one(
            {"cfid": cfid},
            {"$push": {
                "duel_history": {
                    "timestamp": timestamp,
                    "duel_points": 1 if won else -1
                }
            }}
        )

# ------------------ Duel Command ------------------
# @tree.command(name="duel", description="Challenge someone to a Codeforces duel")
# @app_commands.describe(user="Opponent", min_rating="Min rating", max_rating="Max rating")
# async def duel(interaction: discord.Interaction, user: discord.User, min_rating: int, max_rating: int):
#     guild_id = interaction.guild_id
#     guild_config = guilds_collection.find_one({"guild_id": guild_id})
#     duel_channel = guild_config.get("duel_channel") if guild_config else None
#     if duel_channel and interaction.channel_id != duel_channel:
#         return await interaction.response.send_message("❌ Use this in the designated duel channel.", ephemeral=True)

#     id1, id2 = str(interaction.user.id), str(user.id)
#     user1 = users_collection.find_one({"discord_id": id1})
#     user2 = users_collection.find_one({"discord_id": id2})

#     if not user1 or not user2:
#         return await interaction.response.send_message("Both users must be verified to duel.")

#     h1, h2 = user1["cfid"], user2["cfid"]

#     thread = await interaction.channel.create_thread(
#         name=f"duel-{interaction.user.name}-vs-{user.name}",
#         type=discord.ChannelType.private_thread
#     )



# class DuelConfirmView(discord.ui.View):
#     def __init__(self, user, thread, min_rating, max_rating, h1, h2):
#         super().__init__(timeout=180)
#         self.user = user
#         self.thread = thread
#         self.min_rating = min_rating
#         self.max_rating = max_rating
#         self.h1 = h1
#         self.h2 = h2

#     @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
#     async def accept(self, i: discord.Interaction, _):
#         if i.user.id != self.user.id:
#             return await i.response.send_message("Only the invited user can accept the duel.", ephemeral=True)

#         await i.response.defer()

#         problem = await get_unsolved_problem(self.min_rating, self.max_rating, self.h1, self.h2)
#         if not problem:
#             await self.thread.send("❌ Could not fetch a suitable problem.")
#             return await self.thread.delete()

#         await self.thread.send(
#             f"🎯 Problem: [{problem['name']}](https://codeforces.com/problemset/problem/{problem['contestId']}/{problem['index']})"
#         )

#         winner = await wait_for_ac(self.h1, self.h2, problem)
#         if not winner:
#             await self.thread.send("⏳ No one solved the problem in time. Duel ended.")
#         else:
#             loser = self.h2 if winner == self.h1 else self.h1
#             record_duel_result(winner, loser)
#             await self.thread.send(f"🏆 `{winner}` wins the duel!\n❌ `{loser}` loses.")
#         await self.thread.delete()

#     @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
#     async def reject(self, i: discord.Interaction, _):
#         if i.user.id != self.user.id:
#             return await i.response.send_message("Only the invited user can reject the duel.", ephemeral=True)
#         await self.thread.send("❌ Duel cancelled.")
#         await self.thread.delete()

@tree.command(name="duel", description="Challenge someone to a Codeforces duel")
@app_commands.describe(user="Opponent", min_rating="Minimum rating", max_rating="Maximum rating")
async def duel(interaction: discord.Interaction, user: discord.User, min_rating: int, max_rating: int):
    guild_id = interaction.guild_id
    guild_config = guilds_collection.find_one({"guild_id": guild_id})
    duel_channel = guild_config.get("duel_channel") if guild_config else None

    if duel_channel and interaction.channel_id != duel_channel:
        return await interaction.response.send_message("❌ Use this in the designated duel channel.", ephemeral=True)

    id1, id2 = str(interaction.user.id), str(user.id)
    user1 = users_collection.find_one({"discord_id": id1})
    user2 = users_collection.find_one({"discord_id": id2})

    if not user1 or not user2:
        return await interaction.response.send_message("❌ Both users must be verified to duel.", ephemeral=True)

    h1, h2 = user1["cfid"], user2["cfid"]

    # Create a private thread
    thread = await interaction.channel.create_thread(
        name=f"duel-{interaction.user.name}-vs-{user.name}",
        type=discord.ChannelType.private_thread
    )

    # Define DuelConfirmView with required arguments
    class DuelConfirmView(discord.ui.View):
        def __init__(self, user, thread, min_rating, max_rating, h1, h2):
            super().__init__(timeout=180)
            self.user = user
            self.thread = thread
            self.min_rating = min_rating
            self.max_rating = max_rating
            self.h1 = h1
            self.h2 = h2

        @discord.ui.button(label="✅ Accept", style=discord.ButtonStyle.success)
        async def accept(self, i: discord.Interaction, _):
            if i.user.id != self.user.id:
                return await i.response.send_message("❌ Only the invited user can accept the duel.", ephemeral=True)

            try:
                problem = await get_unsolved_problem(self.min_rating, self.max_rating, self.h1, self.h2)
            except Exception as e:
                await self.thread.send(f"❌ Error fetching problem: {e}")
                return await self.thread.delete()

            if not problem:
                await self.thread.send("❌ Could not find a suitable problem.")
                return await self.thread.delete()

            await self.thread.send(
                f"🎯 Problem: [{problem['name']}](https://codeforces.com/problemset/problem/{problem['contestId']}/{problem['index']})"
            )

            winner = await wait_for_ac(self.h1, self.h2, problem)
            if not winner:
                await self.thread.send("⏳ No one solved the problem in time. Duel ended.")
            else:
                loser = self.h2 if winner == self.h1 else self.h1
                record_duel_result(winner, loser)
                await self.thread.send(f"🏆 `{winner}` wins the duel!\n❌ `{loser}` loses.")
            await self.thread.delete()

        @discord.ui.button(label="❌ Reject", style=discord.ButtonStyle.danger)
        async def reject(self, i: discord.Interaction, _):
            if i.user.id != self.user.id:
                return await i.response.send_message("❌ Only the invited user can reject the duel.", ephemeral=True)
            await self.thread.send("❌ Duel cancelled.")
            await self.thread.delete()

        async def on_timeout(self):
            try:
                await self.thread.send("⌛ Duel timed out due to no response.")
                await self.thread.delete()
            except:
                pass

    await thread.send(
        f"{user.mention}, do you accept the duel challenge from {interaction.user.mention}?",
        view=DuelConfirmView(user, thread, min_rating, max_rating, h1, h2)
    )

    await interaction.response.send_message("📨 Duel request sent.", ephemeral=True)




# ------------------ Duel Leaderboard ------------------
@tree.command(name="duelleaderboard", description="See top duel performers")
async def duelleaderboard(interaction: discord.Interaction):
    users = users_collection.find().sort("duel_points", -1).limit(10)
    msg = "🏆 **Top Duel Performers** 🏆\n"
    for i, user in enumerate(users, 1):
        msg += f"**{i}.** `{user['cfid']}` → {user.get('duel_points', 0)} points\n"
    await interaction.response.send_message(msg)


# ------------------ My Duel Points ------------------
@tree.command(name="myduelpoints", description="See your current duel points")
async def myduelpoints(interaction: discord.Interaction):
    user = users_collection.find_one({"discord_id": str(interaction.user.id)})
    if not user:
        return await interaction.response.send_message("You must be verified.")
    points = user.get("duel_points", 0)
    await interaction.response.send_message(f"📊 `{user['cfid']}` has **{points}** duel points.")


# ------------------ Record Duel Result ------------------
def record_duel_result(winner_cfid, loser_cfid):
    users_collection.update_one({"cfid": winner_cfid}, {"$inc": {"duel_points": 1}})
    users_collection.update_one({"cfid": loser_cfid}, {"$inc": {"duel_points": -1}})

    timestamp = int(datetime.datetime.utcnow().timestamp())
    for cfid, won in [(winner_cfid, True), (loser_cfid, False)]:
        users_collection.update_one(
            {"cfid": cfid},
            {"$push": {
                "duel_history": {
                    "timestamp": timestamp,
                    "duel_points": 1 if won else -1
                }
            }}
        )


# ---------------- Generate Duel History Graph ------------------
def generate_duel_history_graph(history, username):
    dates = [datetime.datetime.fromtimestamp(entry["timestamp"]) for entry in history]
    points = []
    total = 0
    for entry in history:
        total += entry["duel_points"]
        points.append(total)

    plt.style.use("dark_background")
    plt.figure(figsize=(8, 4))

    plt.plot(dates, points, marker='o', linestyle='-', color='lime', label='Duel Points')
    plt.axhline(0, color='red', linestyle='--', linewidth=1)
    plt.title(f"{username}'s Duel History")
    plt.xlabel("Date")
    plt.ylabel("Points")
    plt.grid(True, linestyle='--', alpha=0.5)
    plt.tight_layout()
    plt.legend()

    buf = BytesIO()
    plt.savefig(buf, format="png", dpi=150)
    buf.seek(0)
    plt.close()
    return buf

# ------------------ /myduelhistory ------------------
@tree.command(name="myduelhistory", description="View your duel point progression graph")
async def myduelhistory(interaction: discord.Interaction):
    user = users_collection.find_one({"discord_id": str(interaction.user.id)})
    if not user:
        return await interaction.response.send_message("❌ You must be verified.", ephemeral=True)

    history = user.get("duel_history", [])
    if not history:
        return await interaction.response.send_message("📉 No duel history found.", ephemeral=True)

    buf = generate_duel_history_graph(history, interaction.user.display_name)
    file = discord.File(buf, filename="duel_history.png")

    embed = discord.Embed(
        title=f"{interaction.user.display_name}'s Duel History",
        description="📈 Here's how your duel points changed over time.",
        color=discord.Color.green()
    )
    embed.set_image(url="attachment://duel_history.png")

    await interaction.response.send_message(embed=embed, file=file)

# ------------------ Compare Features ------------------

# Helper: Get rating history for a single CF handle
async def fetch_cf_history(handle: str):
    url = f"https://codeforces.com/api/user.rating?handle={handle}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data.get("result", [])

# Helper: Draw comparison graph
def generate_comparison_graph(histories, title):
    plt.figure(figsize=(12, 6))
    colors = ['blue', 'green', 'red', 'purple', 'orange']

    for i, (handle, history) in enumerate(histories):
        dates = [datetime.datetime.fromtimestamp(e['ratingUpdateTimeSeconds']) for e in history]
        ratings = [e['newRating'] for e in history]
        plt.plot(dates, ratings, marker='o', linestyle='-', color=colors[i % len(colors)], label=handle)

    plt.title(title)
    plt.xlabel("Date")
    plt.ylabel("Rating")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ------------------ /comparecf ------------------
@tree.command(name="comparecf", description="Compare two Codeforces handles")
@app_commands.describe(user1="First Codeforces handle", user2="Second Codeforces handle")
async def comparecf(interaction: discord.Interaction, user1: str, user2: str):
    """Compares rating history of two CF users"""
    await interaction.response.defer()
    try:
        h1 = await fetch_cf_history(user1)
        h2 = await fetch_cf_history(user2)

        if not h1 or not h2:
            return await interaction.followup.send("❌ One or both users have no rating history.")

        buf = generate_comparison_graph([(user1, h1), (user2, h2)], f"{user1} vs {user2} Rating Comparison")
        file = discord.File(buf, filename="compare.png")

        embed = discord.Embed(
            title=f"{user1} vs {user2} Rating Graph",
            color=discord.Color.blue()
        )
        embed.set_image(url="attachment://compare.png")

        await interaction.followup.send(embed=embed, file=file)

    except Exception as e:
        await interaction.followup.send(f"⚠️ Error: {str(e)}")

# ------------------ /comparediscord ------------------
@tree.command(name="comparediscord", description="Compare CF ratings of 2 verified Discord users")
@app_commands.describe(user1="First Discord user", user2="Second Discord user")
async def comparediscord(interaction: discord.Interaction, user1: discord.User, user2: discord.User):
    """Fetches and compares CF handles linked to Discord users"""
    await interaction.response.defer()  # 🔥 Add this line

    cf1 = get_user_handle(user1.id)
    cf2 = get_user_handle(user2.id)

    if not cf1 or not cf2:
        return await interaction.followup.send("❌ Both users must be verified with /verify.")

    await comparecf_func(interaction, cf1, cf2)


# Helper to call comparison logic (can't directly call slash command)
async def comparecf_func(interaction, user1: str, user2: str):
    h1 = await fetch_cf_history(user1)
    h2 = await fetch_cf_history(user2)

    if not h1 or not h2:
        return await interaction.followup.send("❌ One or both users have no rating history.")

    buf = generate_comparison_graph([(user1, h1), (user2, h2)], f"{user1} vs {user2} Rating Comparison")
    file = discord.File(buf, filename="compare.png")

    embed = discord.Embed(
        title=f"{user1} vs {user2} Rating Graph",
        color=discord.Color.green()
    )
    embed.set_image(url="attachment://compare.png")

    await interaction.followup.send(embed=embed, file=file)

# ------------------ /comparemulti ------------------
@tree.command(name="comparemulti", description="Compare 2 to 5 Codeforces handles")
@app_commands.describe(handles="Enter 2 to 5 handles separated by space")
async def comparemulti(interaction: discord.Interaction, handles: str):
    """Compares multiple CF users together"""
    handle_list = handles.strip().split()
    if len(handle_list) < 2 or len(handle_list) > 5:
        return await interaction.response.send_message("❌ Provide 2 to 5 handles only.", ephemeral=True)

    await interaction.response.defer()
    histories = []

    try:
        for handle in handle_list:
            hist = await fetch_cf_history(handle)
            if not hist:
                return await interaction.followup.send(f"⚠️ `{handle}` has no contest history.")
            histories.append((handle, hist))

        buf = generate_comparison_graph(histories, "Multi-User Rating Comparison")
        file = discord.File(buf, filename="multi_compare.png")

        embed = discord.Embed(title="Multi-User Comparison Graph", color=discord.Color.orange())
        embed.set_image(url="attachment://multi_compare.png")

        await interaction.followup.send(embed=embed, file=file)

    except Exception as e:
        await interaction.followup.send(f"⚠️ Error occurred: {str(e)}")


# ------------------ /statscf ------------------
@tree.command(name="statscf", description="Show Codeforces profile stats and rating graph")
@app_commands.describe(handle="Your Codeforces handle")
async def statscf(interaction: discord.Interaction, handle: str):
    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        # Fetch user info
        async with session.get(f"https://codeforces.com/api/user.info?handles={handle}") as resp:
            info = await resp.json()
            if info["status"] != "OK":
                return await interaction.followup.send("❌ Invalid Codeforces handle.")

            user = info["result"][0]

        # Fetch rating history
        async with session.get(f"https://codeforces.com/api/user.rating?handle={handle}") as resp:
            hist = await resp.json()
            if hist["status"] != "OK" or not hist["result"]:
                return await interaction.followup.send("⚠️ No contest data available.")

            history = hist["result"]

    # Extract dates and ratings
    dates = [datetime.datetime.fromtimestamp(e["ratingUpdateTimeSeconds"]) for e in history]
    ratings = [e["newRating"] for e in history]

    # Dynamic Y limit
    max_rating = max(ratings)
    y_limit = max(2000, max_rating + 200)

    # Create graph
    plt.figure(figsize=(10, 5))
    plt.plot(dates, ratings, marker='o', linestyle='-', color='black', label='Rating')

    # Rating bands
    rating_bands = [
        (0, 1199, "#CCCCCC", "Newbie"),
        (1200, 1399, "#77FF77", "Pupil"),
        (1400, 1599, "#77DDBB", "Specialist"),
        (1600, 1899, "#AAAAFF", "Expert"),
        (1900, 2099, "#FF88FF", "CM"),
        (2100, 2299, "#FFCC88", "Master"),
        (2300, 2399, "#FFBB55", "IM"),
        (2400, 2599, "#FF7777", "GM"),
        (2600, 2899, "#FF3333", "IGM"),
        (2900, 4000, "#AA0000", "LGM"),
    ]
    for low, high, color, _ in rating_bands:
        if low < y_limit:
            plt.axhspan(low, min(high, y_limit), facecolor=color, alpha=0.2)

    # Annotate max rating
    max_idx = ratings.index(max_rating)
    plt.annotate(f'Max: {max_rating}', xy=(dates[max_idx], max_rating),
                 xytext=(dates[max_idx], max_rating + 50),
                 arrowprops=dict(arrowstyle="->", color='red'))

    plt.xlabel("Date")
    plt.ylabel("Rating")
    plt.title(f"{handle}'s Codeforces Rating History")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.ylim(0, y_limit)
    plt.tight_layout()

    # Save image
    buf = BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close()

    # Send embed
    file = discord.File(buf, filename="cf_rating.png")
    embed = discord.Embed(
        title=f"{handle}'s Codeforces Stats",
        description=(
            f"🏅 **Rank**: `{user.get('rank', 'Unrated').title()}`\n"
            f"📊 **Rating**: `{user.get('rating', 'Unrated')}`\n"
            f"📈 **Max Rating**: `{user.get('maxRating', 'N/A')}`"
        ),
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=user.get("avatar", ""))
    embed.set_image(url="attachment://cf_rating.png")

    await interaction.followup.send(embed=embed, file=file)

@tasks.loop(minutes=30)
async def check_contests():
    now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    upcoming = []

    async with aiohttp.ClientSession() as session:
        # Codeforces
        try:
            cf = await session.get("https://codeforces.com/api/contest.list")
            data = await cf.json()
            for contest in data["result"]:
                if contest["phase"] != "BEFORE":
                    continue
                start = datetime.datetime.utcfromtimestamp(contest["startTimeSeconds"]).replace(tzinfo=pytz.utc)
                if 4.9 < (start - now).total_seconds() / 3600 < 5.1:
                    upcoming.append({
                        "name": contest["name"],
                        "url": f"https://codeforces.com/contest/{contest['id']}",
                        "platform": "Codeforces"
                    })
        except: pass

        # LeetCode (uses a GitHub mirror for now)
        try:
            lc = await session.get("https://kontests.net/api/v1/leet_code")
            data = await lc.json()
            for contest in data:
                start = datetime.datetime.fromisoformat(contest["start_time"].replace("Z", "+00:00"))
                if 4.9 < (start - now).total_seconds() / 3600 < 5.1:
                    upcoming.append({
                        "name": contest["name"],
                        "url": contest["url"],
                        "platform": "LeetCode"
                    })
        except: pass

        # CodeChef
        try:
            cc = await session.get("https://kontests.net/api/v1/code_chef")
            data = await cc.json()
            for contest in data:
                start = datetime.datetime.fromisoformat(contest["start_time"].replace("Z", "+00:00"))
                if 4.9 < (start - now).total_seconds() / 3600 < 5.1:
                    upcoming.append({
                        "name": contest["name"],
                        "url": contest["url"],
                        "platform": "CodeChef"
                    })
        except: pass

    # Notify all guilds
    for guild_data in guilds_collection.find():
        channel_id = guild_data.get("reminder_channel")
        role_id = guild_data.get("reminder_role")
        message_template = guild_data.get("reminder_message", "CONTEST TODAY: {name}\nREGISTER HERE: {url}\n{role}")

        enabled = {
            "Codeforces": guild_data.get("reminder_enable_cf", True),
            "CodeChef": guild_data.get("reminder_enable_cc", True),
            "LeetCode": guild_data.get("reminder_enable_lc", True),
        }

        guild = bot.get_guild(guild_data["guild_id"])
        if not guild:
            continue

        channel = guild.get_channel(channel_id)
        role = guild.get_role(role_id)
        if not channel or not role:
            continue

        for contest in upcoming:
            if not enabled.get(contest["platform"], False):
                continue
            msg = message_template.format(name=contest["name"], url=contest["url"], platform=contest["platform"], role=role.mention)
            try:
                await channel.send(msg, allowed_mentions=discord.AllowedMentions(roles=True))
            except: pass

# ------------------ Slash Command: /trainingplan ------------------
@tree.command(name="trainingplan", description="Get a personalized Codeforces training plan")
@app_commands.describe(
    min_rating="Minimum problem rating",
    max_rating="Maximum problem rating",
    tags="Comma-separated tags (e.g., dp, graphs, binary search)"
)
async def trainingplan(interaction: discord.Interaction, min_rating: int = 800, max_rating: int = 1600, tags: str = ""):
    """Suggests 5 Codeforces problems between given rating range and optional tag filter"""
    await interaction.response.defer()

    tag_list = [tag.strip().lower() for tag in tags.split(",") if tag.strip()]
    problems = await fetch_problems_from_cf(tag_filter=tag_list if tag_list else None, min_rating=min_rating, max_rating=max_rating)

    if not problems:
        return await interaction.followup.send("❌ No problems found for the specified criteria.")

    embed = discord.Embed(
        title="📘 Training Plan",
        description=f"Here are 5 problems between `{min_rating}` and `{max_rating}` rating.",
        color=discord.Color.blurple()
    )

    for i, p in enumerate(problems, 1):
        url = f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}"
        tag_str = ", ".join(p.get("tags", []))
        embed.add_field(
            name=f"{i}. {p['name']}",
            value=f"[Solve]({url}) • Tags: `{tag_str}` • Rating: `{p['rating']}`",
            inline=False
        )

    await interaction.followup.send(embed=embed)

# ------------------ Slash Command: /recommendcf ------------------
@tree.command(name="recommendcf", description="Get 5 recommended problems based on your rating")
async def recommendcf(interaction: discord.Interaction):
    await interaction.response.defer()

    user = users_collection.find_one({"discord_id": str(interaction.user.id)})
    if not user or "cfid" not in user:
        return await interaction.followup.send("❌ You must be verified to use this command.", ephemeral=True)

    handle = user["cfid"]
    rating = user.get("rating", 1200)

    # Fetch CF problems
    async with aiohttp.ClientSession() as session:
        resp = await session.get("https://codeforces.com/api/problemset.problems")
        data = await resp.json()
        if data["status"] != "OK":
            return await interaction.followup.send("⚠️ Failed to fetch problems.")

        problems = data["result"]["problems"]
        unsolved = [
            p for p in problems
            if "rating" in p and abs(p["rating"] - rating) <= 300 and "contestId" in p
        ]

        if not unsolved:
            return await interaction.followup.send("No suitable problems found.")

        chosen = random.sample(unsolved, min(5, len(unsolved)))
        msg = "**🧠 Recommended Problems:**\n"
        for p in chosen:
            link = f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}"
            msg += f"- [{p['name']}]({link}) — Rating: {p['rating']}\n"

        await interaction.followup.send(msg)

# ------------------ Slash Command: /suggestions ------------------
@tree.command(name="suggestions", description="Send feedback or report bugs to the mod team")
@app_commands.describe(message="Your feedback, suggestion, or bug report")
async def suggestions(interaction: discord.Interaction, message: str):
    config = guilds_collection.find_one({"guild_id": interaction.guild_id})
    mod_channel_id = config.get("mod_channel") if config else None

    if not mod_channel_id:
        return await interaction.response.send_message("❌ No mod channel is configured on this server.", ephemeral=True)

    mod_channel = interaction.guild.get_channel(mod_channel_id)
    if not mod_channel:
        return await interaction.response.send_message("❌ Configured mod channel not found.", ephemeral=True)

    embed = discord.Embed(
        title="📬 New Feedback",
        description=message,
        color=discord.Color.blurple()
    )
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.timestamp = datetime.datetime.utcnow()

    await mod_channel.send(embed=embed)
    await interaction.response.send_message("✅ Your suggestion has been sent to the moderators!", ephemeral=True)

tz_ist = pytz.timezone("Asia/Kolkata")
scheduler = AsyncIOScheduler(timezone=tz_ist)

@tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=tz_ist))
async def post_potds():
    day = datetime.datetime.now(tz_ist).strftime("%a").lower()[:3]  # mon, tue, ...
    if day == "sun":
        return  # No posting on Sundays

    for guild_doc in guilds_collection.find():
        guild_id = guild_doc["guild_id"]
        guild = bot.get_guild(guild_id)
        if not guild:
            continue

        # POTD 1
        potd1_channel_id = guild_doc.get("potd1_channel")
        potd1_role_id = guild_doc.get("potd1_role")
        potd1_problems = guild_doc.get("potd1_problems", {})

        if potd1_channel_id and day in potd1_problems:
            channel = guild.get_channel(potd1_channel_id)
            role = guild.get_role(potd1_role_id)
            problem = potd1_problems[day]
            if channel and role:
                embed = discord.Embed(
                    title=f"POTD Level 1 – {day.upper()}",
                    description=f"{problem}",
                    color=discord.Color.blue()
                )
                await channel.send(content=f"{role.mention}", embed=embed)

        # POTD 2
        potd2_channel_id = guild_doc.get("potd2_channel")
        potd2_role_id = guild_doc.get("potd2_role")
        potd2_problems = guild_doc.get("potd2_problems", {})

        if potd2_channel_id and day in potd2_problems:
            channel = guild.get_channel(potd2_channel_id)
            role = guild.get_role(potd2_role_id)
            problem = potd2_problems[day]
            if channel and role:
                embed = discord.Embed(
                    title=f"POTD Level 2 – {day.upper()}",
                    description=f"{problem}",
                    color=discord.Color.purple()
                )
                await channel.send(content=f"{role.mention}", embed=embed)

def generate_cf_heatmap(solved_dates, cfid):
    """Generate heatmap image and return BytesIO"""
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=365)
    dates = list(solved_dates.keys())

    heatmap_data = defaultdict(int)
    for dt in dates:
        if dt >= start_date:
            heatmap_data[dt] += solved_dates[dt]

    days = (today - start_date).days + 1
    counts = [heatmap_data.get(start_date + datetime.timedelta(days=i), 0) for i in range(days)]

    weeks = (days + start_date.weekday()) // 7 + 1
    mat = np.zeros((7, weeks))

    for i, count in enumerate(counts):
        date = start_date + datetime.timedelta(days=i)
        week = (i + start_date.weekday()) // 7
        weekday = date.weekday()
        mat[weekday][week] = count

    fig, ax = plt.subplots(figsize=(14, 3))
    cmap = plt.cm.Reds
    im = ax.imshow(mat, cmap=cmap, aspect='auto', interpolation='nearest')

    # Customize
    ax.set_xticks([])
    ax.set_yticks(range(7))
    ax.set_yticklabels(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
    ax.set_title(f"📅 CF Solve Heatmap for {cfid}")

    # Color bar
    cbar = plt.colorbar(im, ax=ax, orientation="vertical")
    cbar.set_label("Solved Count")

    plt.tight_layout()
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

@tree.command(name="cfheatmap", description="View your Codeforces AC heatmap (like GitHub)")
async def cfheatmap(interaction: discord.Interaction):
    user = users_collection.find_one({"discord_id": str(interaction.user.id)})
    if not user or "cfid" not in user:
        return await interaction.response.send_message("❌ You must be verified first.")

    cfid = user["cfid"]
    await interaction.response.defer()

    solved_dates = await fetch_ac_submissions(cfid)
    if solved_dates is None:
        return await interaction.followup.send("⚠️ Failed to fetch submissions.")

    buf = generate_cf_heatmap(solved_dates, cfid)
    total_ac = sum(solved_dates.values())

    # Streak Calculation
    streak, max_streak = 0, 0
    today = datetime.date.today()
    for i in range(365):
        date = today - datetime.timedelta(days=i)
        if solved_dates.get(date):
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0

    embed = discord.Embed(
        title=f"{cfid}'s Heatmap",
        description=f"✅ Total Solved: `{total_ac}`\n🔥 Best Streak: `{max_streak}` days",
        color=discord.Color.red()
    )
    file = discord.File(buf, filename="heatmap.png")
    embed.set_image(url="attachment://heatmap.png")

    await interaction.followup.send(embed=embed, file=file)



# ------------------ Bot Ready Event ------------------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"🌐 Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")
    
    try:
        scheduler.start()
        print("🕒 Scheduler started successfully.")
    except Exception as e:
        print(f"Scheduler error: {e}")

# ------------------ Run the Bot ------------------
bot.run(TOKEN)
# pip install matplotlib numpy aiohttp
