import discord
import logging
import time
from discord import app_commands
from discord.ext import commands

class Uptime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()  # Record the bot's start time

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mUptime\033[0m cog synced successfully.")

    @app_commands.command(name="uptime", description="Shows how long the bot has been running.")
    async def uptime(self, interaction: discord.Interaction):
        uptime_seconds = int(time.time() - self.start_time)
        days, remainder = divmod(uptime_seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
        logging.info(f"Uptime command used. Bot has been running for: {uptime_str}")
        
        embed = discord.Embed(
            title="Bot Uptime",
            description=f"The bot has been running for: `{uptime_str}`",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Uptime(bot))