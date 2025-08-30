import discord
from discord.ext import commands, tasks
import os
import traceback
from flask import Flask
import aiohttp
import asyncio
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("Missing TOKEN in environment")

app = Flask(__name__)
bot_name = "Loading..."

@app.route("/")
def home():
    return f"Bot {bot_name} is operational"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.session = None

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        try:
            await self.load_extension("cogs.infoCommands")
        except Exception as e:
            print(f"Failed to load cog: {e}")
            traceback.print_exc()
        await self.tree.sync()
        self.update_status.start()

    async def on_ready(self):
        global bot_name
        bot_name = str(self.user)
        print(f"Connected as {bot_name}, Serving {len(self.guilds)} servers")
        if os.environ.get("RENDER"):
            import threading
            threading.Thread(target=run_flask, daemon=True).start()
            print("Flask server started")

    @tasks.loop(minutes=5)
    async def update_status(self):
        try:
            activity = discord.Activity(type=discord.ActivityType.watching,
                                        name=f"{len(self.guilds)} servers")
            await self.change_presence(activity=activity)
        except Exception as e:
            print(f"Status update failed: {e}")

    @update_status.before_loop
    async def before_status_update(self):
        await self.wait_until_ready()

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

async def main():
    bot = Bot()
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        await bot.close()
    except Exception as e:
        print(f"Critical error: {e}")
        traceback.print_exc()
        await bot.close()

if __name__ == "__main__":
    if os.environ.get("RENDER"):
        asyncio.run(main())
    else:
        Bot().run(TOKEN)
