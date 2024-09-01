import discord
import logging
from discord import app_commands
from discord.ext import commands


class Dm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="dm", description="Sends a user a custom message via DM.")
    async def dm(self, interaction: discord.Interaction, member: discord.Member, *, message: str):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Send the notice to the member via DM
        try:
            await member.send(message)
            logging.info(
                f"Direct message successfully sent to '{member.name}'.")
            embed = discord.Embed(
                title="Direct Message Sent", description=f"Successfully sent message to {member.mention} via DM.", color=discord.Color.green())
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.HTTPException as e:
            logging.error(
                f"Error when attempting to send direct message: {e}")
            # Handle cases where the direct message cannot be sent e.g. DM disabled
            embed = discord.Embed(
                title="Error", description=f"Failed to send custom message to {member.mention} via DM.", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Dm(bot))
