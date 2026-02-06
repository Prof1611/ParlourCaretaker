from __future__ import annotations

from typing import Optional, List, Tuple, Sequence

import datetime
import logging
import random
import re
import sqlite3

import discord
import yaml
from discord import app_commands
from discord.ext import commands, tasks

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

# Winners table (persistent record of who won)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS giveaway_winners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        giveaway_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        announced_at INTEGER NOT NULL,
        is_reroll INTEGER NOT NULL DEFAULT 0,
        message_id INTEGER,
        FOREIGN KEY (giveaway_id) REFERENCES giveaways(giveaway_id) ON DELETE CASCADE
    )
    """
)
conn.commit()


def _column_names(table: str) -> List[str]:
    cursor.execute(f"PRAGMA table_info({table})")
    return [row["name"] for row in cursor.fetchall()]


def _ensure_schema() -> None:
    """
    Add idempotency columns so the DB communicates clearly:
      - giveaways.winners_drawn: 0/1 flag indicating whether original winners were chosen
      - giveaways.winners_message_id: message id of the original winners announcement
      - giveaways.winners_announced_at: unix time when the original announcement was posted
    """
    cols = _column_names("giveaways")

    if "winners_drawn" not in cols:
        cursor.execute(
            "ALTER TABLE giveaways ADD COLUMN winners_drawn INTEGER NOT NULL DEFAULT 0"
        )
    if "winners_message_id" not in cols:
        cursor.execute("ALTER TABLE giveaways ADD COLUMN winners_message_id INTEGER")
    if "winners_announced_at" not in cols:
        cursor.execute("ALTER TABLE giveaways ADD COLUMN winners_announced_at INTEGER")

    # Normalise any NULLs that may exist after adding columns
    cursor.execute("UPDATE giveaways SET winners_drawn = COALESCE(winners_drawn, 0)")
    cursor.execute(
        "UPDATE giveaways SET winners_message_id = NULL WHERE winners_message_id IS NOT NULL AND CAST(winners_message_id AS TEXT) = ''"
    )
    cursor.execute(
        "UPDATE giveaways SET winners_announced_at = NULL WHERE winners_announced_at IS NOT NULL AND CAST(winners_announced_at AS TEXT) = ''"
    )
    cursor.execute(
        "UPDATE giveaways SET message_id = NULL WHERE message_id IS NOT NULL AND CAST(message_id AS TEXT) = ''"
    )
    conn.commit()


_ensure_schema()


def audit_log(message: str) -> None:
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open("audit.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception as e:
        logging.error(f"Failed to write to audit.log: {e}")


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


def humanise_remaining(seconds: int) -> str:
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
        super().__init__(timeout=None)  # persistent
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
            self.ping_role_id = (
                int(gw["ping_role_id"]) if gw.get("ping_role_id") else None
            )
            self.defaults["winner_count"] = int(gw.get("default_winner_count", 1))
            self.defaults["duration"] = str(gw.get("default_duration", "1h"))
            self.defaults["max_entries_per_user"] = int(
                gw.get("default_max_entries_per_user", 1)
            )
            labels_cfg = gw.get("labels", {})
            self.labels["enter_label"] = str(
                labels_cfg.get("enter_button_label", "Enter")
            )
            self.labels["leave_label"] = str(
                labels_cfg.get("leave_button_label", "Leave")
            )
        except Exception as e:
            logging.warning(
                f"Giveaways: failed to load config.yaml, using defaults. {e}"
            )

        # Register component callbacks for persistent custom_ids
        bot.add_listener(self.on_component_interaction, "on_interaction")

        # Background task to sweep and end overdue giveaways
        self._sweep_overdue.start()

    def cog_unload(self) -> None:
        try:
            self._sweep_overdue.cancel()
        except Exception:
            pass
        try:
            self.bot.remove_listener(self.on_component_interaction, "on_interaction")
        except Exception:
            pass

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

    @staticmethod
    def _winners_embed(
        prize: str,
        winners: Sequence[int],
        host_id: Optional[int],
        title: str = "🎉 Giveaway Winners",
    ) -> discord.Embed:
        if winners:
            mentions = " ".join(f"<@{uid}>" for uid in winners)
            contact_line = (
                f"\n\nPlease contact <@{host_id}> to collect your prize."
                if host_id
                else ""
            )
            desc = f"Congratulations {mentions}!\n\nYou won **{prize}**.{contact_line}"
        else:
            desc = "No valid entries. No winners could be selected."
        return discord.Embed(title=title, description=desc, color=discord.Color.gold())

    @staticmethod
    def _dm_winner_embed(
        guild_name: str, prize: str, host_id: Optional[int]
    ) -> discord.Embed:
        contact_line = (
            f"\n\nPlease contact <@{host_id}> to collect your prize." if host_id else ""
        )
        return discord.Embed(
            title="🎉 You won a giveaway!",
            description=f"You won **{prize}** in **{guild_name}**.{contact_line}",
            color=discord.Color.gold(),
        )

    @staticmethod
    def _dm_host_embed(
        giveaway_id: int, prize: str, winners: Sequence[int], is_reroll: bool
    ) -> discord.Embed:
        if winners:
            mentions = " ".join(f"<@{uid}>" for uid in winners)
            action = "Reroll winners" if is_reroll else "Winners"
            desc = f"{action} for giveaway `{giveaway_id}` (**{prize}**): {mentions}"
        else:
            desc = f"No valid entries were available for giveaway `{giveaway_id}` (**{prize}**)."
        return discord.Embed(
            title="Giveaway Result", description=desc, color=discord.Color.gold()
        )

    # --------------------------------------------------------
    # DB Helpers
    # --------------------------------------------------------
    def _fetch_giveaway(self, giveaway_id: int) -> Optional[sqlite3.Row]:
        cursor.execute("SELECT * FROM giveaways WHERE giveaway_id = ?", (giveaway_id,))
        return cursor.fetchone()

    def _active_giveaways_for_guild(self, guild_id: int) -> List[sqlite3.Row]:
        now = unix_now()
        cursor.execute(
            "SELECT * FROM giveaways WHERE guild_id = ? AND status = 'running' AND end_time > ? ORDER BY end_time ASC",
            (guild_id, now),
        )
        return cursor.fetchall()

    def _count_unique_entrants(self, giveaway_id: int) -> int:
        cursor.execute(
            "SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        return int(cursor.fetchone()[0])

    def _count_total_entries(self, giveaway_id: int) -> int:
        cursor.execute(
            "SELECT COALESCE(SUM(entries), 0) FROM giveaway_entries WHERE giveaway_id = ?",
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

    def _record_winners(
        self,
        giveaway_id: int,
        winners: Sequence[int],
        is_reroll: bool,
        message_id: Optional[int],
    ) -> None:
        ts = unix_now()
        rows = [
            (giveaway_id, uid, ts, 1 if is_reroll else 0, message_id) for uid in winners
        ]
        if rows:
            cursor.executemany(
                "INSERT INTO giveaway_winners (giveaway_id, user_id, announced_at, is_reroll, message_id) VALUES (?, ?, ?, ?, ?)",
                rows,
            )
        conn.commit()

    def _has_original_winners(self, giveaway_id: int) -> bool:
        cursor.execute(
            "SELECT 1 FROM giveaway_winners WHERE giveaway_id = ? AND is_reroll = 0 LIMIT 1",
            (giveaway_id,),
        )
        return cursor.fetchone() is not None

    def _existing_original_winner_ids(self, giveaway_id: int) -> List[int]:
        cursor.execute(
            "SELECT user_id FROM giveaway_winners WHERE giveaway_id = ? AND is_reroll = 0 ORDER BY id ASC",
            (giveaway_id,),
        )
        return [row["user_id"] for row in cursor.fetchall()]

    def _fetch_winners(self, giveaway_id: int, is_reroll: bool) -> List[sqlite3.Row]:
        cursor.execute(
            "SELECT user_id, announced_at FROM giveaway_winners WHERE giveaway_id = ? AND is_reroll = ? ORDER BY id ASC",
            (giveaway_id, 1 if is_reroll else 0),
        )
        return cursor.fetchall()

    def _mark_winners_drawn(self, giveaway_id: int) -> None:
        cursor.execute(
            "UPDATE giveaways SET winners_drawn = 1 WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        conn.commit()

    def _save_winners_announcement_message(
        self, giveaway_id: int, message_id: Optional[int]
    ) -> None:
        if message_id is None:
            return
        cursor.execute(
            "UPDATE giveaways SET winners_message_id = ?, winners_announced_at = ? WHERE giveaway_id = ?",
            (int(message_id), unix_now(), giveaway_id),
        )
        conn.commit()

    def _set_status_and_end_time(self, giveaway_id: int, status: str) -> None:
        # Keep end_time accurate for "Ended" display if the giveaway is ended early or cancelled.
        cursor.execute(
            "UPDATE giveaways SET status = ?, end_time = ? WHERE giveaway_id = ?",
            (status, unix_now(), giveaway_id),
        )
        conn.commit()

    # --------------------------------------------------------
    # Idempotent Winner Flow
    # --------------------------------------------------------
    async def _choose_original_winners_once(
        self, giveaway_id: int, desired_count: int
    ) -> List[int]:
        """
        Choose original winners exactly once. If already chosen, return the existing list.
        If not, select from entrants with weighting, record to DB, and mark winners_drawn.
        """
        if self._has_original_winners(giveaway_id):
            return self._existing_original_winner_ids(giveaway_id)

        entrants_rows = self._get_entrants(giveaway_id)

        # Build "ticket bucket" with weighting (each entry is a ticket).
        tickets: List[int] = []
        for r in entrants_rows:
            uid = int(r["user_id"])
            count = int(max(1, int(r["entries"])))
            tickets.extend([uid] * count)

        winners: List[int] = []
        desired = max(0, int(desired_count))
        if tickets and desired > 0:
            # Weighted without replacement:
            # pick from tickets; when a user wins, remove all of their tickets.
            while tickets and len(winners) < desired:
                pick_uid = random.choice(tickets)
                if pick_uid not in winners:
                    winners.append(pick_uid)
                tickets = [u for u in tickets if u != pick_uid]

        self._record_winners(
            giveaway_id=giveaway_id, winners=winners, is_reroll=False, message_id=None
        )
        self._mark_winners_drawn(giveaway_id)

        audit_log(
            f"Original winners drawn for giveaway {giveaway_id}: {', '.join(map(str, winners)) if winners else 'no winners'}"
        )
        return winners

    async def _announce_original_winners_once(
        self,
        guild: discord.Guild,
        row: sqlite3.Row,
        title: str = "🎉 Giveaway Winners",
    ) -> Tuple[List[int], Optional[discord.Message]]:
        """
        Announce original winners at most once. If winners already chosen, do not pick again.
        If an announcement message was already posted, do not post another.
        """
        giveaway_id = row["giveaway_id"]
        channel_id = row["channel_id"]
        prize = row["prize"]
        winner_count = int(row["winner_count"])
        host_id = row["host_id"]

        winners = await self._choose_original_winners_once(giveaway_id, winner_count)

        if row["winners_message_id"]:
            audit_log(
                f"Skip duplicate announce for giveaway {giveaway_id}. Existing message id {row['winners_message_id']}."
            )
            return winners, None

        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(
                channel_id
            )
            embed = self._winners_embed(prize, winners, host_id, title=title)
            msg = await channel.send(embed=embed)
            self._save_winners_announcement_message(giveaway_id, msg.id)

            for uid in winners:
                try:
                    user = guild.get_member(uid) or await guild.fetch_member(uid)
                    await user.send(
                        embed=self._dm_winner_embed(guild.name, prize, host_id)
                    )
                except Exception:
                    pass

            if host_id:
                try:
                    host_member = guild.get_member(host_id) or await guild.fetch_member(
                        host_id
                    )
                    await host_member.send(
                        embed=self._dm_host_embed(
                            giveaway_id, prize, winners, is_reroll=False
                        )
                    )
                except Exception:
                    pass

            return winners, msg
        except Exception as e:
            logging.warning(
                f"Failed to post winners message for giveaway {giveaway_id}: {e}"
            )
            return winners, None

    async def _announce_reroll_winners(
        self,
        guild: discord.Guild,
        row: sqlite3.Row,
        winners_to_draw: int,
        title: str = "🎉 Giveaway Winners (reroll)",
    ) -> Tuple[List[int], Optional[discord.Message]]:
        """
        Always draw and announce reroll winners. These are recorded separately (is_reroll = 1).
        """
        giveaway_id = row["giveaway_id"]
        channel_id = row["channel_id"]
        prize = row["prize"]
        host_id = row["host_id"]

        entrants_rows = self._get_entrants(giveaway_id)
        tickets: List[int] = []
        for r in entrants_rows:
            uid = int(r["user_id"])
            count = int(max(1, int(r["entries"])))
            tickets.extend([uid] * count)

        winners: List[int] = []
        desired = max(0, int(winners_to_draw))
        if tickets and desired > 0:
            while tickets and len(winners) < desired:
                pick_uid = random.choice(tickets)
                if pick_uid not in winners:
                    winners.append(pick_uid)
                tickets = [u for u in tickets if u != pick_uid]

        msg: Optional[discord.Message] = None
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(
                channel_id
            )
            embed = self._winners_embed(prize, winners, host_id, title=title)
            msg = await channel.send(embed=embed)
        except Exception:
            msg = None

        self._record_winners(
            giveaway_id=giveaway_id,
            winners=winners,
            is_reroll=True,
            message_id=(msg.id if msg else None),
        )
        audit_log(
            f"Giveaway {giveaway_id} reroll winners: {', '.join(map(str, winners)) if winners else 'no winners'}"
        )

        for uid in winners:
            try:
                user = guild.get_member(uid) or await guild.fetch_member(uid)
                await user.send(embed=self._dm_winner_embed(guild.name, prize, host_id))
            except Exception:
                pass

        if host_id:
            try:
                host_member = guild.get_member(host_id) or await guild.fetch_member(
                    host_id
                )
                await host_member.send(
                    embed=self._dm_host_embed(
                        giveaway_id, prize, winners, is_reroll=True
                    )
                )
            except Exception:
                pass

        return winners, msg

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
            else (
                discord.Color.red() if status == "cancelled" else discord.Color.gold()
            )
        )

        safe_desc = (description or "").strip()

        embed = discord.Embed(
            title="🎁 Giveaway",
            description=safe_desc if safe_desc else "",
            color=colour,
        )
        embed.add_field(name="Prize", value=prize, inline=False)
        embed.add_field(name="Winners", value=str(winner_count), inline=True)
        if status == "running":
            embed.add_field(name="Ends", value=f"{pretty_time}", inline=True)
            embed.add_field(
                name="Time Remaining", value=humanise_remaining(remaining), inline=True
            )
        else:
            embed.add_field(name="Ended", value=f"{pretty_time}", inline=True)

        embed.add_field(name="Entries", value=str(entry_count), inline=True)

        if required_role_id:
            embed.add_field(
                name="Requirement", value=f"<@&{required_role_id}>", inline=True
            )
        if host:
            embed.set_footer(text=f"Hosted by {host.display_name}")
            try:
                embed.set_author(
                    name=host.display_name, icon_url=host.display_avatar.url
                )
            except Exception:
                embed.set_author(name=host.display_name)
        if message_url:
            embed.add_field(
                name="Jump", value=f"[Go to message]({message_url})", inline=False
            )
        return embed

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
            entry_count = self._count_total_entries(giveaway_id)
            channel = guild.get_channel(row["channel_id"]) or await guild.fetch_channel(
                row["channel_id"]
            )

            message_id_val: Optional[int]
            try:
                message_id_val = (
                    int(row["message_id"])
                    if row["message_id"] is not None
                    and str(row["message_id"]).strip() != ""
                    else None
                )
            except (TypeError, ValueError):
                message_id_val = None

            msg: Optional[discord.Message]
            if message_hint and (
                message_id_val is None
                or (
                    message_hint.id == message_id_val
                    and message_hint.channel.id == row["channel_id"]
                )
            ):
                msg = message_hint
            elif message_id_val is not None:
                try:
                    msg = await channel.fetch_message(message_id_val)
                except Exception:
                    msg = None
            else:
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
            )
            view = (
                GiveawayEntryView(self, giveaway_id)
                if row["status"] == "running"
                else None
            )
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logging.warning(f"Failed to refresh giveaway message {giveaway_id}: {e}")

    async def _end_if_overdue(self, guild: discord.Guild, row: sqlite3.Row) -> bool:
        """
        If the giveaway has passed its end_time, end it now and announce winners.
        Returns True if it was ended here.
        """
        if row["status"] != "running" or row["end_time"] > unix_now():
            return False
        try:
            await self._end_and_announce_now(guild, row)
            audit_log(
                f"Auto-ended giveaway {row['giveaway_id']} in guild {row['guild_id']} and handled winners idempotently."
            )
            return True
        except Exception as e:
            logging.warning(
                f"Failed to auto-end overdue giveaway {row['giveaway_id']}: {e}"
            )
            return False

    async def _announce_if_missing(
        self, guild: discord.Guild, row: sqlite3.Row
    ) -> bool:
        """
        If a giveaway is already ended but has no original winners recorded,
        announce original winners now. Returns True if announced.
        """
        if row["status"] != "ended":
            return False
        if self._has_original_winners(row["giveaway_id"]):
            return False
        try:
            await self._refresh_giveaway_message(guild, row["giveaway_id"])
            await self._announce_original_winners_once(
                guild=guild,
                row=row,
                title="🎉 Giveaway Winners",
            )
            audit_log(
                f"Late-announced winners for giveaway {row['giveaway_id']} in guild {row['guild_id']} (first and only time)."
            )
            return True
        except Exception as e:
            logging.warning(
                f"Failed to late-announce winners for giveaway {row['giveaway_id']}: {e}"
            )
            return False

    async def _end_and_announce_now(
        self, guild: discord.Guild, row: sqlite3.Row
    ) -> List[int]:
        """
        Helper to mark a running giveaway as ended now, update message,
        and announce winners exactly once. Returns list of original winners.
        """
        giveaway_id = row["giveaway_id"]

        try:
            self._set_status_and_end_time(giveaway_id, "ended")
        except Exception:
            pass

        # Update original message to show ended (and remove buttons)
        try:
            channel = guild.get_channel(row["channel_id"]) or await guild.fetch_channel(
                row["channel_id"]
            )
            msg = None
            if row["message_id"]:
                try:
                    msg = await channel.fetch_message(row["message_id"])
                except Exception:
                    msg = None

            ended_row = self._fetch_giveaway(giveaway_id)
            if ended_row and msg:
                embed = self._build_giveaway_embed(
                    guild=guild,
                    prize=ended_row["prize"],
                    description=ended_row["description"],
                    host=guild.get_member(ended_row["host_id"]),
                    end_ts=ended_row["end_time"],
                    winner_count=int(ended_row["winner_count"]),
                    required_role_id=ended_row["required_role_id"],
                    entry_count=self._count_total_entries(giveaway_id),
                    status="ended",
                )
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        fresh = self._fetch_giveaway(giveaway_id)
        if not fresh:
            return []
        winners, _ = await self._announce_original_winners_once(
            guild, fresh, title="🎉 Giveaway Winners"
        )
        return winners

    # --------------------------------------------------------
    # Background Sweeper
    # --------------------------------------------------------
    @tasks.loop(seconds=60)
    async def _sweep_overdue(self) -> None:
        try:
            now = unix_now()
            cursor.execute(
                "SELECT * FROM giveaways WHERE status = 'running' AND end_time <= ?",
                (now,),
            )
            rows = cursor.fetchall()
            for row in rows:
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    try:
                        guild = await self.bot.fetch_guild(row["guild_id"])
                    except Exception:
                        continue
                await self._end_if_overdue(guild, row)
        except Exception as e:
            logging.warning(f"Giveaways sweep failed: {e}")

    @_sweep_overdue.before_loop
    async def _sweep_overdue_before_loop(self) -> None:
        await self.bot.wait_until_ready()

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

        if not (
            custom_id.startswith("giveaway_enter:")
            or custom_id.startswith("giveaway_leave:")
        ):
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
                    embed=self._embed(
                        "Giveaway not found",
                        "This giveaway could not be found.",
                        discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        guild = interaction.guild
        if guild is None:
            return

        # Auto-end if time has passed (and handle winners idempotently)
        if await self._end_if_overdue(guild, row):
            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Giveaway ended",
                        "This giveaway has already ended.",
                        discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        if row["status"] != "running":
            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Not running",
                        "This giveaway is not running.",
                        discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        member = (
            interaction.user
            if isinstance(interaction.user, discord.Member)
            else guild.get_member(interaction.user.id)
        )
        if not isinstance(member, discord.Member):
            return

        # Blacklist check
        if self._user_is_blacklisted(guild.id, member.id):
            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Not eligible",
                        "You are not eligible to participate in giveaways here.",
                        discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        required_role_id = row["required_role_id"]
        max_entries = int(row["max_entries_per_user"])

        # Role requirement
        if required_role_id and not any(r.id == required_role_id for r in member.roles):
            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Missing role",
                        "You do not have the required role to enter this giveaway.",
                        discord.Color.red(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass
            return

        giveaway_id_val = int(row["giveaway_id"])

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
                            embed=self._embed(
                                "Entry limit reached",
                                f"You already have the maximum of {max_entries} entries.",
                                discord.Color.red(),
                            ),
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

            # Keep legacy giveaways.entry_count in sync with total entries
            cursor.execute(
                "UPDATE giveaways SET entry_count = entry_count + 1 WHERE giveaway_id = ?",
                (giveaway_id_val,),
            )
            conn.commit()

            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Entered",
                        "You have entered the giveaway. Good luck.",
                        discord.Color.green(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass

            audit_log(
                f"{member} entered giveaway {giveaway_id_val} in guild {guild.id}."
            )
            await self._refresh_giveaway_message(
                guild, giveaway_id_val, interaction.message
            )

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
                        embed=self._embed(
                            "No entries",
                            "You have no entries to remove.",
                            discord.Color.red(),
                        ),
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

            cursor.execute(
                "UPDATE giveaways SET entry_count = CASE WHEN entry_count > 0 THEN entry_count - 1 ELSE 0 END WHERE giveaway_id = ?",
                (giveaway_id_val,),
            )
            conn.commit()

            try:
                await interaction.response.send_message(
                    embed=self._embed(
                        "Entry removed",
                        "Your entry has been removed.",
                        discord.Color.orange(),
                    ),
                    ephemeral=True,
                )
            except Exception:
                pass

            audit_log(f"{member} left giveaway {giveaway_id_val} in guild {guild.id}.")
            await self._refresh_giveaway_message(
                guild, giveaway_id_val, interaction.message
            )

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
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed(
                    "No permission",
                    "You do not have permission to start giveaways.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        winners = (
            winners if winners and winners > 0 else int(self.defaults["winner_count"])
        )
        max_entries = (
            max_entries_per_user
            if max_entries_per_user and max_entries_per_user > 0
            else int(self.defaults["max_entries_per_user"])
        )
        duration_str = duration or str(self.defaults["duration"])
        seconds = parse_duration_to_seconds(duration_str)
        if seconds is None:
            await interaction.followup.send(
                embed=self._embed(
                    "Invalid duration",
                    "Use formats like 45m, 2h, 1d2h.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        end_ts = unix_now() + seconds
        target_channel = channel or interaction.channel
        if not isinstance(target_channel, discord.TextChannel):
            await interaction.followup.send(
                embed=self._embed(
                    "Channel required",
                    "Please specify a text channel.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        cursor.execute(
            """
            INSERT INTO giveaways
                (guild_id, channel_id, prize, description, host_id, start_time, end_time, winner_count, status, required_role_id, max_entries_per_user, entry_count, winners_drawn, winners_message_id, winners_announced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, 0, 0, NULL, NULL)
            """,
            (
                guild.id,
                target_channel.id,
                prize,
                (description.strip() if description and description.strip() else None),
                actor.id,
                unix_now(),
                end_ts,
                int(winners),
                (required_role.id if required_role else None),
                int(max_entries),
            ),
        )
        conn.commit()
        giveaway_id = cursor.lastrowid

        embed = self._build_giveaway_embed(
            guild=guild,
            prize=prize,
            description=description,
            host=actor,
            end_ts=end_ts,
            winner_count=int(winners),
            required_role_id=(required_role.id if required_role else None),
            entry_count=0,
            status="running",
        )
        view = GiveawayEntryView(self, giveaway_id)

        try:
            content_ping = f"<@&{self.ping_role_id}>" if self.ping_role_id else None
            message = await target_channel.send(
                content=content_ping, embed=embed, view=view
            )
        except Exception as e:
            logging.error(f"Failed to send giveaway message: {e}")
            await interaction.followup.send(
                embed=self._embed(
                    "Post failed",
                    "Failed to post the giveaway message.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        cursor.execute(
            "UPDATE giveaways SET message_id = ? WHERE giveaway_id = ?",
            (message.id, giveaway_id),
        )
        conn.commit()

        await interaction.followup.send(
            embed=self._embed(
                "Giveaway created",
                f"Created in {target_channel.mention} for **{prize}**. ID: `{giveaway_id}`",
                discord.Color.green(),
            ),
            ephemeral=True,
        )
        audit_log(
            f"{actor} started giveaway {giveaway_id} in guild {guild.id} for prize '{prize}'."
        )

    @app_commands.command(
        name="giveaway_end", description="End a running giveaway now and draw winners."
    )
    @app_commands.describe(giveaway_id="The ID of the giveaway to end.")
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: int):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed(
                    "No permission",
                    "You do not have permission to end giveaways.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        try:
            await interaction.response.defer(ephemeral=False, thinking=True)
        except discord.NotFound:
            logging.warning(
                "Interaction for giveaway_end expired before response could be sent."
            )
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed(
                    "Not found",
                    "Giveaway not found in this server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return
        if row["status"] != "running":
            await interaction.followup.send(
                embed=self._embed(
                    "Not running",
                    "That giveaway is not running.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        winners = await self._end_and_announce_now(guild, row)

        await interaction.followup.send(
            embed=self._embed(
                "Giveaway ended",
                f"Winners selected: {len(winners)}.",
                discord.Color.gold(),
            ),
            ephemeral=True,
        )
        audit_log(f"{actor} ended giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(
        name="giveaway_reroll", description="Reroll winners for an ended giveaway."
    )
    @app_commands.describe(
        giveaway_id="The ID of the giveaway to reroll.",
        winners="How many winners to draw this time.",
    )
    async def giveaway_reroll(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        winners: Optional[int] = None,
    ):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed(
                    "No permission",
                    "You do not have permission to reroll giveaways.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed(
                    "Not found",
                    "Giveaway not found in this server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if row["status"] != "ended":
            await interaction.followup.send(
                embed=self._embed(
                    "Cannot reroll",
                    "Only giveaways that have ended can be rerolled.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        winner_count = (
            int(winners) if winners and winners > 0 else int(row["winner_count"])
        )
        winners_list, _ = await self._announce_reroll_winners(
            guild,
            row,
            winner_count,
            title="🎉 Giveaway Winners (reroll)",
        )
        await interaction.followup.send(
            embed=self._embed(
                "Rerolled",
                f"Winners selected: {len(winners_list)}.",
                discord.Color.gold(),
            ),
            ephemeral=True,
        )
        audit_log(
            f"{actor} rerolled giveaway {giveaway_id} in guild {guild.id} for {winner_count} winners."
        )

    @app_commands.command(
        name="giveaway_cancel", description="Cancel a running giveaway."
    )
    @app_commands.describe(giveaway_id="The ID of the giveaway to cancel.")
    async def giveaway_cancel(self, interaction: discord.Interaction, giveaway_id: int):
        actor = interaction.user
        guild = interaction.guild
        if not isinstance(actor, discord.Member) or guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        if not self._is_manager(actor):
            await interaction.response.send_message(
                embed=self._embed(
                    "No permission",
                    "You do not have permission to cancel giveaways.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=False, thinking=True)

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.followup.send(
                embed=self._embed(
                    "Not found",
                    "Giveaway not found in this server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return
        if row["status"] != "running":
            await interaction.followup.send(
                embed=self._embed(
                    "Not running",
                    "Only running giveaways can be cancelled.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        try:
            self._set_status_and_end_time(giveaway_id, "cancelled")
        except Exception:
            pass

        # Update original message
        try:
            fresh = self._fetch_giveaway(giveaway_id)
            if fresh:
                channel = guild.get_channel(
                    fresh["channel_id"]
                ) or await guild.fetch_channel(fresh["channel_id"])
                msg = await channel.fetch_message(fresh["message_id"])
                embed = self._build_giveaway_embed(
                    guild=guild,
                    prize=fresh["prize"],
                    description=fresh["description"],
                    host=guild.get_member(fresh["host_id"]),
                    end_ts=fresh["end_time"],
                    winner_count=int(fresh["winner_count"]),
                    required_role_id=fresh["required_role_id"],
                    entry_count=self._count_total_entries(giveaway_id),
                    status="cancelled",
                )
                await msg.edit(embed=embed, view=None)
        except Exception:
            pass

        await interaction.followup.send(
            embed=self._embed(
                "Cancelled",
                f"Giveaway `{giveaway_id}` cancelled.",
                discord.Color.orange(),
            ),
            ephemeral=True,
        )
        audit_log(f"{actor} cancelled giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(
        name="giveaway_list", description="List active giveaways in this server."
    )
    async def giveaway_list(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        # Optional: mark any overdue ones as ended so they stop showing up
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
            entries = int(row["entry_count"])
            lines.append(
                f"• ID `{gid}` in <#{channel_id}> - **{prize}** - ends <t:{end_ts}:R> - entries: {entries}"
            )

        embed = discord.Embed(
            title="Active Giveaways",
            description="\n".join(lines),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=embed)
        audit_log(f"Listed active giveaways in guild {guild.id}.")

    @app_commands.command(
        name="giveaway_info", description="Show detailed information for a giveaway."
    )
    @app_commands.describe(giveaway_id="The ID of the giveaway.")
    async def giveaway_info(self, interaction: discord.Interaction, giveaway_id: int):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self._embed(
                    "Not found",
                    "Giveaway not found in this server.",
                    discord.Color.red(),
                ),
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
        entry_count = self._count_total_entries(giveaway_id)
        winners_drawn = int(row["winners_drawn"])
        winners_msg_id = row["winners_message_id"]
        winners_announced_at = row["winners_announced_at"]

        message_url = None
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(
                channel_id
            )
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
        embed.add_field(
            name="Max Entries Per User", value=str(max_entries), inline=True
        )
        embed.add_field(name="ID", value=str(giveaway_id), inline=True)
        embed.add_field(
            name="Unique Entrants",
            value=str(self._count_unique_entrants(giveaway_id)),
            inline=True,
        )

        orig_winners = self._fetch_winners(giveaway_id, is_reroll=False)
        reroll_winners = self._fetch_winners(giveaway_id, is_reroll=True)

        def fmt_winners(rows: List[sqlite3.Row]) -> str:
            if not rows:
                return "None recorded"
            parts = []
            for r in rows:
                uid = r["user_id"]
                ts = r["announced_at"]
                parts.append(f"<@{uid}> <t:{ts}:R>")
            return "\n".join(parts)

        embed.add_field(
            name="Original Winners", value=fmt_winners(orig_winners), inline=False
        )
        if reroll_winners:
            embed.add_field(
                name="Reroll Winners", value=fmt_winners(reroll_winners), inline=False
            )

        drawn_state = "Yes" if winners_drawn else "No"
        announced_state = (
            f"Yes (message id {winners_msg_id}, <t:{winners_announced_at}:R>)"
            if winners_msg_id
            else "No"
        )
        embed.add_field(name="Winners Drawn", value=drawn_state, inline=True)
        embed.add_field(
            name="Original Announcement Posted", value=announced_state, inline=True
        )

        await interaction.response.send_message(embed=embed)
        audit_log(f"Viewed info for giveaway {giveaway_id} in guild {guild.id}.")

    @app_commands.command(
        name="giveaway_entrants",
        description="List all people who have entered a giveaway.",
    )
    @app_commands.describe(
        giveaway_id="The ID of the giveaway.",
        show_entries="If true, show each person's entry count.",
    )
    async def giveaway_entrants(
        self,
        interaction: discord.Interaction,
        giveaway_id: int,
        show_entries: Optional[bool] = True,
    ):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                embed=self._embed(
                    "Server only",
                    "This command must be used in a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        row = self._fetch_giveaway(giveaway_id)
        if not row or row["guild_id"] != guild.id:
            await interaction.response.send_message(
                embed=self._embed(
                    "Not found",
                    "Giveaway not found in this server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
            return

        entrants = self._get_entrants(giveaway_id)
        if not entrants:
            await interaction.response.send_message(
                embed=self._embed(
                    "No entrants",
                    "Nobody has entered this giveaway yet.",
                    discord.Color.blurple(),
                ),
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

        chunks: List[List[str]] = []
        current: List[str] = []
        current_len = 0
        for line in lines:
            add_len = len(line) + 1
            if current_len + add_len > 3800:
                chunks.append(current)
                current = [line]
                current_len = add_len
            else:
                current.append(line)
                current_len += add_len
        if current:
            chunks.append(current)

        first_embed = discord.Embed(
            title="Giveaway Entrants",
            description=f"{header}\n\n" + "\n".join(chunks[0]),
            color=discord.Color.blurple(),
        )
        await interaction.response.send_message(embed=first_embed, ephemeral=True)

        for extra in chunks[1:]:
            emb = discord.Embed(
                title="Giveaway Entrants (cont.)",
                description="\n".join(extra),
                color=discord.Color.blurple(),
            )
            try:
                await interaction.followup.send(embed=emb, ephemeral=True)
            except Exception:
                break

    # --------------------------------------------------------
    # Ready: register persistent views for active giveaways and sweep overdue
    # --------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self) -> None:
        try:
            cursor.execute("SELECT giveaway_id FROM giveaways WHERE status = 'running'")
            ids = [row["giveaway_id"] for row in cursor.fetchall()]
            for gid in ids:
                self.bot.add_view(GiveawayEntryView(self, gid))

            now = unix_now()
            cursor.execute(
                "SELECT * FROM giveaways WHERE status = 'running' AND end_time <= ?",
                (now,),
            )
            overdue = cursor.fetchall()
            for row in overdue:
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    try:
                        guild = await self.bot.fetch_guild(row["guild_id"])
                    except Exception:
                        continue
                await self._end_if_overdue(guild, row)

            cursor.execute("SELECT * FROM giveaways WHERE status = 'ended'")
            ended = cursor.fetchall()
            for row in ended:
                if self._has_original_winners(row["giveaway_id"]):
                    continue
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    try:
                        guild = await self.bot.fetch_guild(row["guild_id"])
                    except Exception:
                        continue
                await self._announce_if_missing(guild, row)

            logging.info(
                "\033[96mGiveaways\033[0m cog synced. Persistent views restored for %d giveaways. Overdue processed: %d.",
                len(ids),
                len(overdue),
            )
            audit_log(
                f"Giveaways cog ready. Restored {len(ids)} persistent views. Processed {len(overdue)} overdue giveaways."
            )
        except Exception as e:
            logging.error(f"Error restoring giveaway views on_ready: {e}")
            audit_log(f"Error restoring giveaway views: {e}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Giveaways(bot))
