import re
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


def make_embed(title: str, description: str, color: discord.Color) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


# — Colour picker reused from CustomEmbed —
class ColourSelect(discord.ui.Select):
    def __init__(self, parent_view: "StickyColourPickView"):
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
                label="Random", value="random", description="Pick a random hue"
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
                factory = getattr(discord.Color, choice)
                self.parent_view.chosen_colour = factory()
            except Exception:
                self.parent_view.chosen_colour = discord.Color.default()
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
        self.selected_format = selected_format  # always "embed" here
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
                "Invalid hex—must be exactly 6 hex digits.",
                discord.Color.red(),
            )
            return await interaction.response.send_message(embed=err, ephemeral=True)
        colour = discord.Color(int(hex_str, 16))
        # forward to StickyModal with prefilled message
        modal = StickyModal(
            interaction.client,
            self.sticky_cog,
            self.selected_format,
            colour,
            prefilled_message=self.sticky_message.value,
        )
        await modal.on_submit(interaction)


class StickyFormatSelect(discord.ui.Select):
    def __init__(self, sticky_cog: "Sticky"):
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
        else:  # embed
            view = StickyColourPickView(
                interaction.client, self.sticky_cog, interaction.channel, "embed"
            )
            await interaction.response.send_message(
                "Choose a colour for your sticky embed:", view=view, ephemeral=True
            )
        audit_log(f"{interaction.user} selected sticky format '{choice}'.")


class StickyFormatView(discord.ui.View):
    def __init__(self, sticky_cog: "Sticky"):
        super().__init__()
        self.add_item(StickyFormatSelect(sticky_cog))


# — Modal for both normal & embed stickies —
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
        sticky_cog: "Sticky",
        selected_format: str,
        colour: discord.Color,
        prefilled_message: str = None,
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
        channel = interaction.guild.get_channel(interaction.channel.id)
        perms = channel.permissions_for(interaction.guild.me)
        if not perms.send_messages or (
            self.selected_format == "embed" and not perms.embed_links
        ):
            err = make_embed(
                "Error", "I lack the permissions to post here.", discord.Color.red()
            )
            return await interaction.response.send_message(embed=err, ephemeral=True)

        # remove old sticky
        if channel.id in self.sticky_cog.stickies:
            old = self.sticky_cog.stickies[channel.id]
            try:
                old_msg = await channel.fetch_message(old["message_id"])
                await old_msg.delete()
            except Exception:
                pass

        # send new sticky
        if self.selected_format == "embed":
            embed = discord.Embed(
                title="Sticky Message",
                description=f"{content}{STICKY_MARKER}",
                color=self.colour,
            )
            sent = await channel.send(embed=embed)
            colour_value = self.colour.value
        else:
            sent = await channel.send(f"{content}{STICKY_MARKER}")
            colour_value = 0

        # save it in memory and DB (including colour)
        self.sticky_cog.stickies[channel.id] = {
            "content": content,
            "message_id": sent.id,
            "format": self.selected_format,
            "color": colour_value,
        }
        self.sticky_cog.update_sticky_in_db(
            channel.id, content, sent.id, self.selected_format, colour_value
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


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stickies = {}
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
        self.initialised = False
        self.locks = {}
        self.debounce_tasks = {}
        self.debounce_interval = 1.0

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
        self.db.execute(
            "INSERT OR REPLACE INTO sticky_messages (channel_id, content, message_id, format, color) VALUES (?, ?, ?, ?, ?)",
            (channel_id, content, message_id, fmt, colour),
        )
        self.db.commit()

    def delete_sticky_from_db(self, channel_id: int):
        self.db.execute(
            "DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,)
        )
        self.db.commit()

    async def update_sticky_for_channel(
        self, channel: discord.abc.Messageable, sticky: dict, force_update: bool = False
    ):
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
            # Delete ALL previous sticky messages by the bot (except the one about to post)
            history = [msg async for msg in channel.history(limit=50)]
            newest_is_sticky = False
            for msg in history:
                if msg.author == self.bot.user and (
                    (msg.content and msg.content.endswith(STICKY_MARKER))
                    or (
                        msg.embeds
                        and msg.embeds[0].description
                        and msg.embeds[0].description.endswith(STICKY_MARKER)
                    )
                ):
                    # If this is the message we're about to post, don't delete it
                    if msg.id == sticky.get("message_id"):
                        newest_is_sticky = msg == history[0]
                        continue
                    try:
                        await msg.delete()
                    except Exception as e:
                        logging.error(
                            f"Error deleting old sticky in #{channel.name}: {e}"
                        )

            # If the newest message is already the sticky, and not forced, do nothing
            if (
                not force_update
                and history
                and history[0].id == sticky.get("message_id")
            ):
                return

            # Delete tracked sticky if still present but not in recent history
            if sticky.get("message_id"):
                try:
                    old_message = await channel.fetch_message(sticky["message_id"])
                    await old_message.delete()
                except discord.NotFound:
                    pass
                except Exception as e:
                    logging.error(
                        f"Error deleting tracked sticky in channel #{channel.name}: {e}"
                    )

            fmt = sticky.get("format", "normal")
            new_sticky = await self._send_sticky(channel, sticky["content"], fmt)
            self.stickies[channel.id] = {
                "content": sticky["content"],
                "message_id": new_sticky.id,
                "format": fmt,
            }
            self.update_sticky_in_db(channel.id, sticky["content"], new_sticky.id, fmt)

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

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        # If the bot's sticky was manually deleted, cancel pending debounce and re-post immediately
        if message.author == self.bot.user and message.channel.id in self.stickies:
            sticky = self.stickies[message.channel.id]
            if message.id == sticky["message_id"]:
                # cancel any pending debounce update for this channel
                task = self.debounce_tasks.pop(message.channel.id, None)
                if task:
                    task.cancel()
                # force a re-send right away
                await self.update_sticky_for_channel(
                    message.channel, sticky, force_update=True
                )

    async def _debounced_update(self, channel: discord.abc.Messageable, sticky: dict):
        try:
            await asyncio.sleep(self.debounce_interval)
            await self.update_sticky_for_channel(channel, sticky, force_update=False)
        finally:
            self.debounce_tasks.pop(channel.id, None)

    async def _send_sticky(
        self, channel: discord.TextChannel, content: str, fmt: str, colour_value: int
    ):
        if fmt == "embed":
            embed = discord.Embed(
                title="Sticky Message",
                description=f"{content}{STICKY_MARKER}",
                color=discord.Color(colour_value),
            )
            return await channel.send(embed=embed)
        else:
            return await channel.send(f"{content}{STICKY_MARKER}")

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
        channel = interaction.guild.get_channel(interaction.channel.id)
        if channel.id not in self.stickies:
            err = make_embed(
                "Error", f"No sticky found in {channel.mention}.", discord.Color.red()
            )
            return await interaction.response.send_message(embed=err, ephemeral=True)

        try:
            old_msg = await channel.fetch_message(
                self.stickies[channel.id]["message_id"]
            )
            await old_msg.delete()
        except Exception:
            pass
        self.delete_sticky_from_db(channel.id)
        del self.stickies[channel.id]

        ok = make_embed(
            "Sticky Removed",
            f"Removed sticky from {channel.mention}.",
            discord.Color.green(),
        )
        await interaction.response.send_message(embed=ok, ephemeral=True)
        audit_log(f"{interaction.user} removed sticky in #{channel.name}.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Sticky(bot))
