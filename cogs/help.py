import discord
import logging
from discord import app_commands
from discord.ext import commands
import datetime


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mHelp\033[0m cog synced successfully.")
        audit_log("Help cog synced successfully.")

    @app_commands.command(name="help", description="Sends a list of all commands.")
    async def message(self, interaction: discord.Interaction):
        # Defer the response to avoid timeout errors.
        await interaction.response.defer()

        embed_msg = discord.Embed(
            title="List of Commands:", description="", color=discord.Color.blurple()
        )

        for slash_command in self.bot.tree.walk_commands():
            # Fallback to the command name in case the command description is not defined.
            embed_msg.add_field(
                name=slash_command.name,
                value=(
                    slash_command.description
                    if slash_command.description
                    else slash_command.name
                ),
                inline=False,
            )

        try:
            await interaction.followup.send(embed=embed_msg)
            logging.info(
                f"Successfully sent help message in #{interaction.channel.name} (ID: {interaction.channel.id})."
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) invoked /help command in channel #{interaction.channel.name} (ID: {interaction.channel.id})."
            )
        except discord.HTTPException as e:
            logging.error(
                f"Error when attempting to send help message in #{interaction.channel.name} (ID: {interaction.channel.id}). Error: {e}"
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) encountered error sending /help command in channel #{interaction.channel.name} (ID: {interaction.channel.id}): {e}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
