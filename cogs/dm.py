import discord
import logging
from discord.ext import commands
from discord import app_commands


class DMModal(discord.ui.Modal, title="Send a Direct Message"):
    user_input = discord.ui.TextInput(
        label="Username or User ID", style=discord.TextStyle.short, required=True
    )
    message_input = discord.ui.TextInput(
        label="Message", style=discord.TextStyle.long, required=True
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mDM\033[0m cog synced successfully.")

    async def on_submit(self, interaction: discord.Interaction):
        user_input_value = self.user_input.value.strip()
        message_value = self.message_input.value

        # Try to fetch or locate the user
        member = None
        if user_input_value.isdigit():
            member = interaction.guild.get_member(int(user_input_value))
            if not member:
                member = await self.bot.fetch_user(int(user_input_value))
        else:
            member = discord.utils.get(interaction.guild.members, name=user_input_value)

        if not member:
            logging.error(f"User not found.")
            embed = discord.Embed(
                title="Error",
                description=f"User not found.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # Send the DM
        try:
            await member.send(content=message_value)
            logging.info(f"Direct message successfully sent to '{member.mention}'.")
            embed = discord.Embed(
                title="DM Sent",
                description=f"Direct message successfully sent to {member.mention}!",
                color=discord.Color.green(),
            )
            await interaction.followup.send(embed=embed)

        except discord.Forbidden as e:
            logging.error(f"Could not send a direct message (forbidden). Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"Failed to send the direct message.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class Dm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dm", description="Send a custom direct message to a user."
    )
    async def dm_command(self, interaction: discord.Interaction):
        modal = DMModal(self.bot)
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dm(bot))
