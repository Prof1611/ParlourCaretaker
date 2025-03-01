import discord
import logging
import json
import asyncio
from discord import app_commands
from discord.ext import commands


class StickyModal(discord.ui.Modal, title="Set Sticky Message"):
    sticky_input = discord.ui.TextInput(
        label="Sticky Message",
        style=discord.TextStyle.long,
        required=True,
        placeholder="Enter your sticky message here...",
    )

    def __init__(self, bot: commands.Bot, sticky_cog: "Sticky"):
        super().__init__()
        self.bot = bot
        self.sticky_cog = sticky_cog

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel

        # Delete the old sticky message if it exists.
        if channel.id in self.sticky_cog.stickies:
            previous_sticky = self.sticky_cog.stickies[channel.id]
            try:
                old_message = await channel.fetch_message(previous_sticky["message_id"])
                await old_message.delete()
            except discord.NotFound:
                pass

        try:
            # Send the new sticky message using the multi-line input.
            sticky_message = await channel.send(self.sticky_input.value)
            # Update the sticky data in the cog.
            self.sticky_cog.stickies[channel.id] = {
                "content": sticky_message.content,
                "message_id": sticky_message.id,
            }
            self.sticky_cog.save_stickies()

            logging.info(f"Sticky message successfully set in #{channel}")

            embed = discord.Embed(
                title="Sticky Message Set",
                description=f"Successfully set sticky message in #{channel}!",
                color=discord.Color.green(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException as e:
            await self.sticky_cog.handle_error(e, channel, interaction)


class Sticky(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Dictionary to store sticky details per channel:
        # key: channel id, value: {"content": str, "message_id": int}
        self.stickies = {}
        self.load_stickies()

    def load_stickies(self):
        """Load sticky messages from a JSON file."""
        try:
            with open("stickies.json", "r") as f:
                self.stickies = json.load(f)
                if not self.stickies:
                    self.stickies = {}
                    self.save_stickies()
        except (FileNotFoundError, json.JSONDecodeError):
            self.stickies = {}
            self.save_stickies()

    def save_stickies(self):
        """Save the current sticky messages to a JSON file."""
        with open("stickies.json", "w") as f:
            saved_stickies = {
                str(channel_id): {
                    "content": data["content"],
                    "message_id": data["message_id"],
                }
                for channel_id, data in self.stickies.items()
            }
            json.dump(saved_stickies, f, indent=4)

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")
        # On startup, for each channel with a sticky, delete the old sticky and repost it.
        for channel_id, sticky in list(self.stickies.items()):
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                try:
                    old_message = await channel.fetch_message(sticky["message_id"])
                    await old_message.delete()
                except discord.NotFound:
                    pass
                new_sticky = await channel.send(sticky["content"])
                self.stickies[channel.id] = {
                    "content": sticky["content"],
                    "message_id": new_sticky.id,
                }
        self.save_stickies()

    @app_commands.command(
        name="setsticky",
        description="Set a sticky message in the current channel.",
    )
    async def set_sticky(self, interaction: discord.Interaction):
        """Open a modal to set the sticky message for the current channel."""
        modal = StickyModal(self.bot, self)
        await interaction.response.send_modal(modal)

    @app_commands.command(
        name="removesticky",
        description="Remove the sticky message from the current channel.",
    )
    async def remove_sticky(self, interaction: discord.Interaction):
        """Remove the sticky message for the current channel."""
        await interaction.response.defer()
        channel = interaction.channel

        if channel.id not in self.stickies:
            embed = discord.Embed(
                title="No Sticky Message",
                description=f"There is no sticky message set in #{channel}.",
                color=discord.Color.red(),
            )
            confirmation = await interaction.followup.send(embed=embed)
            await asyncio.sleep(3)
            await confirmation.delete()
            return

        sticky = self.stickies[channel.id]
        try:
            old_message = await channel.fetch_message(sticky["message_id"])
            await old_message.delete()
        except discord.NotFound:
            pass

        del self.stickies[channel.id]
        self.save_stickies()

        embed = discord.Embed(
            title="Sticky Removed",
            description=f"Sticky message successfully removed from #{channel}.",
            color=discord.Color.green(),
        )
        confirmation = await interaction.followup.send(embed=embed)
        await asyncio.sleep(3)
        await confirmation.delete()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Ensure the sticky message stays as the latest message in the channel."""
        if message.author == self.bot.user:
            return

        channel = message.channel
        if channel.id in self.stickies:
            sticky = self.stickies[channel.id]
            # Retrieve the latest message in the channel
            history = [msg async for msg in channel.history(limit=1)]
            if history:
                last_message = history[0]
                # If the last message is already the sticky, do nothing.
                if (
                    last_message.author == self.bot.user
                    and last_message.content == sticky["content"]
                ):
                    return

            # Delete the old sticky message if it exists.
            try:
                old_message = await channel.fetch_message(sticky["message_id"])
                await old_message.delete()
            except discord.NotFound:
                pass

            # Repost the sticky message so it becomes the latest.
            new_sticky = await channel.send(sticky["content"])
            self.stickies[channel.id] = {
                "content": sticky["content"],
                "message_id": new_sticky.id,
            }
            self.save_stickies()

    async def handle_error(self, e, channel, interaction):
        """Handle error cases and send an appropriate response."""
        if e.status == 403:
            logging.error(f"No access to #{channel}. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"I don't have access to #{channel}!",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status == 404:
            logging.error(f"Channel not found. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Channel not found!",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status == 429:
            logging.error(f"RATE LIMIT. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description="Too many requests! Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        elif e.status in {500, 502, 503, 504}:
            logging.error(f"Discord API Error. Error: {e}")
            embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel}. Please try later.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
        else:
            logging.error(
                f"Error when attempting to set sticky message in #{channel}. Error: {e}"
            )
            embed = discord.Embed(
                title="Error",
                description=f"Failed to set sticky message in #{channel}.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Sticky(bot))
