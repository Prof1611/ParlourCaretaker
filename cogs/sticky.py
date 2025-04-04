import discord
import logging
import sqlite3
import asyncio
from discord import app_commands
from discord.ext import commands
import datetime

# Define an invisible marker for sticky messages using zero-width characters.
STICKY_MARKER = "\u200b\u200c\u200d\u2060"


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


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
                description="Send as an embed with title 'Sticky Message'.",
            ),
        ]
        super().__init__(
            placeholder="Choose message format...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_format = self.values[0]
        await interaction.response.send_modal(
            StickyModal(
                interaction.client, self.view.sticky_cog, self.view.selected_format
            )
        )
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) selected sticky format '{self.values[0]}' for channel #{interaction.channel.name} (ID: {interaction.channel.id})."
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

        # Early check: ensure the bot has permission to send messages (and embed links, if required).
        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages or (
            self.selected_format == "embed" and not perms.embed_links
        ):
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Error",
                    description=f"I don't have the necessary permissions to send sticky messages in #{channel.name}. Please check my permissions.",
                    color=discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        # If an old sticky exists, attempt to delete it.
        if channel.id in self.sticky_cog.stickies:
            previous_sticky = self.sticky_cog.stickies[channel.id]
            try:
                old_message = await channel.fetch_message(previous_sticky["message_id"])
                await old_message.delete()
            except discord.NotFound:
                logging.warning(f"Old sticky not found in #{channel.name}.")
            except Exception as e:
                logging.error(f"Error deleting old sticky in #{channel.name}: {e}")

        try:
            sticky_msg = await self.sticky_cog._send_sticky(
                channel, content, self.selected_format
            )
            # Update the in-memory cache and the database.
            self.sticky_cog.stickies[channel.id] = {
                "content": content,
                "message_id": sticky_msg.id,
                "format": self.selected_format,
            }
            self.sticky_cog.update_sticky_in_db(
                channel.id, content, sticky_msg.id, self.selected_format
            )
            logging.info(f"Sticky message successfully set in #{channel.name}.")
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="Sticky Message Set",
                    description=f"Sticky message successfully set in #{channel.name}!\n\nTo change it later, run `/removesticky` first.",
                    color=discord.Color.green(),
                ),
                ephemeral=True,
            )
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) set a sticky message in channel #{channel.name} (ID: {channel.id})."
            )
        except discord.HTTPException as e:
            await self.sticky_cog.handle_error(e, channel, interaction)


# --- Sticky Cog ---
class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # In-memory cache: key is channel ID, value is a dict with sticky details.
        self.stickies = {}
        # Open (or create) a connection to the same database file.
        self.db = sqlite3.connect("database.db", check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sticky_messages (channel_id INTEGER PRIMARY KEY, content TEXT, message_id INTEGER, format TEXT)"
        )
        self.db.commit()
        self.load_stickies()
        self.initialised = False  # Guard flag

        # Locks and debouncing for updates.
        self.locks = {}  # channel_id: asyncio.Lock
        self.debounce_tasks = {}  # channel_id: asyncio.Task
        self.debounce_interval = 1.0  # seconds

    def load_stickies(self):
        """Load sticky messages from the database into the in-memory cache."""
        self.stickies = {}
        cursor = self.db.execute(
            "SELECT channel_id, content, message_id, format FROM sticky_messages"
        )
        for row in cursor.fetchall():
            self.stickies[int(row[0])] = {
                "content": row[1],
                "message_id": row[2],
                "format": row[3],
            }

    def update_sticky_in_db(
        self, channel_id: int, content: str, message_id: int, fmt: str
    ):
        """Insert or replace a sticky record in the database."""
        self.db.execute(
            "INSERT OR REPLACE INTO sticky_messages (channel_id, content, message_id, format) VALUES (?, ?, ?, ?)",
            (channel_id, content, message_id, fmt),
        )
        self.db.commit()

    def delete_sticky_from_db(self, channel_id: int):
        """Delete a sticky record from the database."""
        self.db.execute(
            "DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,)
        )
        self.db.commit()

    async def update_sticky_for_channel(
        self, channel: discord.abc.Messageable, sticky: dict, force_update: bool = False
    ):
        """
        Update the sticky message in the channel if it is not the latest message.
        """
        if not isinstance(channel, discord.TextChannel):
            logging.warning(
                f"Channel {channel} is not a TextChannel. Skipping sticky update."
            )
            return

        permissions = channel.permissions_for(channel.guild.me)
        if not (permissions.send_messages and permissions.manage_messages):
            logging.warning(
                f"Insufficient permissions in channel #{channel.name}. Skipping sticky update."
            )
            return

        lock = self.locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            history = [msg async for msg in channel.history(limit=50)]
            if history and not force_update:
                latest = history[0]
                is_latest_sticky = False

                if latest.author == self.bot.user:
                    if (latest.content and latest.content.endswith(STICKY_MARKER)) or (
                        latest.embeds
                        and latest.embeds[0].description
                        and latest.embeds[0].description.endswith(STICKY_MARKER)
                    ):
                        is_latest_sticky = True

                if is_latest_sticky:
                    for msg in history[1:]:
                        if msg.author == self.bot.user:
                            if (
                                msg.content and msg.content.endswith(STICKY_MARKER)
                            ) or (
                                msg.embeds
                                and msg.embeds[0].description
                                and msg.embeds[0].description.endswith(STICKY_MARKER)
                            ):
                                try:
                                    await msg.delete()
                                except Exception as e:
                                    logging.error(
                                        f"Error deleting duplicate sticky in #{channel.name}: {e}"
                                    )
                    return

            try:
                try:
                    old_message = await channel.fetch_message(sticky["message_id"])
                    await old_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.error(
                        f"Error deleting old sticky in channel #{channel.name}: {e}"
                    )

                fmt = sticky.get("format", "normal")
                new_sticky = await self._send_sticky(channel, sticky["content"], fmt)
                self.stickies[channel.id] = {
                    "content": sticky["content"],
                    "message_id": new_sticky.id,
                    "format": fmt,
                }
                self.update_sticky_in_db(
                    channel.id, sticky["content"], new_sticky.id, fmt
                )
            except Exception as e:
                logging.error(f"Error updating sticky in channel #{channel.name}: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mSticky\033[0m cog synced successfully.")
        audit_log("Sticky cog synced successfully.")
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
        audit_log("Bot resumed: Updating sticky messages in all channels.")
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                await self.update_sticky_for_channel(
                    channel, sticky, force_update=False
                )
        self.initialised = True

    async def _send_sticky(self, channel: discord.TextChannel, content: str, fmt: str):
        """Helper to send a sticky message with the invisible marker appended to the content."""
        if fmt == "embed":
            embed = discord.Embed(
                title="Sticky Message",
                description=f"{content}{STICKY_MARKER}",
                color=discord.Color.blurple(),
            )
            return await channel.send(embed=embed)
        else:
            new_content = f"{content}{STICKY_MARKER}"
            return await channel.send(new_content)

    @app_commands.command(
        name="setsticky",
        description="Set a sticky message in the channel.",
    )
    async def set_sticky(self, interaction: discord.Interaction):
        view = StickyFormatView(self)
        await interaction.response.send_message(
            "Choose the sticky message format:", view=view, ephemeral=True
        )
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) invoked /setsticky in channel #{interaction.channel.name} (ID: {interaction.channel.id})."
        )

    @app_commands.command(
        name="removesticky",
        description="Remove the sticky message in the channel.",
    )
    async def remove_sticky(self, interaction: discord.Interaction):
        await interaction.response.defer()
        channel = interaction.channel
        if channel.id not in self.stickies:
            embed = discord.Embed(
                title="No Sticky Message",
                description=f"There is no sticky message set in #{channel.name}.",
                color=discord.Color.red(),
            )
            confirmation = await interaction.followup.send(embed=embed)
            await asyncio.sleep(3)
            await confirmation.delete()
            audit_log(
                f"{interaction.user.name} (ID: {interaction.user.id}) attempted to remove sticky message in channel #{channel.name} (ID: {channel.id}), but none was set."
            )
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
        self.delete_sticky_from_db(channel.id)

        embed = discord.Embed(
            title="Sticky Removed",
            description=f"Sticky message successfully removed from #{channel.name}.",
            color=discord.Color.green(),
        )
        confirmation = await interaction.followup.send(embed=embed)
        await asyncio.sleep(3)
        await confirmation.delete()
        audit_log(
            f"{interaction.user.name} (ID: {interaction.user.id}) removed sticky message in channel #{channel.name} (ID: {channel.id})."
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return

        channel = message.channel
        if channel.id in self.stickies:
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
        error_embed = None
        if e.status == 403:
            logging.error(f"No access to #{channel.name}. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description=f"I don't have access to #{channel.name}! Please check my permissions.",
                color=discord.Color.red(),
            )
        elif e.status == 404:
            logging.error(f"Channel not found. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Channel not found!",
                color=discord.Color.red(),
            )
        elif e.status == 429:
            logging.error(f"RATE LIMIT. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description="Too many requests! Please try later.",
                color=discord.Color.red(),
            )
        elif e.status in {500, 502, 503, 504}:
            logging.error(f"Discord API Error. Error: {e}")
            error_embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel.name}. Please try later.",
                color=discord.Color.red(),
            )
        else:
            logging.error(
                f"Error when attempting to set sticky message in #{channel.name}. Error: {e}"
            )
            error_embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel.name}.",
                color=discord.Color.red(),
            )

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            else:
                await interaction.response.send_message(
                    embed=error_embed, ephemeral=True
                )
        except Exception as followup_error:
            logging.error(f"Error sending follow-up error message: {followup_error}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
