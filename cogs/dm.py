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

    async def on_submit(self, interaction: discord.Interaction):
        user_input_value = self.user_input.value.strip()
        message_value = self.message_input.value

        # Try to fetch or locate the user from the guild.
        if not interaction.guild:
            embed = discord.Embed(
                title="Error",
                description="This command must be used in a server.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        member = None
        if user_input_value.isdigit():
            member = interaction.guild.get_member(int(user_input_value))
            if not member:
                try:
                    member = await self.bot.fetch_user(int(user_input_value))
                except Exception as e:
                    logging.error(f"Error fetching user by ID: {e}")
        else:
            member = discord.utils.get(interaction.guild.members, name=user_input_value)

        if not member:
            logging.error("User not found.")
            embed = discord.Embed(
                title="Error",
                description="User not found.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Send the DM
        try:
            await member.send(content=message_value)
            logging.info(f"Direct message successfully sent to '{member.name}'.")
            embed = discord.Embed(
                title="DM Sent",
                description=f"Direct message successfully sent to {member.mention}!",
                color=discord.Color.green(),
            )
        except discord.Forbidden as e:
            logging.error(f"Could not send a direct message (forbidden). Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Failed to send the direct message (forbidden).",
                color=discord.Color.red(),
            )
        except Exception as e:
            logging.error(f"Unexpected error while sending DM: {e}")
            embed = discord.Embed(
                title="Error",
                description="An unexpected error occurred while sending the DM.",
                color=discord.Color.red(),
            )

        # Respond to the interaction.
        # Use interaction.response.send_message if not already responded to,
        # otherwise use followup.send.
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(embed=embed)


class Dm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dm", description="Send a custom direct message to a user."
    )
    async def dm_command(self, interaction: discord.Interaction):
        modal = DMModal(self.bot)
        await interaction.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[35mDM\033[0m cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Dm(bot))
