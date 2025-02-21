import discord
import logging
import os
import sys
from discord import app_commands
from discord.ext import commands


class Restart(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="restart", description="Restarts the bot.")
    async def restart(self, interaction: discord.Interaction):
        # Send a message about the restart process
        embed = discord.Embed(
            title="Restarting Bot...",
            description="The bot is restarting. Please wait.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

        # Try to restart the bot using os.execv
        try:
            os.execv(sys.executable, ["python"] + sys.argv)  # Restarts the bot script
        except Exception as e:
            logging.error(f"Failed to restart the bot. Error: {e}")
            
            # Send an error message to the user as an ephemeral message
            error_embed = discord.Embed(
                title="Error",
                description="Failed to restart the bot. Please try again later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=error_embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Restart(bot))
