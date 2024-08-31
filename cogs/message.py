import discord
import logging
from discord import app_commands
from discord.ext import commands


class Message(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="message", description="Test description.")
    async def message(self, interaction: discord.Interaction):
        await interaction.response.send_message("Test message.")


async def setup(bot):
    await bot.add_cog(Message(bot))
