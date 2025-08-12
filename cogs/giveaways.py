from __future__ import annotations
from typing import Optional, List, Tuple
import discord
import random
import sqlite3
import logging
import yaml
from discord.ext import commands
from discord import app_commands
import datetime
import re

# ============================================================
# Database setup
# ============================================================
conn = sqlite3.connect("database.db", check_same_thread=False)
conn.row_factory = sqlite3.Row  # allow name-based column access
cursor = conn.cursor()

# Giveaways table
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS giveaways (
        giveaway_id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER,
        prize TEXT NOT NULL,
        description TEXT,
        host_id INTEGER NOT NULL,
        start_time INTEGER NOT NULL,
        end_time INTEGER NOT NULL,
        winner_count INTEGER NOT NULL DEFAULT 1,
        status TEXT NOT NULL DEFAULT 'running', -- running | ended | cancelled
        required_role_id INTEGER,
        max_entries_per_user INTEGER NOT NULL DEFAULT 1,
        entry_count INTEGER NOT NULL DEFAULT 0
    )
    """
)

# Entries table
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS giveaway_entries (
        giveaway_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        entries INTEGER NOT NULL DEFAULT 1,
        entered_at INTEGER NOT NULL,
        PRIMARY KEY (giveaway_id, user_id),
        FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id) ON DELETE CASCADE
    )
    """
)

# Optional blacklist table (per guild)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS giveaway_blacklist (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason TEXT,
        PRIMARY KEY (guild_id, user_id)
    )
    """
)
conn.commit()


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def unix_now() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def parse_duration_to_seconds(s: str) -> Optional[int]:
    """
    Parse a duration string like '90m', '1h', '2h30m', '1d2h', '45m30s' into seconds.
    Returns None if parsing fails or value is non-positive.
    """
    s = s.strip().lower()
    if not s:
        return None
    pattern = r"(?:(\d+)\s*d)?\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+)\s*s)?$"
    m = re.fullmatch(pattern, s)
    if not m:
        return None
    days = int(m.group(1) or 0)
    hours = int(m.group(2) or 0)
    minutes = int(m.group(3) or 0)
    seconds = int(m.group(4) or 0)
    total = days * 86400 + hours * 3600 + minutes * 60 + seconds
    return total if total > 0 else None


def humanize_remaining(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    parts: List[str] = []
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs and not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


# ============================================================
# Giveaway Entry View (Persistent)
# ============================================================
class GiveawayEntryView(discord.ui.View):
    def __init__(self, cog: "Giveaways", giveaway_id: int):
        # Persistent view so users can enter even after a bot restart
        super().__init__(timeout=None)
        self.cog = cog
        self.giveaway_id = giveaway_id

        # Buttons need stable custom_ids for persistence
        self.add_item(
            discord.ui.Button(
                label=self.cog.labels.get("enter_label", "Enter"),
                style=discord.ButtonStyle.success,
                custom_id=f"giveaway_enter:{giveaway_id}",
            )
        )
        self.add_item(
            discord.ui.Button(
                label=self.cog.labels.get("leave_label", "Leave"),
                style=discord.ButtonStyle.secondary,
                custom_id=f"giveaway_leave:{giveaway_id}",
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # All checks are handled in component callbacks registered in the Cog
        return True


# ============================================================
# The Giveaways Cog
# ============================================================
class Giveaways(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Load optional configuration
        self.config = {}
        self.manager_role_ids: List[int] = []
        self.ping_role_id: Optional[int] = None
        self.defaults = {
            "winner_count": 1,
            "duration": "1h",
            "max_entries_per_user": 1,
        }
        self.labels = {
            "enter_label": "Enter",
            "leave_label": "Leave",
        }

        try:
            with open("config.yaml", "r", encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
            gw = self.config.get("giveaway", {})
            self.manager_role_ids = list(map(int, gw.get("manager_role_ids", [])))
            self.ping_role_id = int(gw["ping_role_id"]) if gw.get("ping_role_id") else None
            self.defaults["winner_count"] = int(gw.get("default_winner_count", 1))
            self.defaults["duration"] = str(gw.get("default_duration", "1h"))
            self.defaults["max_entries_per_user"] = int(
                gw.get("default_max_entries_per_user", 1)
            )
            labels_cfg = gw.get("labels", {})
            self.labels["enter_label"] = str(labels_cfg.get("enter_button_label", "Enter"))
            self.labels["leave_label"] = str(labels_cfg.get("leave_button_label", "Leave"))
        except Exception as e:
            logging.warning(f"Giveaways: failed to load config.yaml, using defaults. {e}")

        # Register component callbacks for persistent custom_ids
        bot.add_listener(self.on_component_interaction, "on_interaction")

    # --------------------------------------------------------
    # Permission Helpers
    # --------------------------------------------------------
    def _is_manager(self, member: discord.Member) -> bool:
        if member.guild_permissions.administrator:
            return True
        if not self.manager_role_ids:
            return member.guild_permissions.manage_guild
        member_role_ids = {r.id for r in member.roles}
        return any(rid in member_role_ids for rid in self.manager_role_ids)

    # --------------------------------------------------------
    # Embeds
    # --------------------------------------------------------
    @staticmethod
    def _embed(title: str, description: str, colour: discord.Color) -> discord.Embed:
        return discord.Embed(title=title, description=description, color=colour)

    # --------------------------------------------------------
    # DB Helpers
    # --------------------------------------------------------
    def _fetch_giveaway(self, giveaway_id: int) -> Optional[sqlite3.Row]:
        cursor.execute("SELECT * FROM giveaways WHERE giveaway_id = ?", (giveaway_id,))
        return cursor.fetchone()

    def _active_giveaways_for_guild(self, guild_id: int) -> List[sqlite3.Row]:
        # Only status running and not past end time
        now = unix_now()
        cursor.execute(
            "SELECT * FROM giveaways WHERE guild_id = ? AND status = 'running' AND end_time > ? ORDER BY end_time ASC",
            (guild_id, now),
        )
        return cursor.fetchall()

    def _count_entries(self, giveaway_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        return int(cursor.fetchone()[0])

    def _get_entrants(self, giveaway_id: int) -> List[sqlite3.Row]:
        cursor.execute(
            "SELECT user_id, entries FROM giveaway_entries WHERE giveaway_id = ? ORDER BY entries DESC, user_id ASC",
            (giveaway_id,),
        )
        return cursor.fetchall()

    def _user_is_blacklisted(self, guild_id: int, user_id: int) -> bool:
        cursor.execute(
            "SELECT 1 FROM giveaway_blacklist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return cursor.fetchone() is not None

    # --------------------------------------------------------
    # UI Builders
    # --------------------------------------------------------
    def _build_giveaway_embed(
        self,
        guild: discord.Guild,
        prize: str,
        description: Optional[str],
        host: Optional[discord.abc.User],
        end_ts: int,
        winner_count: int,
        required_role_id: Optional[int],
        entry_count: int,
        status: str = "running",
        message_url: Optional[str] = None,
    ) -> discord.Embed:
        remaining = max(0, end_ts - unix_now())
        pretty_time = f"<t:{end_ts}:R>" if status == "running" else f"<t:{end_ts}:F>"
        colour = (
            discord.Color.green()
            if status == "running"
            else (discord.Color.red() if status == "cancelled" else discord.Color.gold())
        )
        embed = discord.Embed(
            title="🎁 Giveaway",
            description=description or "\u200b",
            color=colour,
        )
        embed.add_field(name="Prize", value=prize, inline=False)
        embed.add_field(name="Winners", value=str(winner_count), inline=True)
        if status == "running":
            embed.add_field(name="Ends", value=f"{pretty_time}", inline=True)
            embed.add_field(
                name="Time Remaining", value=humanize_remaining(remaining), inline=True
            )
        else:
            embed.add_field(name="Ended", value=f"{pretty_time}", inline=True)
        embed.add_field(name="Entries", value=str(entry_count), inline=True)
        if required_role_id:
            embed.add_field(name="Requirement", value=f"<@&{required_role_id}>", inline=True)
        if host:
            embed.set_footer(text=f"Hosted by {host.display_name}")
            embed.set_author(name=host.display_name, icon_url=host.display_avatar.url)
        if message_url:
            embed.add_field(name="Jump", value=f"[Go to message]({message_url})", inline=False)
        return embed

    async def _announce_winners(
        self,
        interaction: Optional[discord.Interaction],
        guild: discord.Guild,
        channel_id: int,
        giveaway_id: int,
        prize: str,
        winner_count: int,
    ) -> Tuple[List[int], Optional[discord.Message]]:
        entrants = [row["user_id"] for row in self._get_entrants(giveaway_id)]
        random.shuffle(entrants)

        winners: List[int] = []
        if entrants and winner_count > 0:
            pick = min(winner_count, len(entrants))
            winners = random.sample(entrants, pick)

        channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
        if winners:
            mentions = " ".join(f"<@{uid}>" for uid in winners)
            content = f"🎉 Congratulations {mentions}! You won **{prize}**."
        else:
            content = "No valid entries. No winners could be selected."

        try:
            msg = await channel.send(content)
        except Exception:
            msg = None

        # Attempt to DM winners
        for uid in winners:
            user = guild.get_member(uid) or await guild.fetch_member(uid)
            try:
                await user.send(f"🎉 You won **{prize}** in {guild.name}. Please contact the host to claim.")
            except Exception:
                pass

        return winners, msg

    async def _refresh_giveaway_message(
        self,
        guild: discord.Guild,
        giveaway_id: int,
        message_hint: Optional[discord.Message] = None,
    ) -> None:
        row = self._fetch_giveaway(giveaway_id)
        if not row:
            return
        try:
            entry_count = self._count_entries(giveaway_id)
            channel = guild.get_channel(row["channel_id"]) or await guild.fetch_channel(row["channel_id"])

            msg = None
            if message_hint and message_hint.id == row["message_id"]:
                msg = message_hint
            else:
                try:
                    msg = await channel.fetch_message(row["message_id"])
                except Exception:
                    msg = None

            if msg is None:
                return

            embed = self._build_giveaway_embed(
                guild=guild,
                prize=row["prize"],
                description=row["description"],
                host=guild.get_member(row["host_id"]),
                end_ts=row["end_time"],
                winner_count=int(row["winner_count"]),
                required_role_id=row["required_role_id"],
                entry_count=entry_count,
                status=row["status"],
                message_url=msg.jump_url,
            )
            view = GiveawayEntryView(self, giveaway_id) if row["status"] == "running" else None
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logging.warning(f"Failed to refresh giveaway message {giveaway_id}: {e}")

    async def _end_if_overdue(self, guild: discord.Guild, row: sqlite3.Row) -> bool:
        """
        If the giveaway has passed its end_time, mark as ended and update the message.
        Returns True if it was ended now.
        """
        if row["status"] != "running" or row["end_time"] > unix_now():
            return False
        try:
            cursor.execute("UPDATE giveaways SET status = 'ended' WHERE giveaway_id = ?", (row["giveaway_id"],))
            conn.commit()
            await self._refresh_giveaway_message(guild, row["giveaway_id"])
            return True
        except Exception as e:
            logging.warning(f"Failed to auto-end overdue giveaway {row['giveaway_id']}: {e}")
            return False

    # --------------------------------------------------------
    # Component handling for persistent buttons
    # --------------------------------------------------------
    async def on_component_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        data = interaction.data or {}
        custom_id = data.get("custom_id")
        if not custom_id:
            return

        if not (custom_id.startswith("giveaway_enter:") or custom_id.startswith("giveaway_leave:")):
            return

        try:
            action, sid = custom_id.split(":")
            giveaway_id = int(sid)
        except Exception:
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row:
            try:
                await interaction.response.send_message(
                    embed=self._embed("Giveaway not found", "This giveaway could not be found.", discord.Color.red()),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        guild = interaction.guild
        assert guild is not None

        # Auto-end if time has passed
        if await self._end_if_overdue(guild, row):
            try:
                await interaction.response.send_message(
                    embed=self._embed("Giveaway ended", "This giveaway has already ended.", discord.Color.red()),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        if row["status"] != "running":
            try:
                await interaction.response.send_message(
                    embed=self._embed("Not running", "This giveaway is not running.", discord.Color.red()),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        member = interaction.user if isinstance(interaction.user, discord.Member) else guild.get_member(interaction.user.id)

        # Blacklist check
        if self._user_is_blacklisted(guild.id, member.id):
            try:
                await interaction.response.send_message(
                    embed=self._embed("Not eligible", "You are not eligible to participate in giveaways here.", discord.Color.red()),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        required_role_id = row["required_role_id"]
        max_entries = row["max_entries_per_user"]

        # Role requirement
        if required_role_id and not any(r.id == required_role_id for r in member.roles):
            try:
                await interaction.response.send_message(
                    embed=self._embed("Missing role", "You do not have the required role to enter this giveaway.", discord.Color.red()),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        giveaway_id_val = row["giveaway_id"]

        # Enter
        if action == "giveaway_enter":
            cursor.execute(
                "SELECT entries FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                (giveaway_id_val, member.id),
            )
            existing = cursor.fetchone()
            if existing:
                current_entries = int(existing["entries"])
                if current_entries >= max_entries:
                    try:
                        await interaction.response.send_message(
                            embed=self._embed("Entry limit reached", f"You already have the maximum of {max_entries} entries.", discord.Color.red()),
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                    return
                cursor.execute(
                    "UPDATE giveaway_entries SET entries = entries + 1 WHERE giveaway_id = ? AND user_id = ?",
                    (giveaway_id_val, member.id),
                )
            else:
                cursor.execute(
                    "INSERT INTO giveaway_entries (giveaway_id, guild_id, user_id, entries, entered_at) VALUES (?, ?, ?, ?, ?)",
                    (giveaway_id_val, guild.id, member.id, 1, unix_now()),
                )

            # Update giveaway entry count
            cursor.execute("UPDATE giveaways SET entry_count = entry_count + 1 WHERE giveaway_id = ?", (giveaway_id_val,))
            conn.commit()

            try:
                await interaction.response.send_message(
                    embed=self._embed("Entered", "You have entered the giveaway. Good luck.", discord.Color.green()),
                    ephemeral=True,
                )
            except Exception:
                pass
            audit_log(f"{member} entered giveaway {giveaway_id_val} in guild {guild.id}.")
            await self._refresh_giveaway_message(guild, giveaway_id_val, interaction.message)

        # Leave
        elif action == "giveaway_leave":
            cursor.execute(
                "SELECT entries FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                (giveaway_id_val, member.id),
            )
            existing = cursor.fetchone()
            if not existing:
                try:
                    await interaction.response.send_message(
                        embed=self._embed("No entries", "You have no entries to remove.", discord.Color.red()),
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return

            entries_count = int(existing["entries"])
            if entries_count > 1:
                cursor.execute(
                    "UPDATE giveaway_entries SET entries = entries - 1 WHERE giveaway_id = ? AND user_id = ?",
                    (giveaway_id_val, member.id),
                )
            else:
                cursor.execute(
                    "DELETE FROM giveaway_entries WHERE giveaway_id = ? AND user_id = ?",
                    (giveaway_id_val, member.id),
                )

            # Decrement global entry counter, not below zero
            cursor.execute(
                "UPDATE giveaways SET entry_count = CASE WHEN entry_count > 0 THEN entry_count - 1 ELSE 0 END WHERE giveaway_id = ?",
                (giveaway_id_val,),
            )
            conn.commit()

            try:
                await interaction.response.send_message(
                    embed=self._embed("Entry removed", "Your entry has been removed.", discord.Color.orange()),
                    ephemeral=True,
                )
            except Exception:
                pass
            audit_log(f"{member} left giveaway {giveaway_id_val} in guild {guild.id}.")
            await self._refresh_giveaway_message(guild, giveaway_id_val, interaction.message)

    # --------------------------------------------------------
    # Slash Commands
    # --------------------------------------------------------
    @app_commands.command(name="giveaway_start", description="Start a new giveaway.")
    @app_commands.describe(
        prize="The prize to be given away.",
        duration="How long the giveaway runs. Examples: 45m, 2h, 1d2h. Default from config.",
        winners="Number of winners to draw.",
        required_role="Role required to enter (optional).",
        max_entries_per_user="Max entries per user. Default from config.",
        description="Optional description or conditions for the giveaway.",
        channel="Channel to host the giveaway. Defaults to current channel.",
    )
    async def giveaway_start(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: Optional[str] = None,
        winners: Optional[int] = None,
        required_role: Optional[discord.Role] = None,
        max_entries_per_user: Optional[int] = None,
        description: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None,
    ):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed("No permission", "You do not have permission to start giveaways.", discord.Color.red()),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        # Apply defaults
        winners = winners if winners and winners > 0 else int(self.defaults["winner_count"])
        max_entries = max_entries_per_user if max_entries_per_user and max_entries_per_user > 0 else int(self.defaults["max_entries_per_user"])
        duration_str = duration or self.defaults["duration"]
        seconds = parse_duration_to_seconds(duration_str)
        if seconds is None:
            await interaction.followup.send(
                embed=self._embed("Invalid duration", "Use formats like 45m, 2h, 1d2h.", discord.Color.red()),
                ephemeral=True,
            )
            return

        end_ts = unix_now() + seconds
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                embed=self._embed("Channel required", "Please specify a text channel.", discord.Color.red()),
                ephemeral=True,
            )
            return

        # Insert into DB
        cursor.execute(
            """
            INSERT INTO giveaways
                (guild_id, channel_id, prize, description, host_id, start_time, end_time, winner_count, status, required_role_id, max_entries_per_user, entry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, 0)
            """,
            (
                guild.id,
                target_channel.id,
                prize,
                description or None,
                actor.id,
                unix_now(),
                end_ts,
                winners,
                required_role.id if required_role else None,
                max_entries,
            ),
        )
        conn.commit()
        giveaway_id = cursor.lastrowid

        # Build embed and view
        content_ping = None
        if self.ping_role_id:
            content_ping = f"<@&{self.ping_role_id}>"

        embed = self._build_giveaway_embed(
            guild=guild,
            prize=prize,
            description=description,
            host=actor,
            end_ts=end_ts,
            winner_count=winners,
            required_role_id=required_role.id if required_role else None,
            entry_count=0,
            status="running",
        )
        view = GiveawayEntryView(self, giveaway_id)

        try:
            message = await target_channel.send(content=content_ping, embed=embed, view=view)
        except Exception as e:
            logging.error(f"Failed to send giveaway message: {e}")
            await interaction.followup.send(
                embed=self._embed("Post failed", "Failed to post the giveaway message.", discord.Color.red()),
                ephemeral=True,
            )
            return

        # Update message_id and jump link
        cursor.execute("UPDATE giveaways SET message_id = ? WHERE giveaway_id = ?", (message.id, giveaway_id))
        conn.commit()

        # Edit embed to include jump URL
        try:
            jump_url = message.jump_url
            embed_with_jump = self._build_giveaway_embed(
                guild=guild,
                prize=prize,
                description=description,
                host=actor,
                end_ts=end_ts,
                winner_count=winners,
                required_role_id=required_role.id if required_role else None,
                entry_count=0,
                status="running",
                message_url=jump_url,
            )
            await message.edit(embed=embed_with_jump, view=view)
        except Exception:
            pass

        await interaction.followup.send(
            embed=self._embed("Giveaway created", f"Created in {target_channel.mention} for **{prize}**. ID: `{giveaway_id}`", discord.Color.green()),
            ephemeral=True,
        )
        audit_log(f"{actor} started giveaway {giveaway_id} in guild {guild.id} for prize '{prize}'.")

    @app_commands.command(name="giveaway_end", description="End a running giveaway now and draw winners.")
    @app_commands.describe(giveaway_id="The ID of the giveaway to end.")
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed("No permission", "You do not have permission to end giveaways.", discord.Color.red()),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed("Not found", "Giveaway not found in this server.", discord.Color.red()),
                ephemeral=True,
            )
            return
        if row["status"] != "running":
            await interaction.followup.send(
                embed=self._embed("Not running", "That giveaway is not running.", discord.Color.red()),
                ephemeral=True,
            )
            return

        # Mark as ended
        cursor.execute("UPDATE giveaways SET status = 'ended' WHERE giveaway_id = ?", (giveaway_id,))
        conn.commit()

        channel_id = row["channel_id"]
        message_id = row["message_id"]
        prize = row["prize"]
        winner_count = int(row["winner_count"])
        end_ts = unix_now()

        # Update original message embed to show ended
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
            msg = await channel.fetch_message(message_id)
            embed = self._build_giveaway_embed(
                guild=guild,
                prize=prize,
                description=row["description"],
                host=guild.get_member(row["host_id"]),
                end_ts=end_ts,
                winner_count=winner_count,
                required_role_id=row["required_role_id"],
                entry_count=self._count_entries(giveaway_id),
                status="ended",
                message_url=msg.jump_url,
            )
            await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        winners, _ = await self._announce_winners(interaction, guild, channel_id, giveaway_id, prize, winner_count)

        await interaction.followup.send(
            embed=self._embed("Giveaway ended", f"Winners selected: {len(winners)}.", discord.Color.gold()),
            ephemeral=True,
        )
        audit_log(f"{actor} ended giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(name="giveaway_reroll", description="Reroll winners for an ended giveaway.")
    @app_commands.describe(giveaway_id="The ID of the giveaway to reroll.", winners="How many winners to draw this time.")
    async def giveaway_reroll(self, interaction: discord.Interaction, giveaway_id: int, winners: Optional[int] = None):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed("No permission", "You do not have permission to reroll giveaways.", discord.Color.red()),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed("Not found", "Giveaway not found in this server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        # Strict rule: can only reroll if the giveaway has ended
        if row["status"] != "ended":
            await interaction.followup.send(
                embed=self._embed("Cannot reroll", "Only giveaways that have ended can be rerolled.", discord.Color.red()),
                ephemeral=True,
            )
            return

        channel_id = row["channel_id"]
        prize = row["prize"]
        winner_count = int(winners) if winners and winners > 0 else int(row["winner_count"])

        winners_list, _ = await self._announce_winners(interaction, guild, channel_id, giveaway_id, prize, winner_count)
        await interaction.followup.send(
            embed=self._embed("Rerolled", f"Winners selected: {len(winners_list)}.", discord.Color.gold()),
            ephemeral=True,
        )
        audit_log(f"{actor} rerolled giveaway {giveaway_id} in guild {guild.id} for {winner_count} winners.")

    @app_commands.command(name="giveaway_cancel", description="Cancel a running giveaway.")
    @app_commands.describe(giveaway_id="The ID of the giveaway to cancel.")
    async def giveaway_cancel(self, interaction: discord.Interaction, giveaway_id: int):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed("No permission", "You do not have permission to cancel giveaways.", discord.Color.red()),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed("Not found", "Giveaway not found in this server.", discord.Color.red()),
                ephemeral=True,
            )
            return
        if row["status"] != "running":
            await interaction.followup.send(
                embed=self._embed("Not running", "Only running giveaways can be cancelled.", discord.Color.red()),
                ephemeral=True,
            )
            return

        cursor.execute("UPDATE giveaways SET status = 'cancelled' WHERE giveaway_id = ?", (giveaway_id,))
        conn.commit()

        # Update original message
        channel_id = row["channel_id"]
        message_id = row["message_id"]
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
            msg = await channel.fetch_message(message_id)
            embed = self._build_giveaway_embed(
                guild=guild,
                prize=row["prize"],
                description=row["description"],
                host=guild.get_member(row["host_id"]),
                end_ts=unix_now(),
                winner_count=int(row["winner_count"]),
                required_role_id=row["required_role_id"],
                entry_count=self._count_entries(giveaway_id),
                status="cancelled",
                message_url=msg.jump_url,
            )
            await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        await interaction.followup.send(
            embed=self._embed("Cancelled", f"Giveaway `{giveaway_id}` cancelled.", discord.Color.orange()),
            ephemeral=True,
        )
        audit_log(f"{actor} cancelled giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(name="giveaway_list", description="List active giveaways in this server.")
    async def giveaway_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        # Optional: mark any overdue ones as ended so they stop showing up anywhere
        try:
            cursor.execute(
                "SELECT * FROM giveaways WHERE guild_id = ? AND status = 'running' AND end_time <= ?",
                (guild.id, unix_now()),
            )
            overdue = cursor.fetchall()
            for row in overdue:
                await self._end_if_overdue(guild, row)
        except Exception:
            pass

        giveaways = self._active_giveaways_for_guild(guild.id)
        if not giveaways:
            embed = discord.Embed(
                title="Active Giveaways",
                description="There are no active giveaways.",
                color=discord.Color.blurple(),
            )
            await interaction.response.send_message(embed=embed)
            return

        lines: List[str] = []
        for row in giveaways:
            gid = row["giveaway_id"]
            channel_id = row["channel_id"]
            prize = row["prize"]
            end_ts = row["end_time"]
            entries = row["entry_count"]
            lines.append(f"• ID `{gid}` in <#{channel_id}> - **{prize}** - ends <t:{end_ts}:R> - entries: {entries}")

        embed = discord.Embed(title="Active Giveaways", description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)
        audit_log(f"Listed active giveaways in guild {guild.id}.")

    @app_commands.command(name="giveaway_info", description="Show detailed information for a giveaway.")
    @app_commands.describe(giveaway_id="The ID of the giveaway.")
    async def giveaway_info(self, interaction: discord.Interaction, giveaway_id: int):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self._embed("Not found", "Giveaway not found in this server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        channel_id = row["channel_id"]
        message_id = row["message_id"]
        prize = row["prize"]
        description = row["description"]
        host_id = row["host_id"]
        end_ts = row["end_time"]
        winners = int(row["winner_count"])
        status = row["status"]
        required_role_id = row["required_role_id"]
        max_entries = int(row["max_entries_per_user"])
        entry_count = self._count_entries(giveaway_id)

        message_url = None
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
            msg = await channel.fetch_message(message_id)
            message_url = msg.jump_url
        except Exception:
            pass

        embed = self._build_giveaway_embed(
            guild=guild,
            prize=prize,
            description=description,
            host=guild.get_member(host_id),
            end_ts=end_ts,
            winner_count=winners,
            required_role_id=required_role_id,
            entry_count=entry_count,
            status=status,
            message_url=message_url,
        )
        embed.add_field(name="Max Entries Per User", value=str(max_entries), inline=True)
        embed.add_field(name="ID", value=str(giveaway_id), inline=True)
        await interaction.response.send_message(embed=embed)
        audit_log(f"Viewed info for giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(name="giveaway_entrants", description="List all people who have entered a giveaway.")
    @app_commands.describe(
        giveaway_id="The ID of the giveaway.",
        show_entries="If true, show each person's entry count.",
    )
    async def giveaway_entrants(self, interaction: discord.Interaction, giveaway_id: int, show_entries: Optional[bool] = True):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed("Server only", "This command must be used in a server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self._embed("Not found", "Giveaway not found in this server.", discord.Color.red()),
                ephemeral=True,
            )
            return

        entrants = self._get_entrants(giveaway_id)
        if not entrants:
            await interaction.response.send_message(
                embed=self._embed("No entrants", "Nobody has entered this giveaway yet.", discord.Color.blurple()),
                ephemeral=True,
            )
            return

        header = f"Entrants for giveaway `{giveaway_id}` - **{row['prize']}**"
        lines: List[str] = []
        for r in entrants:
            mention = f"<@{r['user_id']}>"
            if show_entries:
                lines.append(f"{mention} - {r['entries']} entries")
            else:
                lines.append(mention)

        # Chunk to respect Discord embed limits
        chunks: List[List[str]] = []
        current: List[str] = []
        current_len = 0
        for line in lines:
            add_len = len(line) + 1
            if current_len + add_len > 3800:  # safe margin under 4096 description cap
                chunks.append(current)
                current = [line]
                current_len = add_len
            else:
                current.append(line)
                current_len += add_len
        if current:
            chunks.append(current)

        # Send first as reply, rest follow-ups
        first_embed = discord.Embed(title="Giveaway Entrants", description=f"{header}\n\n" + "\n".join(chunks[0]), color=discord.Color.blurple())
        await interaction.response.send_message(embed=first_embed, ephemeral=True)

        for extra in chunks[1:]:
            emb = discord.Embed(title="Giveaway Entrants (cont.)", description="\n".join(extra), color=discord.Color.blurple())
            try:
                await interaction.followup.send(embed=emb, ephemeral=True)
            except Exception:
                break

    # --------------------------------------------------------
    # Ready: register persistent views for active giveaways
    # --------------------------------------------------------
    @commands.Cog.listener())
    async def on_ready(self) -> None:
        try:
            # Re-register persistent views for all running giveaways so buttons continue to work after restarts
            cursor.execute("SELECT giveaway_id FROM giveaways WHERE status = 'running'")
            ids = [row["giveaway_id"] for row in cursor.fetchall()]
            for gid in ids:
                self.bot.add_view(GiveawayEntryView(self, gid))
            logging.info("\033[96mGiveaways\033[0m cog synced. Persistent views restored for %d giveaways.", len(ids))
            audit_log(f"Giveaways cog ready. Restored {len(ids)} persistent views.")
        except Exception as e:
            logging.error(f"Error restoring giveaway views on_ready: {e}")
            audit_log(f"Error restoring giveaway views: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
