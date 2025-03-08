import discord
import logging
import yaml
from discord.ext import commands
import datetime


class AutoRole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Load the config file (UTF-8 for special characters)
        with open("config.yaml", "r", encoding="utf-8") as config_file:
            self.config = yaml.safe_load(config_file)
        # Get the Role ID to assign to new joiners from config
        self.newjoin_role_id = self.config.get("newjoin_role_id")
        # Check if auto-role is enabled; default is True if not specified.
        self.autorole_enabled = self.config.get("autorole_enabled", True)

    def audit_log(self, message: str):
        """Append a timestamped message to the audit log file."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open("audit.log", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[96mAutoRole\033[0m cog synced successfully.")
        self.audit_log("AutoRole cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Check if autorole feature is enabled.
        if not self.autorole_enabled:
            logging.info(
                "Autorole is disabled in the configuration. Skipping role assignment."
            )
            self.audit_log(
                f"AutoRole disabled: Skipped role assignment for {member} in guild '{member.guild.name}' (ID: {member.guild.id})."
            )
            return

        role_id = self.newjoin_role_id
        try:
            role = member.guild.get_role(role_id)
            if not role:
                logging.error(
                    f"Role with ID '{role_id}' not found in guild '{member.guild.name}'."
                )
                self.audit_log(
                    f"Error: Role with ID '{role_id}' not found in guild '{member.guild.name}' (ID: {member.guild.id})."
                )
                return
        except Exception as e:
            logging.error(
                f"Error retrieving role with ID '{role_id}' in guild '{member.guild.name}': {e}"
            )
            self.audit_log(
                f"Error retrieving role with ID '{role_id}' in guild '{member.guild.name}' (ID: {member.guild.id}): {e}"
            )
            return

        try:
            await member.add_roles(role, reason="Auto-assigned role on join")
            logging.info(f"Assigned role '{role.name}' to new member '@{member.name}'.")
            self.audit_log(
                f"Assigned role '{role.name}' (ID: {role.id}) to new member '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id})."
            )
        except discord.Forbidden:
            logging.error(
                f"Forbidden error when assigning role to '@{member.name}'. Check permissions and role hierarchy."
            )
            self.audit_log(
                f"Forbidden error: Failed to assign role to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id})."
            )
        except discord.HTTPException as http_e:
            logging.error(
                f"HTTP error occurred while assigning role to '@{member.name}': {http_e}"
            )
            self.audit_log(
                f"HTTP error: Failed to assign role to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id}): {http_e}"
            )
        except Exception as e:
            logging.error(
                f"Unexpected error when assigning role to '@{member.name}': {e}"
            )
            self.audit_log(
                f"Unexpected error: Failed to assign role to '@{member.name}' in guild '{member.guild.name}' (ID: {member.guild.id}): {e}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
