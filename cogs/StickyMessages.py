import re
import discord
import logging
import sqlite3
import asyncio
from discord import app_commands
from discord.ext import commands
import datetime
from typing import Optional, Dict, Iterable, Sequence, Union

# Define invisible marker for sticky messages using zero-width characters.
STICKY_MARKER = "\u200b\u200c\u200d\u2060"

# Pattern that matches any run of our zero-width characters anywhere in text.
ZERO_WIDTH_RUN = re.compile(r"[\u200b\u200c\u200d\u2060]+")

# How deep we manually scan when hunting for stale stickies (older than 14d, etc.)
MANUAL_SCAN_LIMIT = 2000


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def make_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


# Colour picker reused from CustomEmbed - extended
class ColourSelect(discord.ui.Select):
    def __init__(self, parent_view: "StickyColourPickView"):
        options = [
            discord.SelectOption(
                label="Default", value="default", description="Blurple (#5865F2)"
            ),
            discord.SelectOption(
                label="Custom Hex",
                value="custom_hex",
                description="Enter your own hex code…",
            ),
            discord.SelectOption(
                label="Random", value="random", description="Bot picks a random colour!"
            ),
            discord.SelectOption(
                label="White", value="white", description="Pure White (#FFFFFF)"
            ),
            discord.SelectOption(
                label="Red", value="red", description="Carmine Pink (#E74C3C)"
            ),
            discord.SelectOption(
                label="Dark Red", value="dark_red", description="Red Birch (#992D22)"
            ),
            discord.SelectOption(
                label="Orange", value="orange", description="Dark Cheddar (#E67E22)"
            ),
            discord.SelectOption(
                label="Yellow", value="yellow", description="Corn (#FEE75C)"
            ),
            discord.SelectOption(
                label="Gold", value="gold", description="Tanned Leather (#F1C40F)"
            ),
            discord.SelectOption(
                label="Green", value="green", description="UFO Green (#2ECC71)"
            ),
            discord.SelectOption(
                label="Dark Green", value="dark_green", description="Pine (#145A32)"
            ),
            discord.SelectOption(
                label="Teal", value="teal", description="Aloha (#1ABC9C)"
            ),
            discord.SelectOption(
                label="Dark Teal", value="dark_teal", description="Blue Green (#11806A)"
            ),
            discord.SelectOption(
                label="Blue", value="blue", description="Dayflower (#3498DB)"
            ),
            discord.SelectOption(
                label="Dark Blue", value="dark_blue", description="Deep Water (#206694)"
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
                label="Fuchsia", value="fuchsia", description="Hot Pink (#EB459E)"
            ),
            discord.SelectOption(
                label="Magenta", value="magenta", description="Vivid Magenta (#E84393)"
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
                description="Discord UI (#36393F)",
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
        if choice == "custom_hex":
            await interaction.response.send_modal(
                HexContentModal(
                    self.parent_view.channel,
                    self.parent_view.sticky_cog,
                    self.parent_view.selected_format,
                )
            )
        else:
            try:
                if choice == "default":
                    self.parent_view.chosen_colour = discord.Color.blurple()
                elif choice == "random":
                    self.parent_view.chosen_colour = discord.Color.random()
                else:
                    factory = getattr(discord.Color, choice)
                    self.parent_view.chosen_colour = factory()
            except Exception:
                self.parent_view.chosen_colour = discord.Color.blurple()
            await interaction.response.send_modal(
                StickyModal(
                    self.parent_view.bot,
                    self.parent_view.sticky_cog,
                    self.parent_view.selected_format,
                    self.parent_view.chosen_colour,
                )
            )
        audit_log(f"{interaction.user} picked colour '{choice}' for sticky embed.")


class StickyColourPickView(discord.ui.View):
    def __init__(self, bot, sticky_cog, channel, selected_format):
        super().__init__(timeout=60)
        self.bot = bot
        self.sticky_cog = sticky_cog
        self.channel = channel
        self.selected_format = selected_format
        self.chosen_colour = discord.Color.default()
        self.add_item(ColourSelect(self))

    async def on_timeout(self):
        logging.info(f"ColourPickView timed out in #{self.channel.name}")
        audit_log(f"Colour pick dropdown timed out in #{self.channel.name}.")
        for child in self.children:
            child.disabled = True


class HexContentModal(discord.ui.Modal, title="Custom HEX Embed"):
    hex_code = discord.ui.TextInput(
        label="HEX Code",
        style=discord.TextStyle.short,
        required=True,
        placeholder="#RRGGBB or RRGGBB",
        max_length=7,
    )
    sticky_message = discord.ui.TextInput(
        label="Sticky Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your sticky message here…",
    )

    def __init__(self, channel, sticky_cog, selected_format):
        super().__init__()
        self.channel = channel
        self.sticky_cog = sticky_cog
        self.selected_format = selected_format
        self.chosen_colour = None

    async def on_submit(self, interaction: discord.Interaction):
        hex_str = self.hex_code.value.strip().lstrip("#")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", hex_str):
            err = make_embed(
                "Error",
                "Invalid hex. Must be exactly 6 hex digits.",
                discord.Color.red(),
            )
            return await interaction.response.send_message(embed=err, ephemeral=True)
        colour = discord.Color(int(hex_str, 16))
        modal = StickyModal(
            interaction.client,
            self.sticky_cog,
            self.selected_format,
            colour,
            prefilled_message=self.sticky_message.value,
        )
        await modal.on_submit(interaction)


class StickyFormatSelect(discord.ui.Select):
    def __init__(self, sticky_cog: "StickyMessages"):
        options = [
            discord.SelectOption(
                label="Normal", value="normal", description="Plain text sticky"
            ),
            discord.SelectOption(
                label="Embed",
                value="embed",
                description="Embed sticky with custom colour",
            ),
        ]
        super().__init__(
            placeholder="Choose message format…",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.sticky_cog = sticky_cog

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "normal":
            await interaction.response.send_modal(
                StickyModal(interaction.client, self.sticky_cog, "normal", None)
            )
        else:
            view = StickyColourPickView(
                interaction.client, self.sticky_cog, interaction.channel, "embed"
            )
            await interaction.response.send_message(
                "Choose a colour for your sticky embed:", view=view, ephemeral=True
            )
        audit_log(f"{interaction.user} selected sticky format '{choice}'.")


class StickyFormatView(discord.ui.View):
    def __init__(self, sticky_cog: "StickyMessages"):
        super().__init__()
        self.add_item(StickyFormatSelect(sticky_cog))


class StickyModal(discord.ui.Modal, title="Set Sticky Message"):
    sticky_message = discord.ui.TextInput(
        label="Sticky Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your sticky message here…",
    )

    def __init__(
        self,
        bot: commands.Bot,
        sticky_cog: "StickyMessages",
        selected_format: str,
        colour: Optional[discord.Color],
        prefilled_message: Optional[str] = None,
    ):
        super().__init__()
        self.bot = bot
        self.sticky_cog = sticky_cog
        self.selected_format = selected_format
        self.colour = colour or discord.Color.blurple()
        if prefilled_message:
            self.sticky_message.default = prefilled_message

    async def on_submit(self, interaction: discord.Interaction):
        content = self.sticky_message.value
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            err = make_embed("Error", "This isn’t a text channel.", discord.Color.red())
            return await interaction.response.send_message(embed=err, ephemeral=True)

        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or (
            self.selected_format == "embed" and not perms.embed_links
        ):
            err = make_embed(
                "Error", "I lack the permissions to post here.", discord.Color.red()
            )
            return await interaction.response.send_message(embed=err, ephemeral=True)

        # Replace any existing sticky first, under lock.
        await self.sticky_cog._replace_sticky_atomically(
            channel,
            {
                "content": content,
                "format": self.selected_format,
                "color": self.colour.value if self.selected_format == "embed" else 0,
            },
        )

        ok = make_embed(
            "Sticky Set",
            f"Sticky successfully set in {channel.mention}.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=ok, ephemeral=True)
        audit_log(
            f"{interaction.user} set a '{self.selected_format}' sticky in #{channel.name}."
        )


GuildTextLike = Union[discord.TextChannel, discord.Thread]


class StickyMessages(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stickies: Dict[int, Dict] = {}
        self.db = sqlite3.connect("database.db", check_same_thread=False)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS sticky_messages (channel_id INTEGER PRIMARY KEY, content TEXT, message_id INTEGER, format TEXT, color INTEGER DEFAULT 0)"
        )
        cols = [
            r[1]
            for r in self.db.execute("PRAGMA table_info(sticky_messages)").fetchall()
        ]
        if "color" not in cols:
            self.db.execute(
                "ALTER TABLE sticky_messages ADD COLUMN color INTEGER DEFAULT 0"
            )
        self.db.commit()
        self.load_stickies()

        # Concurrency and debouncing
        self.locks: Dict[int, asyncio.Lock] = {}
        self.debounce_tasks: Dict[int, asyncio.Task] = {}
        # Use a slightly longer debounce window to reduce churn and duplicates during active chat
        self.debounce_interval = 1.2

    def cog_unload(self):
        try:
            self.db.close()
        except Exception as e:
            logging.error(f"Error closing Sticky cog database: {e}")

    def load_stickies(self):
        self.stickies = {}
        cursor = self.db.execute(
            "SELECT channel_id, content, message_id, format, color FROM sticky_messages"
        )
        for row in cursor.fetchall():
            self.stickies[int(row[0])] = {
                "content": row[1],
                "message_id": row[2],
                "format": row[3],
                "color": row[4],
            }

    def update_sticky_in_db(
        self, channel_id: int, content: str, message_id: int, fmt: str, colour: int
    ):
        # Explicitly delete any existing row first to avoid duplicates if schema changes elsewhere.
        try:
            self.db.execute(
                "DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,)
            )
        except Exception:
            pass
        self.db.execute(
            "INSERT INTO sticky_messages (channel_id, content, message_id, format, color) VALUES (?, ?, ?, ?, ?)",
            (channel_id, content, message_id, fmt, colour),
        )
        self.db.commit()

    def delete_sticky_from_db(self, channel_id: int):
        self.db.execute(
            "DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,)
        )
        self.db.commit()

    # -----------------------
    # Utility and helpers
    # -----------------------

    def _is_message_sticky(self, msg: discord.Message) -> bool:
        """Detect our sticky messages robustly, both text and embed forms."""
        if msg.author.id != (self.bot.user.id if self.bot.user else 0):
            return False

        # Plain text sticky: marker anywhere in content
        if msg.content and ZERO_WIDTH_RUN.search(msg.content):
            return True

        # Embed sticky: look through all embeds for marker in description, fields, or footer
        for e in msg.embeds or []:
            try:
                if e.description and ZERO_WIDTH_RUN.search(e.description):
                    return True
                for f in e.fields:
                    if f.value and ZERO_WIDTH_RUN.search(str(f.value)):
                        return True
                if e.footer and e.footer.text and ZERO_WIDTH_RUN.search(e.footer.text):
                    return True
            except Exception:
                continue

        return False

    async def _manual_sweep_for_stickies(
        self,
        channel: GuildTextLike,
        skip_ids: Optional[Sequence[int]] = None,
        limit: int = MANUAL_SCAN_LIMIT,
    ):
        """Manually scan recent history and delete any detected stickies, regardless of age."""
        skip = set(skip_ids or [])
        deleted = 0
        try:
            async for msg in channel.history(limit=limit):
                if msg.id in skip:
                    continue
                if self._is_message_sticky(msg):
                    try:
                        await msg.delete()
                        deleted += 1
                    except Exception as e:
                        logging.warning(f"Manual delete failed in #{channel.name}: {e}")
        except Exception as e:
            logging.debug(f"Manual sweep error in #{channel.name}: {e}")
        if deleted:
            audit_log(
                f"Manual sticky sweep deleted {deleted} messages in #{channel.name}."
            )

    async def _purge_old_stickies(
        self, channel: GuildTextLike, skip_id: Optional[int] = None
    ):
        """Delete all previous sticky messages in the channel, optionally skipping one id.

        Strategy:
          1) Try purge with a check (fast). This will skip >14d silently.
          2) Always follow with a manual sweep to catch anything the purge skipped.
        """
        perms = channel.permissions_for(channel.guild.me)
        can_manage = perms.manage_messages
        # 1) Bulk purge if possible
        if perms.send_messages and can_manage:

            def check(m: discord.Message) -> bool:
                if skip_id is not None and m.id == skip_id:
                    return False
                return self._is_message_sticky(m)

            try:
                await channel.purge(limit=200, check=check, oldest_first=False)
            except Exception as e:
                # Ignore; we will still do the manual pass
                logging.debug(
                    f"Purge failed in #{channel.name}, will manual sweep: {e}"
                )

        # 2) Manual sweep (handles >14d and when manage_messages is missing)
        await self._manual_sweep_for_stickies(
            channel, skip_ids=[skip_id] if skip_id else None
        )

    async def _send_sticky(
        self, channel: GuildTextLike, content: str, fmt: str, colour_value: int
    ):
        """Send a sticky message in the requested format."""
        if fmt == "embed":
            embed = discord.Embed(
                title="Sticky Message",
                description=f"{content}{STICKY_MARKER}",
                color=discord.Color(colour_value),
            )
            return await channel.send(embed=embed)
        else:
            return await channel.send(f"{content}{STICKY_MARKER}")

    async def _replace_sticky_atomically(self, channel: GuildTextLike, new_data: Dict):
        """Under a per-channel lock, remove all old stickies and post the new one exactly once.

        Important: we delete any existing DB row for this channel BEFORE inserting the new one,
        to guarantee no duplicate rows even if constraints change or were previously broken.
        """
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logging.warning(
                f"Channel {channel} is not a TextChannel/Thread. Skipping sticky replace."
            )
            return

        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages:
            logging.warning(f"Insufficient permissions to send in #{channel.name}.")
            return

        lock = self.locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            # Purge all prior stickies first (both bulk + manual)
            await self._purge_old_stickies(channel)

            # If we have a tracked sticky id, ensure it is gone as well
            tracked = self.stickies.get(channel.id)
            if tracked and tracked.get("message_id"):
                try:
                    old_message = await channel.fetch_message(tracked["message_id"])
                    try:
                        await old_message.delete()
                    except Exception:
                        pass
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.error(
                        f"Error fetching tracked sticky in #{channel.name}: {e}"
                    )

            # Explicitly delete any existing DB row for this channel BEFORE we insert the new one
            try:
                self.delete_sticky_from_db(channel.id)
            except Exception:
                # If the row does not exist yet, ignore
                pass

            # Post the new sticky
            sent = await self._send_sticky(
                channel, new_data["content"], new_data["format"], new_data["color"]
            )

            # Update memory and DB with the new single source of truth
            self.stickies[channel.id] = {
                "content": new_data["content"],
                "message_id": sent.id,
                "format": new_data["format"],
                "color": new_data["color"],
            }
            self.update_sticky_in_db(
                channel.id,
                new_data["content"],
                sent.id,
                new_data["format"],
                new_data["color"],
            )

            # Post-send safety sweep to eliminate any race-created duplicates
            await self._manual_sweep_for_stickies(channel, skip_ids=[sent.id], limit=25)

    async def update_sticky_for_channel(
        self, channel: GuildTextLike, sticky: dict, force_update: bool = False
    ):
        """Reposition the sticky to the bottom if needed."""
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            logging.warning(
                f"Channel {channel} is not a TextChannel/Thread. Skipping sticky update."
            )
            return

        perms = channel.permissions_for(channel.guild.me)
        if not perms.send_messages:
            logging.warning(
                f"Insufficient permissions in channel #{channel.name}. Skipping sticky update."
            )
            return

        lock = self.locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            # If not forced and the latest message is already our sticky, do nothing
            try:
                async for last in channel.history(limit=1):
                    if self._is_message_sticky(last) and (
                        sticky.get("message_id") is None
                        or last.id == sticky.get("message_id")
                    ):
                        if not force_update:
                            return
                        break
            except Exception:
                pass

            # Purge all old stickies except the one we track if it happens to be latest
            await self._purge_old_stickies(channel, skip_id=sticky.get("message_id"))

            # If we still have the tracked sticky in the channel but it is not last, delete it so we can re-send
            if sticky.get("message_id"):
                try:
                    old_message = await channel.fetch_message(sticky["message_id"])
                    try:
                        await old_message.delete()
                    except Exception:
                        pass
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.error(
                        f"Error deleting tracked sticky in channel #{channel.name}: {e}"
                    )

            # Send fresh sticky at bottom
            fmt = sticky.get("format", "normal")
            colour_value = sticky.get("color", discord.Color.blurple().value)
            new_msg = await self._send_sticky(
                channel, sticky["content"], fmt, colour_value
            )

            # Update cache and DB
            self.stickies[channel.id] = {
                "content": sticky["content"],
                "message_id": new_msg.id,
                "format": fmt,
                "color": colour_value,
            }
            self.update_sticky_in_db(
                channel.id, sticky["content"], new_msg.id, fmt, colour_value
            )

            # Final small sweep
            await self._manual_sweep_for_stickies(
                channel, skip_ids=[new_msg.id], limit=25
            )

    # -----------------------
    # Events
    # -----------------------

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mSticky\033[0m cog synced successfully.")
        audit_log("Sticky cog synced successfully.")
        # Do not force an update on start to reduce churn. Only fix if missing.
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                try:
                    # If the tracked message does not exist, replace it; else leave as is.
                    if sticky.get("message_id"):
                        try:
                            await channel.fetch_message(sticky["message_id"])
                        except discord.NotFound:
                            await self.update_sticky_for_channel(
                                channel, sticky, force_update=True
                            )
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_resumed(self):
        logging.info("Bot resumed. Ensuring stickies exist.")
        audit_log("Bot resumed: Ensuring stickies exist.")
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                try:
                    if sticky.get("message_id"):
                        try:
                            await channel.fetch_message(sticky["message_id"])
                        except discord.NotFound:
                            await self.update_sticky_for_channel(
                                channel, sticky, force_update=True
                            )
                except Exception:
                    pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        channel = message.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return
        if channel.id in self.stickies:
            # Proper debounce: cancel existing task and reschedule
            task = self.debounce_tasks.get(channel.id)
            if task and not task.done():
                task.cancel()
            self.debounce_tasks[channel.id] = asyncio.create_task(
                self._debounced_update(channel, dict(self.stickies[channel.id]))
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # If the bot's sticky was manually deleted, cancel pending debounce and re-post immediately
        if message.author == self.bot.user and message.channel.id in self.stickies:
            sticky = self.stickies[message.channel.id]
            if message.id == sticky["message_id"]:
                task = self.debounce_tasks.pop(message.channel.id, None)
                if task:
                    task.cancel()
                await self.update_sticky_for_channel(
                    message.channel, sticky, force_update=True
                )

    async def _debounced_update(self, channel: GuildTextLike, sticky: dict):
        try:
            await asyncio.sleep(self.debounce_interval)
            # Channel might have lost its sticky during wait
            if channel.id not in self.stickies:
                return
            await self.update_sticky_for_channel(channel, sticky, force_update=False)
        except asyncio.CancelledError:
            pass
        finally:
            # Only clear if this exact task is still the active one
            current = self.debounce_tasks.get(channel.id)
            if current and current.done():
                self.debounce_tasks.pop(channel.id, None)
            elif current is None:
                pass

    # -----------------------
    # Commands
    # -----------------------

    @app_commands.command(
        name="setsticky", description="Set a sticky message in the channel."
    )
    async def set_sticky(self, interaction: discord.Interaction):
        view = StickyFormatView(self)
        await interaction.response.send_message(
            "Choose the sticky message format:", view=view, ephemeral=True
        )
        audit_log(
            f"{interaction.user} invoked /setsticky in channel #{interaction.channel.name}."
        )

    @app_commands.command(
        name="removesticky", description="Remove the sticky message in the channel."
    )
    async def remove_sticky(self, interaction: discord.Interaction):
        channel = interaction.channel
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            err = make_embed("Error", "This isn’t a text channel.", discord.Color.red())
            return await interaction.response.send_message(embed=err, ephemeral=True)

        # Remove under lock to avoid races with debounce
        lock = self.locks.setdefault(channel.id, asyncio.Lock())
        async with lock:
            try:
                tracked = self.stickies.get(channel.id)
                old_id = tracked["message_id"] if tracked else None
                if old_id:
                    try:
                        old_msg = await channel.fetch_message(old_id)
                        await old_msg.delete()
                    except Exception:
                        pass

                # Always sweep even if we had no tracked entry
                await self._purge_old_stickies(channel)
            finally:
                # Clean DB record regardless of cache presence
                self.delete_sticky_from_db(channel.id)
                self.stickies.pop(channel.id, None)
                task = self.debounce_tasks.pop(channel.id, None)
                if task:
                    task.cancel()

        ok = make_embed(
            "Sticky Removed",
            f"Removed sticky from {channel.mention}.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=ok, ephemeral=True)
        audit_log(f"{interaction.user} removed sticky in #{channel.name}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(StickyMessages(bot))
