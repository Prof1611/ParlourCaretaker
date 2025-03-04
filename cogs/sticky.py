import discord
import logging
import json
import asyncio
from discord import app_commands
from discord.ext import commands

# --- Dropdown (Select) and View to choose sticky format ---


class StickyFormatSelect(discord.ui.Select):
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
                description="Send as an embed with the title 'Sticky Message'.",
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
            StickyModal(
                interaction.client, self.view.sticky_cog, self.view.selected_format
            )
        )


class StickyFormatView(discord.ui.View):
    def __init__(self, sticky_cog: "Sticky"):
        super().__init__()
        self.sticky_cog = sticky_cog
        self.selected_format = "normal"
        self.add_item(StickyFormatSelect())


# --- Modal for multi-line sticky message input ---
class StickyModal(discord.ui.Modal, title="Set Sticky Message"):
    sticky_message = discord.ui.TextInput(
        label="Sticky Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your sticky message here...",
    )

    def __init__(self, bot: commands.Bot, sticky_cog: "Sticky", selected_format: str):
        super().__init__()
        self.bot = bot
        self.sticky_cog = sticky_cog
        self.selected_format = selected_format

    async def on_submit(self, interaction: discord.Interaction):
        content = self.sticky_message.value
        channel = interaction.channel

        # If an old sticky exists, delete it.
        if channel.id in self.sticky_cog.stickies:
            previous_sticky = self.sticky_cog.stickies[channel.id]
            try:
                old_message = await channel.fetch_message(previous_sticky["message_id"])
                await old_message.delete()
            except discord.NotFound:
                logging.warning(f"Old sticky not found in #{channel}.")
            except Exception as e:
                logging.error(f"Error deleting old sticky in #{channel}: {e}")

        try:
            if self.selected_format == "embed":
                embed = discord.Embed(
                    title="Sticky Message",
                    description=content,
                    color=discord.Color.blurple(),
                )
                sticky_msg = await channel.send(embed=embed)
            else:
                sticky_msg = await channel.send(content)

            # Store the sticky details (content, message ID, and format).
            self.sticky_cog.stickies[channel.id] = {
                "content": content,
                "message_id": sticky_msg.id,
                "format": self.selected_format,
            }
            self.sticky_cog.save_stickies()

            logging.info(f"Sticky message successfully set in #{channel}")
            embed = discord.Embed(
                title="Sticky Message Set",
                description=f"Sticky message successfully set in #{channel}!",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.HTTPException as e:
            await self.sticky_cog.handle_error(e, channel, interaction)


# --- Sticky Cog ---
class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # key: channel id, value: {"content": str, "message_id": int, "format": "normal" or "embed"}
        self.stickies = {}
        self.load_stickies()
        self.initialised = False  # Guard flag

        # For ensuring only one sticky update per channel at a time.
        self.locks = {}  # channel_id: asyncio.Lock

        # For debouncing updates to avoid flooding API calls.
        self.debounce_tasks = {}  # channel_id: asyncio.Task
        self.debounce_interval = 1.0  # seconds

    def load_stickies(self):
        """Load sticky messages from a JSON file."""
        try:
            with open("stickies.json", "r") as f:
                self.stickies = json.load(f)
                if not self.stickies:
                    self.stickies = {}
                    self.save_stickies()
        except (FileNotFoundError, json.JSONDecodeError):
            self.stickies = {}
            self.save_stickies()

    def save_stickies(self):
        """Save the current sticky messages to a JSON file."""
        saved_stickies = {
            str(channel_id): {
                "content": data["content"],
                "message_id": data["message_id"],
                "format": data.get("format", "normal"),
            }
            for channel_id, data in self.stickies.items()
        }
        try:
            with open("stickies.json", "w") as f:
                json.dump(saved_stickies, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save stickies to file: {e}")

    async def update_sticky_for_channel(
        self, channel: discord.abc.Messageable, sticky: dict, force_update: bool = False
    ):
        """
        Update the sticky message in the channel only if the stored sticky is not the latest message.
        """
        # Check that the channel is a text channel.
        if not isinstance(channel, discord.TextChannel):
            logging.warning(
                f"Channel {channel} is not a TextChannel. Skipping sticky update."
            )
            return

        # Check for necessary permissions.
        permissions = channel.permissions_for(channel.guild.me)
        if not (permissions.send_messages and permissions.manage_messages):
            logging.warning(
                f"Insufficient permissions in channel #{channel.name}. Skipping sticky update."
            )
            return

        # Use a per-channel lock to avoid concurrent updates.
        lock = self.locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            # Fetch the latest message in the channel.
            history = [msg async for msg in channel.history(limit=1)]
            if history and not force_update:
                last_message = history[0]
                # Check if the last message is our stored sticky message.
                if last_message.id == sticky["message_id"]:
                    return

            try:
                # Attempt to delete the previous sticky message.
                try:
                    old_message = await channel.fetch_message(sticky["message_id"])
                    await old_message.delete()
                except discord.NotFound:
                    logging.warning(f"Old sticky not found in channel #{channel.name}.")
                except Exception as e:
                    logging.error(
                        f"Error deleting old sticky in channel #{channel.name}: {e}"
                    )

                # Send a new sticky message.
                fmt = sticky.get("format", "normal")
                new_sticky = await self._send_sticky(channel, sticky["content"], fmt)
                self.stickies[channel.id] = {
                    "content": sticky["content"],
                    "message_id": new_sticky.id,
                    "format": fmt,
                }
                self.save_stickies()
            except Exception as e:
                logging.error(f"Error updating sticky in channel #{channel.name}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        # On startup, update sticky messages only if needed.
        logging.info("\033[35mSticky\033[0m cog synced successfully.")
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await self.update_sticky_for_channel(
                    channel, sticky, force_update=False
                )
        self.initialised = True

    @commands.Cog.listener()
    async def on_resumed(self):
        logging.info("Bot resumed. Updating sticky messages in all channels.")
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await self.update_sticky_for_channel(
                    channel, sticky, force_update=False
                )
        self.initialised = True

    async def _send_sticky(self, channel: discord.TextChannel, content: str, fmt: str):
        """Helper method to send a sticky message in the chosen format."""
        if fmt == "embed":
            embed = discord.Embed(
                title="Sticky Message",
                description=content,
                color=discord.Color.blurple(),
            )
            return await channel.send(embed=embed)
        else:
            return await channel.send(content)

    @app_commands.command(
        name="setsticky",
        description="Set a sticky message in the current channel.",
    )
    async def set_sticky(self, interaction: discord.Interaction):
        """Open a modal form to set the sticky message for the current channel."""
        view = StickyFormatView(self)
        await interaction.response.send_message(
            "Choose the sticky message format:", view=view, ephemeral=True
        )

    @app_commands.command(
        name="removesticky",
        description="Remove the sticky message from the current channel.",
    )
    async def remove_sticky(self, interaction: discord.Interaction):
        """Remove the sticky message for the current channel."""
        await interaction.response.defer()
        channel = interaction.channel
        if channel.id not in self.stickies:
            embed = discord.Embed(
                title="No Sticky Message",
                description=f"There is no sticky message set in #{channel}.",
                color=discord.Color.red(),
            )
            confirmation = await interaction.followup.send(embed=embed)
            await asyncio.sleep(3)
            await confirmation.delete()
            return

        sticky = self.stickies[channel.id]
        try:
            old_message = await channel.fetch_message(sticky["message_id"])
            await old_message.delete()
        except discord.NotFound:
            logging.warning(
                f"Sticky message not found in channel {channel.name} during removal."
            )
        except Exception as e:
            logging.error(f"Error deleting sticky in channel {channel.name}: {e}")

        del self.stickies[channel.id]
        self.save_stickies()

        embed = discord.Embed(
            title="Sticky Removed",
            description=f"Sticky message successfully removed from #{channel}.",
            color=discord.Color.green(),
        )
        confirmation = await interaction.followup.send(embed=embed)
        await asyncio.sleep(3)
        await confirmation.delete()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Ensure the sticky message stays as the latest message in the channel."""
        if message.author == self.bot.user:
            return

        channel = message.channel
        if channel.id in self.stickies:
            # Instead of updating immediately, debounce the update.
            if channel.id in self.debounce_tasks:
                return
            self.debounce_tasks[channel.id] = self.bot.loop.create_task(
                self._debounced_update(channel, self.stickies[channel.id])
            )

    async def _debounced_update(self, channel: discord.abc.Messageable, sticky: dict):
        try:
            await asyncio.sleep(self.debounce_interval)
            await self.update_sticky_for_channel(channel, sticky, force_update=False)
        finally:
            self.debounce_tasks.pop(channel.id, None)

    async def handle_error(self, e, channel, interaction):
        """Handle error cases and send an appropriate response."""
        if e.status == 403:
            logging.error(f"No access to #{channel}. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"I don't have access to #{channel}!",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status == 404:
            logging.error(f"Channel not found. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status == 429:
            logging.error(f"RATE LIMIT. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Too many requests! Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status in {500, 502, 503, 504}:
            logging.error(f"Discord API Error. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel}. Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        else:
            logging.error(
                f"Error when attempting to set sticky message in #{channel}. Error: {e}"
            )
            embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel}.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Sticky(bot))
