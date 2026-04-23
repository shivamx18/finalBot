import asyncio
import traceback
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config.settings import TOKEN
from config.database import init_db
from utils.scheduler import start_scheduler

COGS = [
    "cogs.admin",
    "cogs.verify",
    "cogs.duel",
    "cogs.stats",
    "cogs.contests",
    "cogs.community",
    "cogs.tracker",       
    "cogs.leaderboard",
    "cogs.daily",    
    "cogs.practice", 
    "cogs.streaks",  
    "cogs.teamduel", 
    "cogs.broadcast",
    "cogs.hunt",
]
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"[ERROR] Command error: {error}")
    traceback.print_exc()
    try:
        msg = "❌ This command is for **admins only**." if isinstance(error, app_commands.MissingPermissions) else f"⚠️ Error: `{error}`"
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        print(f"[ERROR] Could not send error message: {e}")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🌐 Synced {len(synced)} commands globally.")
    except Exception as e:
        print(f"❌ Sync failed: {e}")
    await start_scheduler(bot)


async def main():
    load_dotenv()
    init_db()

    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                print(f"✅ Loaded: {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}:")
                traceback.print_exc()  # prints the FULL error so you can see exactly what's wrong

        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
