import re
import discord
import logging
from discord import app_commands, AllowedMentions
from discord.ext import commands
import asyncio
import datetime


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("audit.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        logging.error(f"Failed to write to audit.log: {e}")


def make_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


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
                description="Send as an embed message with colour options.",
            ),
        ]
        super().__init__(
            placeholder="Choose message format...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Store the selected format in the view and continue the flow.
        self.view.selected_format = self.values[0]

        # Normal message path: open the standard modal to collect the message.
        if self.view.selected_format == "normal":
            await interaction.response.send_modal(
                MessageModal(
                    interaction.client,
                    self.view.target_channel,
                    self.view.selected_format,
                )
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) selected 'normal' for channel #{self.view.target_channel.name} (ID: {self.view.target_channel.id})."
            )
            return

        # Embed path: first let the user choose an embed colour, then collect title and description.
        try:
            # Permissions check for embeds before proceeding
            perms = self.view.target_channel.permissions_for(interaction.guild.me)
            if not (perms.send_messages and perms.embed_links):
                error = make_embed(
                    "Error",
                    f"I need send_messages and embed_links in {self.view.target_channel.mention}.",
                    discord.Color.red(),
                )
                await interaction.response.send_message(embed=error, ephemeral=True)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) attempted embed in #{self.view.target_channel.name} without sufficient permissions."
                )
                return

            colour_view = ColourPickView(self.view.target_channel)
            await interaction.response.send_message(
                "Choose a colour for your embed:", view=colour_view, ephemeral=True
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) selected 'embed' for channel #{self.view.target_channel.name} (ID: {self.view.target_channel.id})."
            )
        except Exception as e:
            logging.warning(f"MessageFormatSelect callback error: {e}")
            audit_log(f"Error processing message format selection: {e}")
            error = make_embed(
                "Error", f"Unexpected error:\n`{e}`", discord.Color.red()
            )
            # Try to respond, or fall back to followup if already responded
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error, ephemeral=True)
            else:
                await interaction.followup.send(embed=error, ephemeral=True)


class MessageFormatView(discord.ui.View):
    def __init__(self, target_channel: discord.TextChannel):
        super().__init__()
        self.target_channel = target_channel
        self.selected_format = "normal"
        self.add_item(MessageFormatSelect())


# --- Modal for normal message input ---
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
        # Allow user and role mentions when sending
        allowed = AllowedMentions(users=True, roles=True)

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
            await self.target_channel.send(
                message_value,
                allowed_mentions=allowed,
            )
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


# ===== Embed colour picking components (adapted from CustomEmbed) =====


# Dropdown to choose embed colour first (24 options + custom)
class ColourSelect(discord.ui.Select):
    def __init__(self, parent_view: "ColourPickView"):
        options = [
            discord.SelectOption(
                label="Default", value="default", description="Black (#000000)"
            ),
            discord.SelectOption(
                label="Custom Hex",
                value="custom_hex",
                description="Enter your own hex code…",
            ),
            discord.SelectOption(
                label="Random", value="random", description="Pick a random colour"
            ),
            discord.SelectOption(
                label="Teal", value="teal", description="Aloha (#1ABC9C)"
            ),
            discord.SelectOption(
                label="Dark Teal", value="dark_teal", description="Blue Green (#11806A)"
            ),
            discord.SelectOption(
                label="Green", value="green", description="UFO Green (#2ECC71)"
            ),
            discord.SelectOption(
                label="Blurple", value="blurple", description="Blue Genie (#5865F2)"
            ),
            discord.SelectOption(
                label="OG Blurple",
                value="og_blurple",
                description="Zeus' Temple (#7289DA)",
            ),
            discord.SelectOption(
                label="Blue", value="blue", description="Dayflower (#3498DB)"
            ),
            discord.SelectOption(
                label="Dark Blue", value="dark_blue", description="Deep Water (#206694)"
            ),
            discord.SelectOption(
                label="Purple", value="purple", description="Deep Lilac (#9B59B6)"
            ),
            discord.SelectOption(
                label="Dark Purple",
                value="dark_purple",
                description="Maximum Purple (#71368A)",
            ),
            discord.SelectOption(
                label="Magenta", value="magenta", description="Mellow Melon (#E91E63)"
            ),
            discord.SelectOption(
                label="Dark Magenta",
                value="dark_magenta",
                description="Plum Perfect (#AD1457)",
            ),
            discord.SelectOption(
                label="Gold", value="gold", description="Tanned Leather (#F1C40F)"
            ),
            discord.SelectOption(
                label="Dark Gold", value="dark_gold", description="Tree Sap (#C27C0E)"
            ),
            discord.SelectOption(
                label="Orange", value="orange", description="Dark Cheddar (#E67E22)"
            ),
            discord.SelectOption(
                label="Dark Orange",
                value="dark_orange",
                description="Pepperoni (#A84300)",
            ),
            discord.SelectOption(
                label="Red", value="red", description="Carmine Pink (#E74C3C)"
            ),
            discord.SelectOption(
                label="Dark Red", value="dark_red", description="Red Birch (#992D22)"
            ),
            discord.SelectOption(
                label="Greyple", value="greyple", description="Irogon Blue (#99AAB5)"
            ),
            discord.SelectOption(
                label="Light Grey",
                value="light_grey",
                description="Harrison Grey (#979C9F)",
            ),
            discord.SelectOption(
                label="Darker Grey",
                value="darker_grey",
                description="Morro Bay (#546E7A)",
            ),
            discord.SelectOption(
                label="Dark Theme",
                value="dark_theme",
                description="Antarctic Deep (transparent)",
            ),
            discord.SelectOption(
                label="Yellow", value="yellow", description="Corn (#FEE75C)"
            ),
        ]
        super().__init__(
            placeholder="Choose an embed colour…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        try:
            if choice == "custom_hex":
                await interaction.response.send_modal(
                    HexContentModal(self.parent_view.channel)
                )
            else:
                # Support for 'random' which is a valid discord.Color method
                colour_method = getattr(discord.Color, choice)
                self.parent_view.chosen_colour = colour_method()
                await interaction.response.send_modal(
                    ContentModal(
                        self.parent_view.channel, self.parent_view.chosen_colour
                    )
                )
            audit_log(
                f"{interaction.user} chose colour '{choice}' for #{self.parent_view.channel.name}."
            )
        except Exception as e:
            logging.warning(f"ColourSelect.callback failed on choice '{choice}': {e}")
            audit_log(f"Error processing colour choice '{choice}': {e}")
            # Fallback to default colour
            self.parent_view.chosen_colour = discord.Color.default()
            await interaction.response.send_modal(
                ContentModal(self.parent_view.channel, discord.Color.default())
            )


class ColourPickView(discord.ui.View):
    def __init__(self, channel: discord.TextChannel):
        super().__init__(timeout=60)
        self.channel = channel
        self.chosen_colour = discord.Color.default()
        self.add_item(ColourSelect(self))

    async def on_timeout(self):
        logging.info(f"ColourPickView timed out in #{self.channel.name}")
        audit_log(f"Colour pick dropdown timed out in #{self.channel.name}.")
        for child in self.children:
            child.disabled = True


class ContentModal(discord.ui.Modal, title="Write your embed"):
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        required=True,
        placeholder="Title…",
    )
    embed_message = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Your message…",
    )

    def __init__(self, channel: discord.TextChannel, colour: discord.Color):
        super().__init__()
        self.channel = channel
        self.colour = colour

    async def on_submit(self, interaction: discord.Interaction):
        # Mentions allowed: users and roles
        allowed = AllowedMentions(users=True, roles=True)

        # Check permissions before sending
        perms = self.channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            error = make_embed(
                "Error",
                f"I need send_messages and embed_links in {self.channel.mention}.",
                discord.Color.red(),
            )
            await interaction.response.send_message(embed=error, ephemeral=True)
            audit_log(
                f"{interaction.user} attempted to send embed in #{self.channel.name} without sufficient permissions."
            )
            return

        embed = discord.Embed(
            title=self.embed_title.value,
            description=self.embed_message.value,
            color=self.colour,
        )
        try:
            await self.channel.send(embed=embed, allowed_mentions=allowed)
            audit_log(
                f"{interaction.user} sent embed '{self.embed_title.value}' in #{self.channel.name} with colour {self.colour}."
            )
            success = make_embed(
                "Embed sent!", "Custom embed sent successfully.", discord.Color.green()
            )
            await interaction.response.send_message(embed=success, ephemeral=True)
        except discord.Forbidden:
            logging.error(f"No permission to send embed in #{self.channel.name}")
            audit_log(f"{interaction.user} lacked permissions in #{self.channel.name}.")
            error = make_embed(
                "Error",
                f"I don't have permission to send embeds in {self.channel.mention}.",
                discord.Color.red(),
            )
            await interaction.response.send_message(embed=error, ephemeral=True)
        except Exception as e:
            logging.error(f"ContentModal.on_submit error: {e}")
            audit_log(f"Error sending embed: {e}")
            error = make_embed(
                "Error", f"Unexpected error:\n`{e}`", discord.Color.red()
            )
            await interaction.response.send_message(embed=error, ephemeral=True)


class HexContentModal(discord.ui.Modal, title="Custom HEX Embed"):
    hex_code = discord.ui.TextInput(
        label="HEX Code",
        style=discord.TextStyle.short,
        required=True,
        placeholder="#RRGGBB or RRGGBB",
        max_length=7,
    )
    embed_title = discord.ui.TextInput(
        label="Embed Title",
        style=discord.TextStyle.short,
        required=True,
        placeholder="Title…",
    )
    embed_message = discord.ui.TextInput(
        label="Description",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Your message…",
    )

    def __init__(self, channel: discord.TextChannel):
        super().__init__()
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        # Mentions allowed: users and roles
        allowed = AllowedMentions(users=True, roles=True)

        hex_str = self.hex_code.value.strip().lstrip("#")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", hex_str):
            audit_log(
                f"{interaction.user} provided invalid hex '{self.hex_code.value}'."
            )
            error = make_embed(
                "Error",
                "Invalid hex code. Must be exactly 6 hex digits.",
                discord.Color.red(),
            )
            return await interaction.response.send_message(embed=error, ephemeral=True)

        colour = discord.Color(int(hex_str, 16))

        # Check permissions before sending
        perms = self.channel.permissions_for(interaction.guild.me)
        if not (perms.send_messages and perms.embed_links):
            error = make_embed(
                "Error",
                f"I need send_messages and embed_links in {self.channel.mention}.",
                discord.Color.red(),
            )
            await interaction.response.send_message(embed=error, ephemeral=True)
            audit_log(
                f"{interaction.user} attempted to send custom hex embed in #{self.channel.name} without sufficient permissions."
            )
            return

        embed = discord.Embed(
            title=self.embed_title.value,
            description=self.embed_message.value,
            color=colour,
        )
        try:
            await self.channel.send(embed=embed, allowed_mentions=allowed)
            audit_log(
                f"{interaction.user} sent custom embed '{self.embed_title.value}' in #{self.channel.name}."
            )
            success = make_embed(
                "Embed sent!", "Custom embed sent successfully.", discord.Color.green()
            )
            await interaction.response.send_message(embed=success, ephemeral=True)
        except discord.Forbidden:
            logging.error(f"No permission to send custom embed in #{self.channel.name}")
            audit_log(f"{interaction.user} lacked permissions in #{self.channel.name}.")
            error = make_embed(
                "Error",
                f"I don't have permission to send embeds in {self.channel.mention}.",
                discord.Color.red(),
            )
            await interaction.response.send_message(embed=error, ephemeral=True)
        except Exception as e:
            logging.error(f"HexContentModal.on_submit error: {e}")
            audit_log(f"Error sending custom embed: {e}")
            error = make_embed(
                "Error", f"Unexpected error:\n`{e}`", discord.Color.red()
            )
            await interaction.response.send_message(embed=error, ephemeral=True)


# ===== Cog tying everything together =====
class Message(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="message",
        description="Sends a custom message in a specified channel. Choose normal text or a coloured embed.",
    )
    @app_commands.describe(channel="The channel in which to send the custom message.")
    async def message_command(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        try:
            # Basic permission check for ability to send messages at all
            perms = channel.permissions_for(interaction.guild.me)
            if not perms.send_messages:
                error = make_embed(
                    "Error",
                    f"I need send_messages permission in {channel.mention}.",
                    discord.Color.red(),
                )
                await interaction.response.send_message(embed=error, ephemeral=True)
                audit_log(
                    f"{interaction.user.name} (ID: {interaction.user.id}) invoked /message but lacked send_messages in #{channel.name}."
                )
                return

            view = MessageFormatView(channel)
            await interaction.response.send_message(
                "Choose the message format:", view=view, ephemeral=True
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) invoked message command for channel #{channel.name} (ID: {channel.id})."
            )
        except Exception as e:
            logging.error(f"Error in /message: {e}")
            audit_log(f"Unexpected error in /message: {e}")
            error = make_embed(
                "Error", f"Unexpected error:\n`{e}`", discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=error, ephemeral=True)
            else:
                await interaction.followup.send(embed=error, ephemeral=True)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mMessage\033[0m cog synced successfully.")
        audit_log("Message cog synced successfully.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Message(bot))
