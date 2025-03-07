import discord
import logging
from discord import app_commands
from discord.ext import commands


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mHelp\033[0m cog synced successfully.")

    @app_commands.command(name="help", description="Sends a list of all commands.")
    async def message(self, interaction: discord.Interaction):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        embed_msg = discord.Embed(
            title="List of Commands:",
            description="",
            color=discord.Color.blurple())

        for slash_command in self.bot.tree.walk_commands():
            # fallbacks to the command name incase command description is not defined
            embed_msg.add_field(name=slash_command.name,
                                value=slash_command.description if slash_command.description else slash_command.name, inline=False)

        # Try send the help message
        try:
            await interaction.followup.send(embed=embed_msg)
            logging.info(
                f"Successfully sent help message in #{interaction.channel.name}.")

        except discord.HTTPException as e:
            logging.error(
                f"Error when attempting to send help message in #{interaction.channel.name}. Error: {e}")


async def setup(bot):
    await bot.add_cog(Help(bot))
