import discord
import logging
from discord.ext import commands
from discord import app_commands


class DMModal(discord.ui.Modal, title="Send a Direct Message"):
    message_input = discord.ui.TextInput(
        label="Message", style=discord.TextStyle.long, required=True
    )

    def __init__(self, bot: commands.Bot, user: discord.User):
        super().__init__()
        self.bot = bot
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        message_value = self.message_input.value

        # Create a processing embed and send it.
        processing_embed = discord.Embed(
            title="Processing DM",
            description="Please wait...",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=processing_embed, ephemeral=True)
        original_response = await interaction.original_response()

        # Attempt to send the DM.
        try:
            await self.user.send(content=message_value)
            logging.info(f"Direct message successfully sent to '{self.user.name}'.")
            embed = discord.Embed(
                title="DM Sent",
                description=f"Direct message successfully sent to {self.user.mention}!",
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

        # Edit the original processing embed with the final embed.
        await interaction.followup.edit_message(
            message_id=original_response.id, content="", embed=embed
        )


class Dm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="dm", description="Send a custom direct message to a user."
    )
    @app_commands.describe(user="The user to send the DM to")
    async def dm_command(self, interaction: discord.Interaction, user: discord.User):
        modal = DMModal(self.bot, user)
        await interaction.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mDM\033[0m cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Dm(bot))
