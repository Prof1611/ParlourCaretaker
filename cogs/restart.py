import discord
import logging
import os
import sys
import subprocess
import platform
from discord import app_commands
from discord.ext import commands


class Restart(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mRestart\033[0m cog synced successfully.")

    @app_commands.command(name="restart", description="Restarts the bot.")
    async def restart(self, interaction: discord.Interaction):
        """Handles bot restart based on the operating system."""
        embed = discord.Embed(
            title="Restarting Bot...",
            description="The bot is restarting. Please wait.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Detect OS
        system_os = platform.system()

        try:
            if system_os == "Linux":
                # Restart monitor.service on Linux
                subprocess.run(["sudo", "systemctl", "restart", "monitor.service"], check=True)
                logging.info("Restart command issued successfully via systemctl.")

            elif system_os == "Windows":
                # Restart using os.execv on Windows
                logging.info("Restarting bot using os.execv on Windows...")
                os.execv(sys.executable, [sys.executable] + sys.argv)  # Restart bot script

        except Exception as e:
            logging.error(f"Failed to restart: {e}")
            error_embed = discord.Embed(
                title="Restart Failed",
                description=f"Error: `{e}`",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Restart(bot))
