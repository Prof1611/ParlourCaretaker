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

    @app_commands.command(name="dm", description="Sends a specified user a custom message via DM.")
    async def dm(self, interaction: discord.Interaction, user_input: str, *, message: str):
        """Send a DM to a user using either their ID or username (works for non-server members too)."""
        
        member = None

        try:
            if user_input.isdigit():  # If the input is a number, assume it's a user ID
                member = interaction.guild.get_member(int(user_input))  # Check if they are in the server
                if not member:
                    member = await self.bot.fetch_user(int(user_input))  # Fetch globally if not in server
            else:
                member = discord.utils.get(interaction.guild.members, name=user_input)

        except discord.NotFound:
            logging.error("User not found.")
        except discord.HTTPException as e:
            logging.error(f"Error retrieving user: {e}")

        if not member:
            embed = discord.Embed(
                title="Error",
                description="User not found. Please provide a valid username or ID.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Prevent the bot from DMing itself
        if member == self.bot.user:
            embed = discord.Embed(
                title="Error",
                description="The bot cannot send a direct message to itself.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Defer response to avoid timeout issues
        await interaction.response.defer()

        try:
            await member.send(message)
            logging.info(f"Direct message successfully sent to '{member.name}'.")
            embed = discord.Embed(
                title="Direct Message Sent",
                description=f"Successfully sent message to {member.mention} via DM.",
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.Forbidden:
            embed = discord.Embed(
                title="Error",
                description=f"Failed to send a DM to {member.mention}. They might have DMs disabled.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)

        except discord.HTTPException as e:
            logging.error(f"Error sending DM to '{member.name}'. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"An unexpected error occurred while sending a DM to {member.mention}.",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Dm(bot))
