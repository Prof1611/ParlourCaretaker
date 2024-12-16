import discord
import logging
from discord import app_commands
from discord.ext import commands
import random


class Harry(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(
        name="harry",
        description="Selects a random message from Harry in the current channel.",
    )
    async def harry(self, interaction: discord.Interaction):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        # Define Harry's user ID
        harry_id = 398205938265358339

        try:
            # Fetch the last 1000 messages from the current channel
            messages = []
            async for message in interaction.channel.history(limit=1000):
                # Only include messages with text content
                if message.author.id == harry_id and message.content.strip():
                    messages.append(message)

            # Check if any valid messages were found
            if not messages:
                embed = discord.Embed(
                    title="No Messages Found",
                    description="No messages with text content from Harry were found in this channel.",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            # Choose a random message
            random_message = random.choice(messages)

            # Create an embed for the random message
            embed = discord.Embed(
                title="Random Message by Harry",
                description=random_message.content,
                colour=discord.Colour.blue(),
                timestamp=random_message.created_at,
            )
            embed.set_footer(
                text=f"Message ID: {random_message.id} • Channel: #{interaction.channel.name}"
            )
            embed.set_author(
                name=random_message.author.display_name,
                icon_url=random_message.author.avatar.url
                if random_message.author.avatar
                else None,
            )
            embed.add_field(
                name="Jump to Message",
                value=f"[Click here]({random_message.jump_url})",
                inline=False,
            )

            # Send the embed
            await interaction.followup.send(embed=embed)

        except discord.Forbidden:
            # Handle missing permissions
            embed = discord.Embed(
                title="Error: Missing Permissions",
                description="The bot lacks permissions to read message history or send messages in this channel.",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)

        except discord.HTTPException as http_exc:
            # Handle other HTTP exceptions
            logging.error(f"HTTPException: {http_exc}")
            embed = discord.Embed(
                title="Error: HTTP Exception",
                description="An unexpected HTTP error occurred while processing the command. Please try again later.",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)

        except Exception as exc:
            # Handle unexpected errors
            logging.error(f"Unexpected Error: {exc}")
            embed = discord.Embed(
                title="Error: Unexpected Exception",
                description="An unexpected error occurred. The issue has been logged for review.",
                colour=discord.Colour.red(),
            )
            await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Harry(bot))
