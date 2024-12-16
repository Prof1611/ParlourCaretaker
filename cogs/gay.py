import discord
import logging
from discord import app_commands
from discord.ext import commands
import random


class Gay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        logging.info(f"\033[35m{__name__}\033[0m synced successfully.")

    @app_commands.command(
        name="gay",
        description="Selects a random message containing the word 'gay' from any user in any channel."
    )
    async def randomgaymessage(self, interaction: discord.Interaction):
        # Defer the response to avoid timeout errors
        await interaction.response.defer()

        try:
            messages = []
            
            # Search through all text channels in the guild
            for channel in interaction.guild.text_channels:
                async for message in channel.history(limit=3000):
                    # Check if the message contains 'gay' and has content
                    if 'gay' in message.content.lower() and message.content.strip():
                        messages.append(message)

            # Check if any valid messages were found
            if not messages:
                embed = discord.Embed(
                    title="No Messages Found",
                    description="No messages containing the word 'gay' were found in any channel.",
                    colour=discord.Colour.red(),
                )
                await interaction.followup.send(embed=embed)
                return

            # Choose a random message
            random_message = random.choice(messages)

            # Create an embed for the random message
            embed = discord.Embed(
                title="Random Message Containing 'Gay'",
                description=random_message.content,
                colour=discord.Colour.blue(),
                timestamp=random_message.created_at,
            )
            embed.set_footer(
                text=f"Message ID: {random_message.id} • Channel: #{random_message.channel.name}"
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
    await bot.add_cog(Gay(bot))
