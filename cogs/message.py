import discord
import logging
from discord import app_commands
from discord.ext import commands
import asyncio


class MessageModal(discord.ui.Modal, title="Send a Custom Message"):
    message_input = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your message here (multiline supported)...",
    )

    def __init__(self, bot: commands.Bot, target_channel: discord.TextChannel):
        super().__init__()
        self.bot = bot
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        message_value = self.message_input.value

        # Send a processing embed immediately.
        processing_embed = discord.Embed(
            title="Processing Message",
            description="Please wait...",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=processing_embed, ephemeral=True)
        original_response = await interaction.original_response()

        # Check if the target channel is valid.
        if not self.target_channel:
            embed = discord.Embed(
                title="Error",
                description="Target channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=embed
            )
            return

        # Attempt to send the custom message.
        try:
            await self.target_channel.send(message_value)
            logging.info(
                f"Custom message successfully sent in {self.target_channel.name}."
            )
            embed = discord.Embed(
                title="Custom Message Sent",
                description=f"Successfully sent message in {self.target_channel.mention}.",
                color=discord.Color.green(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=embed
            )
        except discord.HTTPException as e:
            if e.status == 403:  # No access to channel
                logging.error(f"No access to {self.target_channel.name}. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"I don't have access to {self.target_channel.mention}!",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status == 404:  # Channel not found
                logging.error(f"Channel not found. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description="Channel not found!",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status == 429:  # Rate limit hit
                logging.error(f"RATE LIMIT. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description="Too many requests! Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            elif e.status in {500, 502, 503, 504}:  # Discord API error
                logging.error(f"Discord API Error. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send custom message in {self.target_channel.mention}. Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            else:  # Other errors
                logging.error(
                    f"Error when attempting to send custom message in {self.target_channel.name}. Error: {e}"
                )
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send custom message in {self.target_channel.mention}.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )


class Message(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="message", description="Sends a custom message in a specified channel."
    )
    async def message_command(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        modal = MessageModal(self.bot, channel)
        await interaction.response.send_modal(modal)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mMessage\033[0m cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Message(bot))
