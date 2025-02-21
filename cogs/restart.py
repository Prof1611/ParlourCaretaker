import discord
import logging
import subprocess
from discord import app_commands
from discord.ext import commands


class Restart(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="restart", description="Restarts the bot service.")
    async def restart(self, interaction: discord.Interaction):
        """Restarts the bot service using systemctl."""
        await interaction.response.defer()

        try:
            # Run the restart command
            subprocess.run(["sudo", "systemctl", "restart", "monitor.service"], check=True)

            embed = discord.Embed(
                title="Restarting Bot",
                description="The bot service is restarting...",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed)

            logging.info("Bot service restarted successfully.")

        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to restart bot service: {e}")

            embed = discord.Embed(
                title="Restart Failed",
                description="Could not restart the bot service. Check system logs for details.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Restart(bot))
