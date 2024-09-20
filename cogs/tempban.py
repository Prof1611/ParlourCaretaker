import discord
import logging
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import re
from datetime import datetime, timedelta, timezone


class TempBan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ban_file = "bans.json"  # File to store ban details
        self.load_bans()
        self.check_bans.start()  # Start the background task

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    def load_bans(self):  # Load ban data from the file
        if os.path.exists(self.ban_file):
            with open(self.ban_file, 'r') as f:
                self.ban_data = json.load(f)
        else:
            self.ban_data = {}

    def save_bans(self):  # Save the current ban data to the file
        with open(self.ban_file, 'w') as f:
            json.dump(self.ban_data, f)

    def parse_duration(self, duration_str: str) -> int:
        # Pattern to match duration strings like '100s', '5m', '3h', '2d'
        pattern = r"(\d+)([smhd])"
        match = re.match(pattern, duration_str)

        if not match:
            raise ValueError(
                """Please specify the duration in either seconds(s), minutes(m), hours(h) or days(d)!

                **Examples:**
                    '100s', '5m', '3h', '2d'.""")

        try:
            # Extract the numeric part and the unit
            amount = int(match.group(1))
            unit = match.group(2)

            # Ensure the amount is positive
            if amount <= 0:
                raise ValueError(
                    "The duration can't be a negative number!")

            # Convert to seconds based on the unit
            if unit == 's':
                return amount
            elif unit == 'm':
                return amount * 60
            elif unit == 'h':
                return amount * 3600
            elif unit == 'd':
                return amount * 86400
            else:
                raise ValueError(
                    """Please specify the duration in either seconds(s), minutes(m), hours(h) or days(d)!

                **Examples:**
                    '100s', '5m', '3h', '2d'.""")
        except (ValueError, OverflowError) as e:
            raise ValueError(
                f"Error parsing duration '{duration_str}': {str(e)}")

    @app_commands.command(name="tempban", description="Temporarily bans a member and sends them a notice via DM.")
    async def tempban(self, interaction: discord.Interaction, member: discord.Member, duration: str, *, reason: str):
        # Check if the author has ban permissions
        if not interaction.user.guild_permissions.ban_members:
            embed = discord.Embed(
                title="Error", description=f"You don't have permission to ban members!", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Parse the duration string to seconds
        try:
            duration_seconds = self.parse_duration(duration)
        except ValueError as e:
            embed = discord.Embed(
                title="Invalid duration", description=str(e), color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Calculate unban time
        unban_time = (datetime.now(timezone.utc) +
                      timedelta(seconds=duration_seconds)).isoformat()

        # Try to send a DM to the member before banning
        try:
            await member.send(f"""**NOTICE: Temporary Ban from The Parlour Discord Server**

Dear {member.mention},

We are writing to inform you that you have been temporarily banned from The Parlour Discord server for {duration}.

**Reason for Temporary Ban:** {reason}

We take upholding the standards of our community very seriously, and continued disruptive or disrespectful behaviour will not be tolerated.

Upon the expiration of your ban, you are welcome to re-join the server. We encourage you to take this time to reflect on your behaviour and consider how you can contribute positively to our community moving forward.

**Appeal Process:** If you wish to appeal this ban, you may do so by filling out the following form: https://forms.gle/Sn73Tvn7VJP2eiTD6

Sincerely,
The Parlour Moderation Team
*Please do not reply to this message as the staff team will not see it.*
""")
            logging.info(
                f"Successfully sent temporary ban notice to '{member.name}' via DM.")
        except discord.HTTPException as e:
            if e.status == 403:  # DMs Disabled
                logging.error(
                    f"DMs disabled when attempting to send temporary ban notice via DM. Error: {e}")
                embed = discord.Embed(
                    title="Error", description=f"That user has their DMs disabled. Failed to send notice.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)
            else:
                logging.error(
                    f"Error when attempting to send temporary ban notice via DM: {e}")
                embed = discord.Embed(
                    title="Error", description=f"Failed to send notice to {member.mention} via DM.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed)

        # Ban the member
        await interaction.guild.ban(member, reason=reason, delete_message_days=0)
        logging.info(
            f"Temporarily banned '{member.name}' from '{interaction.guild.name}' for '{duration}'.")

        embed = discord.Embed(
            title="Member Banned", description=f"Temporarily banned {member.mention} from the server for {duration} and sent them a notice via DM.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)

        # Store ban details
        self.ban_data[str(member.id)] = {
            "username": member.name,
            "guild_id": interaction.guild.id,
            "unban_time": unban_time
        }
        self.save_bans()

    @tasks.loop(seconds=15)  # Run this every 15 seconds
    async def check_bans(self):  # Check if any bans need to be lifted
        now = datetime.now(timezone.utc)  # Get the current time in UTC
        to_unban = []

        for user_id, ban_info in self.ban_data.items():
            unban_time = datetime.fromisoformat(ban_info["unban_time"])
            if now >= unban_time:
                to_unban.append((user_id, ban_info["guild_id"]))

        for user_id, guild_id in to_unban:
            guild = self.bot.get_guild(guild_id)
            if guild:
                member = discord.Object(id=user_id)
                try:
                    await guild.unban(member)
                    logging.info(
                        f"Successfully unbanned user id: {user_id} from guild id: {guild_id}.")
                except discord.NotFound:
                    logging.warning(
                        f"Failed to unban user id: {user_id}, user not found in guild id: {guild_id}.")
            # Remove the unban entry from the data
            del self.ban_data[user_id]

        # Save the updated ban data
        self.save_bans()

    @check_bans.before_loop
    # Wait until the bot is ready before starting the check
    async def before_check_bans(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(TempBan(bot))
