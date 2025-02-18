import discord
from discord.ext import commands
from discord import app_commands

class DMModal(discord.ui.Modal, title="Send a DM"):
    user_input = discord.ui.TextInput(
        label="User ID or Username",
        style=discord.TextStyle.short,
        required=True
    )
    message_input = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.long,
        required=True
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        # Your logic to find the user and send the DM
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
            return await interaction.response.send_message(
                "User not found.", ephemeral=True
            )

        # Send the DM
        try:
            await member.send(content=message_value)
            await interaction.response.send_message(
                f"Message sent to {member.mention}!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "Could not send a DM (forbidden).", 
                ephemeral=True
            )

class Dm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="dm", description="Open a form to send a custom DM.")
    async def dm_command(self, interaction: discord.Interaction):
        """Slash command that shows a modal."""
        modal = DMModal(self.bot)
        await interaction.response.send_modal(modal)

async def setup(bot: commands.Bot):
    await bot.add_cog(Dm(bot))
