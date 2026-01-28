import os
import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

@client.event
async def on_ready():
    with open('roles_dump.txt', 'w', encoding='utf-8') as f:
        f.write(f'Logged in as {client.user}\n')
        for guild in client.guilds:
            f.write(f'\nGuild: {guild.name} (ID: {guild.id})\n')
            f.write('--- Roles ---\n')
            for role in guild.roles:
                f.write(f' - {role.name}: {role.id}\n')
            f.write('\n--- Emojis ---\n')
            for emoji in guild.emojis:
                f.write(f' - {emoji.name}: {emoji.id}\n')
    await client.close()

client.run(TOKEN)
