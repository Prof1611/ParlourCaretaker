import discord
import logging
from discord import app_commands
from discord.ext import commands
import asyncio
import datetime


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


# --- Dropdown (Select) and View to choose message format ---
class MessageFormatSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Normal",
                value="normal",
                description="Send as a normal text message.",
            ),
            discord.SelectOption(
                label="Embed",
                value="embed",
                description="Send as an embed message.",
            ),
        ]
        super().__init__(
            placeholder="Choose message format...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Store the selected format in the view and open the modal.
        self.view.selected_format = self.values[0]
        await interaction.response.send_modal(
            MessageModal(
                interaction.client, self.view.target_channel, self.view.selected_format
            )
        )
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) selected message format '{self.values[0]}' for channel #{self.view.target_channel.name} (ID: {self.view.target_channel.id})."
        )


class MessageFormatView(discord.ui.View):
    def __init__(self, target_channel: discord.TextChannel):
        super().__init__()
        self.target_channel = target_channel
        self.selected_format = "normal"
        self.add_item(MessageFormatSelect())


# --- Modal for message input ---
class MessageModal(discord.ui.Modal, title="Send a Custom Message"):
    def __init__(
        self,
        bot: commands.Bot,
        target_channel: discord.TextChannel,
        selected_format: str,
    ):
        super().__init__()
        self.bot = bot
        self.target_channel = target_channel
        self.selected_format = selected_format

        # If the embed format is chosen, add the embed title input first, then the message input.
        if self.selected_format == "embed":
            self.embed_title_input = discord.ui.TextInput(
                label="Embed Title",
                style=discord.TextStyle.short,
                required=True,
                placeholder="Enter a title for the embed...",
                custom_id=f"embed_title_input_{target_channel.id}",
            )
            self.message_input = discord.ui.TextInput(
                label="Message",
                style=discord.TextStyle.long,
                required=True,
                placeholder="Enter your message here...",
                custom_id=f"message_input_{target_channel.id}",
            )
            self.add_item(self.embed_title_input)
            self.add_item(self.message_input)
        else:
            # For normal messages, only add the message input.
            self.message_input = discord.ui.TextInput(
                label="Message",
                style=discord.TextStyle.long,
                required=True,
                placeholder="Enter your message here...",
                custom_id=f"message_input_{target_channel.id}",
            )
            self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        message_value = self.message_input.value
        embed_title = (
            self.embed_title_input.value if self.selected_format == "embed" else None
        )

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
            error_embed = discord.Embed(
                title="Error",
                description="Target channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message: target channel not found."
            )
            return

        # Attempt to send the custom message.
        try:
            if self.selected_format == "embed":
                embed = discord.Embed(
                    title=embed_title,
                    description=message_value,
                    color=discord.Color.blurple(),
                )
                await self.target_channel.send(embed=embed)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) sent custom embed message in channel #{self.target_channel.name} (ID: {self.target_channel.id}) with title '{embed_title}'."
                )
            else:
                await self.target_channel.send(message_value)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) sent custom normal message in channel #{self.target_channel.name} (ID: {self.target_channel.id})."
                )
            logging.info(
                f"Custom message successfully sent in #{self.target_channel.name}."
            )
            success_embed = discord.Embed(
                title="Custom Message Sent",
                description=f"Successfully sent message in {self.target_channel.mention}.",
                color=discord.Color.green(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=success_embed
            )
        except discord.HTTPException as e:
            await self.handle_error(e, original_response, interaction)

    async def handle_error(self, e, original_response, interaction):
        """Handle different error types and send the appropriate response."""
        if e.status == 403:  # No access to channel
            logging.error(f"No access to #{self.target_channel.name}. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description=f"I don't have access to {self.target_channel.mention}!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message: no access to channel #{self.target_channel.name} (ID: {self.target_channel.id})."
            )
        elif e.status == 404:  # Channel not found
            logging.error(f"Channel not found. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message: channel #{self.target_channel.name} (ID: {self.target_channel.id}) not found."
            )
        elif e.status == 429:  # Rate limit hit
            logging.error(f"RATE LIMIT. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Too many requests! Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message: rate limited in channel #{self.target_channel.name} (ID: {self.target_channel.id})."
            )
        elif e.status in {500, 502, 503, 504}:  # Discord API error
            logging.error(f"Discord API Error. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description=f"Failed to send custom message in {self.target_channel.mention}. Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message: Discord API error in channel #{self.target_channel.name} (ID: {self.target_channel.id})."
            )
        else:  # Other errors
            logging.error(
                f"Error when attempting to send custom message in #{self.target_channel.name}. Error: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description=f"Failed to send custom message in {self.target_channel.mention}.",
                color=discord.Color.red(),
            )
            await interaction.followup.edit_message(
                message_id=original_response.id, content="", embed=error_embed
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) failed to send custom message in channel #{self.target_channel.name} (ID: {self.target_channel.id}): {e}"
            )


class Message(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="message", description="Sends a custom message in a specified channel."
    )
    @app_commands.describe(channel="The channel in which to send the custom message.")
    async def message_command(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        view = MessageFormatView(channel)
        await interaction.response.send_message(
            "Choose the message format:", view=view, ephemeral=True
        )
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) invoked message command for channel #{channel.name} (ID: {channel.id})."
        )

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mMessage\033[0m cog synced successfully.")
        audit_log("Message cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Message(bot))
