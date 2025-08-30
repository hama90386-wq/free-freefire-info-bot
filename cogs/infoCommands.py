import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
from datetime import datetime
import json
import io
import uuid
import gc
import os

CONFIG_FILE = "info_channels.json"

class InfoCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, session: aiohttp.ClientSession):
        self.bot = bot
        self.session = session  # استخدام نفس session من البوت
        self.api_url = "http://raw.thug4ff.com/info"
        self.profile_url = "https://genprofile-24nr.onrender.com/api/profile"
        self.profile_card_url = "https://genprofile-24nr.onrender.com/api/profile_card"
        self.config_data = self.load_config()
        self.cooldowns = {}

    def convert_unix_timestamp(self, timestamp: int) -> str:
        try:
            return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            return "Not found"

    def load_config(self):
        default_config = {
            "servers": {},
            "global_settings": {
                "default_all_channels": False,
                "default_cooldown": 30,
                "default_daily_limit": 30
            }
        }
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    loaded_config = json.load(f)
                    loaded_config.setdefault("global_settings", {})
                    loaded_config["global_settings"].setdefault("default_all_channels", False)
                    loaded_config["global_settings"].setdefault("default_cooldown", 30)
                    loaded_config["global_settings"].setdefault("default_daily_limit", 30)
                    loaded_config.setdefault("servers", {})
                    return loaded_config
            except:
                return default_config
        return default_config

    def save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    async def is_channel_allowed(self, ctx):
        try:
            guild_id = str(ctx.guild.id)
            allowed_channels = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            if not allowed_channels:
                return True
            return str(ctx.channel.id) in allowed_channels
        except:
            return False

    @commands.hybrid_command(name="setinfochannel", description="Allow a channel for !info commands")
    @commands.has_permissions(administrator=True)
    async def set_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        self.config_data["servers"].setdefault(guild_id, {"info_channels": [], "config": {}})
        if str(channel.id) not in self.config_data["servers"][guild_id]["info_channels"]:
            self.config_data["servers"][guild_id]["info_channels"].append(str(channel.id))
            self.save_config()
            await ctx.send(f"✅ {channel.mention} is now allowed for `!info` commands")
        else:
            await ctx.send(f"ℹ️ {channel.mention} is already allowed for `!info` commands")

    @commands.hybrid_command(name="removeinfochannel", description="Remove a channel from !info commands")
    @commands.has_permissions(administrator=True)
    async def remove_info_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"]:
            if str(channel.id) in self.config_data["servers"][guild_id]["info_channels"]:
                self.config_data["servers"][guild_id]["info_channels"].remove(str(channel.id))
                self.save_config()
                await ctx.send(f"✅ {channel.mention} has been removed from allowed channels")
            else:
                await ctx.send(f"❌ {channel.mention} is not in the list of allowed channels")
        else:
            await ctx.send("ℹ️ This server has no saved configuration")

    @commands.hybrid_command(name="infochannels", description="List allowed channels")
    async def list_info_channels(self, ctx: commands.Context):
        guild_id = str(ctx.guild.id)
        if guild_id in self.config_data["servers"] and self.config_data["servers"][guild_id]["info_channels"]:
            channels = [f"• {ctx.guild.get_channel(int(cid)).mention if ctx.guild.get_channel(int(cid)) else f'ID: {cid}'}"
                        for cid in self.config_data["servers"][guild_id]["info_channels"]]
            embed = discord.Embed(title="Allowed channels for !info", description="\n".join(channels),
                                  color=discord.Color.blue())
        else:
            embed = discord.Embed(title="Allowed channels for !info",
                                  description="All channels are allowed (no restriction configured)",
                                  color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Displays information about a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("Invalid UID! It must be numbers and at least 6 digits", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send("This command is not allowed in this channel.", ephemeral=True)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            cooldown = self.config_data["global_settings"].get("default_cooldown", 30)
            if (datetime.now() - last_used).seconds < cooldown:
                remaining = cooldown - (datetime.now() - last_used).seconds
                return await ctx.send(f"Please wait {remaining}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as response:
                    if response.status != 200:
                        return await ctx.send("API error. Try again later.")
                    data = await response.json()

            basic_info = data.get("basicInfo", {})
            embed = discord.Embed(title="Player Information", color=discord.Color.blurple(),
                                  timestamp=datetime.now())
            embed.add_field(name="Name", value=basic_info.get("nickname", "Not found"))
            embed.add_field(name="UID", value=f"`{uid}`")
            await ctx.send(embed=embed)

            # Outfit image
            outfit_url = f"{self.profile_url}?uid={uid}"
            async with self.session.get(outfit_url) as img_file:
                if img_file.status == 200:
                    with io.BytesIO(await img_file.read()) as buf:
                        await ctx.send(file=discord.File(buf, filename=f"profile_{uuid.uuid4().hex[:8]}.png"))

            # Profile card image
            card_url = f"{self.profile_card_url}?uid={uid}"
            async with self.session.get(card_url) as img_file:
                if img_file.status == 200:
                    with io.BytesIO(await img_file.read()) as buf:
                        await ctx.send(file=discord.File(buf, filename=f"profile_card_{uuid.uuid4().hex[:8]}.png"))

        except Exception as e:
            await ctx.send(f"Unexpected error: `{e}`")
        finally:
            gc.collect()


async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCommands(bot, bot.session))
