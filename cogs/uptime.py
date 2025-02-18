# cogs/uptime.py

import discord
from discord.ext import commands
import datetime

class Uptime(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Record the bot's start time
        self.start_time = datetime.datetime.utcnow()

    @commands.command(name="uptime")
    async def uptime(self, ctx: commands.Context):
        """Shows how long the bot has been running."""
        now = datetime.datetime.utcnow()
        delta = now - self.start_time

        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        await ctx.send(f"**Uptime:** {hours}h {minutes}m {seconds}s")

async def setup(bot: commands.Bot):
    await bot.add_cog(Uptime(bot))
