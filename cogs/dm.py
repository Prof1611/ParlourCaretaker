import discord
import logging
from discord.ext import commands
from discord import app_commands

class DMModal(discord.ui.Modal, title="Send a DM"):
    # Define text inputs here
    user_input = discord.ui.TextInput(
        label="User ID or Username",
        style=discord.TextStyle.short,
        required=True,
        placeholder="Enter user ID or username",
        max_length=50
    )
    message_input = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter the message you want to send",
        max_length=2000
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        """When the user submits the modal, this method is called."""
        user_input_value = self.user_input.value.strip()
        message_value = self.message_input.value

        # Try to find the user by ID or username
        member = None
        try:
            if user_input_value.isdigit():
                # If it's all digits, treat as user ID
                member = interaction.guild.get_member(int(user_input_value))
                if not member:
                    # If not found in guild, try a global fetch
                    member = await self.bot.fetch_user(int(user_input_value))
            else:
                # Otherwise, treat as a username (only works if they share a guild)
                member = discord.utils.get(interaction.guild.members, name=user_input_value)
        except discord.NotFound:
            return await interaction.response.send_message(
                "User not found. Please provide a valid username or ID.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logging.error(f"Error retrieving user: {e}")
            return await interaction.response.send_message(
                "An error occurred while trying to find that user.",
                ephemeral=True
            )

        # If still not found, let the user know
        if not member:
            return await interaction.response.send_message(
                "Could not locate that user in this guild or via fetch.",
                ephemeral=True
            )

        # Prevent the bot from DMing itself
        if member == self.bot.user:
            return await interaction.response.send_message(
                "I can't DM myself, sorry!",
                ephemeral=True
            )

        # Attempt to send the DM
        try:
            embed_dm = discord.Embed(description=message_value, color=discord.Color.blue())
            await member.send(embed=embed_dm)
            await interaction.response.send_message(
                f"Successfully sent message to {member.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"Failed to send a DM to {member.mention}. They might have DMs disabled.",
                ephemeral=True
            )
        except discord.HTTPException as e:
            logging.error(f"Error sending DM to '{member.name}': {e}")
            await interaction.response.send_message(
                "An unexpected error occurred while sending the DM.",
                ephemeral=True
            )

class Dm(commands.Cog):
    """A Cog that contains the slash command to open the DM Modal."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(name="dm", description="Open a form to send a custom DM.")
    async def dm_command(self, interaction: discord.Interaction):
        """Slash command that opens the modal."""
        modal = DMModal(self.bot)
        await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(Dm(bot))
