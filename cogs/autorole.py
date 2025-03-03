import discord
import logging
from discord.ext import commands

class AutoRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35mAutoRole\033[0m cog synced successfully.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        role_id = 1151863422133227594  # Role ID to assign to new joiners
        role = member.guild.get_role(role_id)
        if not role:
            logging.error(f"AutoRole: Role with ID {role_id} not found in guild '{member.guild.name}'.")
            return
        try:
            await member.add_roles(role)
            logging.info(f"AutoRole: Assigned role '{role.name}' to new member '{member.name}'.")
        except discord.HTTPException as e:
            logging.error(f"AutoRole: Failed to assign role to '{member.name}'. Error: {e}")

async def setup(bot):
    await bot.add_cog(AutoRole(bot))
