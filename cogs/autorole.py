import discord
import logging
import sqlite3
from discord.ext import commands, tasks
import datetime
import yaml


def audit_log(message: str):
    """Append a timestamped message to the audit log file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("audit.log", "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load the configuration file (UTF-8 for special characters)
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        # Get the Role IDs from config
        self.newjoin_role_id = self.config.get("newjoin_role_id")
        self.dinner_guest_role_id = self.config.get("dinner_guest_role_id")
        # Check if autorole is enabled; default is True if not specified.
        self.autorole_enabled = self.config.get("autorole_enabled", True)

        # Connect to the database (database.db) for persisting scheduled role removals.
        # check_same_thread=False is used for multi-threaded access.
        self.db = sqlite3.connect("database.db", check_same_thread=False)
        self.db.row_factory = sqlite3.Row  # Allows column access by name.
        self.create_table()

        # Start the background task to check for scheduled role removals.
        self.check_roles.start()

    def create_table(self):
        """Create the scheduled_role_removals table if it doesn't already exist."""
        with self.db:
            self.db.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_role_removals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    member_id INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    removal_time TEXT NOT NULL
                )
                """
            )

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info("\033[96mAutoRole\033[0m cog synced successfully.")
        audit_log("AutoRole cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Check if autorole feature is enabled.
        if not self.autorole_enabled:
            logging.info(
                "Autorole is disabled in the configuration. Skipping role assignment."
            )
            audit_log(
                f"AutoRole disabled: Skipped role assignment for {member} in guild '{member.guild.name}' (ID: {member.guild.id})."
            )
            return

        # Retrieve roles from config and attempt to get them from the guild.
        role_ids = [self.newjoin_role_id, self.dinner_guest_role_id]
        roles = []
        for role_id in role_ids:
            try:
                role = member.guild.get_role(role_id)
                if role is None:
                    logging.error(
                        f"Role with ID '{role_id}' not found in guild '{member.guild.name}'."
                    )
                    audit_log(
                        f"Error: Role with ID '{role_id}' not found in guild '{member.guild.name}' (ID: {member.guild.id})."
                    )
                else:
                    roles.append(role)
            except Exception as e:
                logging.error(
                    f"Error retrieving role with ID '{role_id}' in guild '{member.guild.name}': {e}"
                )
                audit_log(
                    f"Error retrieving role with ID '{role_id}' in guild '{member.guild.name}' (ID: {member.guild.id}): {e}"
                )

        if not roles:
            # No valid roles found; nothing to assign.
            return

        try:
            await member.add_roles(*roles, reason="Auto-assigned roles on join")
            for role in roles:
                logging.info(
                    f"Assigned role '{role.name}' to new member '@{member.name}'."
                )
                audit_log(
                    f"Assigned role '{role.name}' (ID: {role.id}) to new member '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id})."
                )
                # Schedule removal of the new joiner role after 1 week if applicable.
                if role.id == self.newjoin_role_id:
                    removal_time = (
                        (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(days=7)
                        )
                        .replace(microsecond=0)
                        .isoformat(sep=" ")
                    )
                    with self.db:
                        self.db.execute(
                            "INSERT INTO scheduled_role_removals (guild_id, member_id, role_id, removal_time) VALUES (?, ?, ?, ?)",
                            (member.guild.id, member.id, role.id, removal_time),
                        )
                    logging.info(
                        f"Scheduled removal of role '{role.name}' from '@{member.name}' at {removal_time}."
                    )
                    audit_log(
                        f"Scheduled removal of role '{role.name}' (ID: {role.id}) from '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id}) at {removal_time}."
                    )
        except discord.Forbidden:
            logging.error(
                f"Forbidden error when assigning roles to '@{member.name}'. Check permissions and role hierarchy."
            )
            audit_log(
                f"Forbidden error: Failed to assign roles to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id})."
            )
        except discord.HTTPException as http_e:
            logging.error(
                f"HTTP error occurred while assigning roles to '@{member.name}': {http_e}"
            )
            audit_log(
                f"HTTP error: Failed to assign roles to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id}): {http_e}"
            )
        except Exception as e:
            logging.error(
                f"Unexpected error when assigning roles to '@{member.name}': {e}"
            )
            audit_log(
                f"Unexpected error: Failed to assign roles to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id}): {e}"
            )

    @tasks.loop(seconds=15)
    async def check_roles(self):
        """Background task that periodically checks the database for scheduled role removals."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db:
            rows = self.db.execute(
                "SELECT id, guild_id, member_id, role_id, removal_time FROM scheduled_role_removals WHERE removal_time <= ?",
                (now,),
            ).fetchall()

        for row in rows:
            removal_id = row["id"]
            guild_id = row["guild_id"]
            member_id = row["member_id"]
            role_id = row["role_id"]

            guild = self.bot.get_guild(guild_id)
            if guild is None:
                logging.error(f"Guild with ID '{guild_id}' not found.")
                audit_log(
                    f"Error: Guild with ID '{guild_id}' not found for scheduled removal ID {removal_id}."
                )
                with self.db:
                    self.db.execute(
                        "DELETE FROM scheduled_role_removals WHERE id = ?",
                        (removal_id,),
                    )
                continue

            member = guild.get_member(member_id)
            if member is None:
                logging.error(
                    f"Member with ID '{member_id}' not found in guild '{guild.name}'."
                )
                audit_log(
                    f"Error: Member with ID '{member_id}' not found in guild '{guild.name}' for scheduled removal ID {removal_id}."
                )
                with self.db:
                    self.db.execute(
                        "DELETE FROM scheduled_role_removals WHERE id = ?",
                        (removal_id,),
                    )
                continue

            role = guild.get_role(role_id)
            if role is None:
                logging.error(
                    f"Role with ID '{role_id}' not found in guild '{guild.name}'."
                )
                audit_log(
                    f"Error: Role with ID '{role_id}' not found in guild '{guild.name}' for scheduled removal ID {removal_id}."
                )
                with self.db:
                    self.db.execute(
                        "DELETE FROM scheduled_role_removals WHERE id = ?",
                        (removal_id,),
                    )
                continue

            try:
                await member.remove_roles(
                    role, reason="Auto-removed new joiner role after 1 week"
                )
                logging.info(
                    f"Removed role '{role.name}' from member '@{member.name}' after scheduled delay."
                )
                audit_log(
                    f"Removed role '{role.name}' (ID: {role.id}) from member '@{member.name}' in guild '{guild.name}' (ID: {guild.id}) after scheduled delay."
                )
            except discord.Forbidden:
                logging.error(
                    f"Forbidden error when removing role '{role.name}' from '@{member.name}'. Check permissions and role hierarchy."
                )
                audit_log(
                    f"Forbidden error: Failed to remove role '{role.name}' from '@{member.name}' in guild '{guild.name}' (ID: {guild.id})."
                )
            except discord.HTTPException as http_e:
                logging.error(
                    f"HTTP error occurred while removing role '{role.name}' from '@{member.name}': {http_e}"
                )
                audit_log(
                    f"HTTP error: Failed to remove role '{role.name}' from '@{member.name}' in guild '{guild.name}' (ID: {guild.id}): {http_e}"
                )
            except Exception as e:
                logging.error(
                    f"Unexpected error when removing role '{role.name}' from '@{member.name}': {e}"
                )
                audit_log(
                    f"Unexpected error: Failed to remove role '{role.name}' from '@{member.name}' in guild '{guild.name}' (ID: {guild.id}): {e}"
                )
            # Delete the record regardless of the outcome.
            with self.db:
                self.db.execute(
                    "DELETE FROM scheduled_role_removals WHERE id = ?", (removal_id,)
                )

    @check_roles.before_loop
    async def before_check_roles(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
