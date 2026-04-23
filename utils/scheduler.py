"""
utils/scheduler.py — APScheduler wrapper and background task launcher.

Call `start_scheduler(bot)` once from on_ready.
Register new periodic jobs here by adding them to `_register_jobs`.
"""

import discord
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ext import tasks

from config.settings import TZ_IST

# Shared scheduler instance — importable by cogs that add their own jobs
scheduler = AsyncIOScheduler(timezone=TZ_IST)


async def start_scheduler(bot: discord.ext.commands.Bot) -> None:
    """Start APScheduler and any discord.ext.tasks loops registered on cogs."""
    # Start APScheduler
    try:
        scheduler.start()
        print("🕒 APScheduler started.")
    except Exception as e:
        print(f"⚠️ APScheduler error: {e}")

    # Start discord.ext.tasks loops defined in cogs
    _start_cog_tasks(bot)


def _start_cog_tasks(bot: discord.ext.commands.Bot) -> None:
    """Iterate loaded cogs and start any `tasks.Loop` attributes."""
    for cog in bot.cogs.values():
        for attr_name in dir(cog):
            attr = getattr(cog, attr_name, None)
            if isinstance(attr, tasks.Loop) and not attr.is_running():
                try:
                    attr.start()
                    print(f"📋 Started task loop: {cog.__class__.__name__}.{attr_name}")
                except RuntimeError as e:
                    if "already running" in str(e).lower():
                        print(f"ℹ️ Task already running: {attr_name}")
                    else:
                        print(f"❌ Failed to start task {attr_name}: {e}")
