import discord
import logging
import yaml
from discord.ext import commands


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

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mAutoRole\033[0m cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        # Check if autorole feature is enabled.
        if not self.autorole_enabled:
            logging.info(
                "Autorole is disabled in the configuration. Skipping role assignment."
            )
            return

        role_id = self.newjoin_role_id
        try:
            role = member.guild.get_role(role_id)
            if not role:
                logging.error(
                    f"Role with ID {role_id} not found in guild '{member.guild.name}'."
                )
                return
        except Exception as e:
            logging.error(
                f"Error retrieving role with ID {role_id} in guild '{member.guild.name}': {e}"
            )
            return

        try:
            await member.add_roles(role, reason="Auto-assigned role on join")
            logging.info(f"Assigned role '{role.name}' to new member '{member.name}'.")
        except discord.Forbidden:
            logging.error(
                f"Forbidden error when assigning role to '{member.name}'. Check that the bot has Manage Roles permission and its role is high enough."
            )
        except discord.HTTPException as http_e:
            logging.error(
                f"HTTP error occurred while assigning role to '{member.name}': {http_e}"
            )
        except Exception as e:
            logging.error(
                f"Unexpected error when assigning role to '{member.name}': {e}"
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
