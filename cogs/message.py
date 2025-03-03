import discord
import logging
from discord import app_commands
from discord.ext import commands
import asyncio

# --- Dropdown for selecting a channel ---


class ChannelSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        # Build a list of options for all text channels in the guild.
        options = []
        for channel in guild.text_channels:
            options.append(
                discord.SelectOption(label=channel.name, value=str(channel.id))
            )
        if not options:
            options.append(discord.SelectOption(label="No text channels", value="0"))
        super().__init__(
            placeholder="Select a channel...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Store the selected channel's ID in the view and open the modal.
        self.view.selected_channel_id = int(self.values[0])
        await interaction.response.send_modal(
            MessageModal(self.view.bot, self.view.selected_channel_id)
        )


class ChannelSelectView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__()
        self.bot = bot
        self.selected_channel_id: int | None = None
        self.add_item(ChannelSelect(guild))


# --- Modal for entering the message ---
class MessageModal(discord.ui.Modal, title="Send a Custom Message"):
    message_input = discord.ui.TextInput(
        label="Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your message here...",
    )

    def __init__(self, bot: commands.Bot, channel_id: int):
        super().__init__()
        self.bot = bot
        self.channel_id = channel_id

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

        # Locate the target channel.
        target_channel = interaction.guild.get_channel(self.channel_id)
        if not target_channel:
            embed = discord.Embed(
                title="Error",
                description="Channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=embed
            )
            return

        # Attempt to send the custom message with error handling.
        try:
            await target_channel.send(message_value)
            logging.info(
                f"Custom message successfully sent in '#{target_channel.name}'."
            )
            embed = discord.Embed(
                title="Custom Message Sent",
                description=f"Successfully sent message in {target_channel.mention}.",
                color=discord.Color.green(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=embed
            )
        except discord.HTTPException as e:
            if e.status == 403:  # No access to channel
                logging.error(f"No access to '#{target_channel.name}'. Error: {e}")
                embed = discord.Embed(
                    title="Error",
                    description=f"I don't have access to {target_channel.mention}!",
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
                    description=f"Failed to send custom message in {target_channel.mention}. Please try later.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )
            else:  # Other errors
                logging.error(
                    f"Error when attempting to send custom message in '#{target_channel.name}'. Error: {e}"
                )
                embed = discord.Embed(
                    title="Error",
                    description=f"Failed to send custom message in {target_channel.mention}.",
                    color=discord.Color.red(),
                )
                await interaction.followup.edit_message(
                    message_id=original_response.id, content="", embed=embed
                )


class Message(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="message",
        description="Posts a custom message in a chosen channel.",
    )
    async def message_command(self, interaction: discord.Interaction):
        # Create a dropdown view populated with all text channels in the guild.
        view = ChannelSelectView(self.bot, interaction.guild)
        await interaction.response.send_message(
            "Select the channel where you want to send the message:",
            view=view,
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[35mMessage\033[0m cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Message(bot))
