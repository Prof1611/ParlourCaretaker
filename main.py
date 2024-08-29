import discord
from discord.ext import commands

bot = commands.Bot(command_prefix=">", intents=discord.Intents.all())

@bot.event
async def on_ready():
    print (f"Logged in as \033[35m{bot.user}\033[0m")

with open("token.txt") as file:
    token = file.read()

bot.run(token)