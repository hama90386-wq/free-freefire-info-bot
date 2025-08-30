# cogs/infoCommands.py
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

# Optional import for image composition; fallback available
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

CONFIG_FILE = "info_channels.json"

class InfoCommands(commands.Cog):
    def __init__(self, bot: commands.Bot, session: aiohttp.ClientSession):
        self.bot = bot
        self.session = session  # passed from main bot
        self.api_url = "http://raw.thug4ff.com/info"
        self.profile_url = "https://genprofile-24nr.onrender.com/api/profile"
        self.profile_card_url = "https://genprofile-24nr.onrender.com/api/profile_card"
        self.config_data = self.load_config()
        self.cooldowns = {}

    def convert_unix_timestamp(self, timestamp) -> str:
        try:
            ts = int(timestamp)
            return datetime.utcfromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')
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
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    loaded.setdefault("global_settings", {})
                    loaded["global_settings"].setdefault("default_all_channels", False)
                    loaded["global_settings"].setdefault("default_cooldown", 30)
                    loaded["global_settings"].setdefault("default_daily_limit", 30)
                    loaded.setdefault("servers", {})
                    return loaded
            except Exception:
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
            allowed = self.config_data["servers"].get(guild_id, {}).get("info_channels", [])
            if not allowed:
                return True
            return str(ctx.channel.id) in allowed
        except Exception:
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
            channels = []
            for ch_id in self.config_data["servers"][guild_id]["info_channels"]:
                ch_obj = ctx.guild.get_channel(int(ch_id))
                channels.append(f"• {ch_obj.mention if ch_obj else f'ID: {ch_id}'}")
            embed = discord.Embed(title="Allowed channels for !info", description="\n".join(channels), color=discord.Color.blue())
            cooldown = self.config_data["servers"][guild_id].get("config", {}).get("cooldown", self.config_data["global_settings"]["default_cooldown"])
            embed.set_footer(text=f"Current cooldown: {cooldown} seconds")
        else:
            embed = discord.Embed(title="Allowed channels for !info", description="All channels are allowed (no restriction configured)", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="info", description="Displays information about a Free Fire player")
    @app_commands.describe(uid="FREE FIRE INFO")
    async def player_info(self, ctx: commands.Context, uid: str):
        guild_id = str(ctx.guild.id)

        if not uid.isdigit() or len(uid) < 6:
            return await ctx.reply("Invalid UID! It must be numbers only and at least 6 digits.", mention_author=False)

        if not await self.is_channel_allowed(ctx):
            return await ctx.send("This command is not allowed in this channel.", ephemeral=True)

        cooldown = self.config_data["global_settings"].get("default_cooldown", 30)
        if guild_id in self.config_data["servers"]:
            cooldown = self.config_data["servers"][guild_id].get("config", {}).get("cooldown", cooldown)

        if ctx.author.id in self.cooldowns:
            last_used = self.cooldowns[ctx.author.id]
            elapsed = (datetime.now() - last_used).total_seconds()
            if elapsed < cooldown:
                return await ctx.send(f"Please wait {int(cooldown - elapsed)}s before using this command again", ephemeral=True)

        self.cooldowns[ctx.author.id] = datetime.now()

        try:
            async with ctx.typing():
                async with self.session.get(f"{self.api_url}?uid={uid}") as resp:
                    if resp.status == 404:
                        return await ctx.send(f"Player with UID `{uid}` not found.")
                    if resp.status != 200:
                        return await ctx.send("API error. Try again later.")
                    data = await resp.json()

            basic_info = data.get('basicInfo', {}) or {}
            captain_info = data.get('captainBasicInfo', {}) or {}
            clan_info = data.get('clanBasicInfo', {}) or {}
            credit_score_info = data.get('creditScoreInfo', {}) or {}
            pet_info = data.get('petInfo', {}) or {}
            profile_info = data.get('profileInfo', {}) or {}
            social_info = data.get('socialInfo', {}) or {}

            # Build embed text fields
            created_at = self.convert_unix_timestamp(basic_info.get('createAt', 'Not found'))
            last_login = self.convert_unix_timestamp(basic_info.get('lastLoginAt', 'Not found'))

            embed = discord.Embed(title="Player Information", color=discord.Color.blurple(), timestamp=datetime.now())

            # Basic block
            basic_block = "\n".join([
                "**┌  ACCOUNT BASIC INFO**",
                f"**├─ Name**: {basic_info.get('nickname', 'Not found')}",
                f"**├─ UID**: `{uid}`",
                f"**├─ Level**: {basic_info.get('level', 'Not found')} (Exp: {basic_info.get('exp', '?')})",
                f"**├─ Region**: {basic_info.get('region', 'Not found')}",
                f"**├─ Likes**: {basic_info.get('liked', 'Not found')}",
                f"**├─ Honor Score**: {credit_score_info.get('creditScore', 'Not found')}",
                f"**└─ Signature**: {social_info.get('signature', 'None') or 'None'}"
            ])
            embed.add_field(name="\u200b", value=basic_block, inline=False)

            # Activity block
            br_rank = basic_info.get('rankingPoints', '?')
            cs_rank = basic_info.get('csRankingPoints', '?')
            activity_block = "\n".join([
                "**┌  ACCOUNT ACTIVITY**",
                f"**├─ Most Recent OB**: {basic_info.get('releaseVersion', '?')}",
                f"**├─ Current BP Badges**: {basic_info.get('badgeCnt', 'Not found')}",
                f"**├─ BR Rank**: {br_rank}",
                f"**├─ CS Rank**: {cs_rank}",
                f"**├─ Created At**: {created_at}",
                f"**└─ Last Login**: {last_login}"
            ])
            embed.add_field(name="\u200b", value=activity_block, inline=False)

            # Overview block
            overview_block = "\n".join([
                "**┌  ACCOUNT OVERVIEW**",
                f"**├─ Avatar ID**: {profile_info.get('avatarId', 'Not found')}",
                f"**├─ Banner ID**: {basic_info.get('bannerId', 'Not found')}",
                f"**├─ Pin ID**: {captain_info.get('pinId', 'Not found') if captain_info else 'Default'}",
                f"**└─ Equipped Skills**: {profile_info.get('equipedSkills', 'Not found')}"
            ])
            embed.add_field(name="\u200b", value=overview_block, inline=False)

            # Pet block
            pet_block = "\n".join([
                "**┌  PET DETAILS**",
                f"**├─ Equipped?**: {'Yes' if pet_info.get('isSelected') else 'Not Found'}",
                f"**├─ Pet Name**: {pet_info.get('name', 'Not Found')}",
                f"**├─ Pet Exp**: {pet_info.get('exp', 'Not Found')}",
                f"**└─ Pet Level**: {pet_info.get('level', 'Not Found')}"
            ])
            embed.add_field(name="\u200b", value=pet_block, inline=False)

            # Guild block formatted like your sample
            if clan_info:
                guild_lines = [
                    "**┌  GUILD INFO**",
                    f"**├─ Guild Name**: {clan_info.get('clanName', 'Not found')}",
                    f"**├─ Guild ID**: {clan_info.get('clanId', 'Not found')}",
                    f"**├─ Guild Level**: {clan_info.get('clanLevel', 'Not found')}",
                    f"**├─ Live Members**: {clan_info.get('memberNum', 'Not found')}/{clan_info.get('capacity', '?')}",
                    f"**└─ Leader Info:**"
                ]
                if captain_info:
                    guild_lines.extend([
                        f"    **├─ Leader Name**: {captain_info.get('nickname', 'Not found')}",
                        f"    **├─ Leader UID**: {captain_info.get('accountId', 'Not found')}",
                        f"    **├─ Leader Level**: {captain_info.get('level', 'Not found')} (Exp: {captain_info.get('exp', '?')})",
                        f"    **├─ Last Login**: {self.convert_unix_timestamp(captain_info.get('lastLoginAt', 'Not found'))}",
                        f"    **├─ Title**: {captain_info.get('title', 'Not found')}",
                        f"    **├─ BP Badges**: {captain_info.get('badgeCnt', '?')}",
                        f"    **├─ BR Rank**: {captain_info.get('rankingPoints', 'Not found')}",
                        f"    **└─ CS Rank**: {captain_info.get('csRankingPoints', 'Not found')}"
                    ])
                embed.add_field(name="\u200b", value="\n".join(guild_lines), inline=False)

            # Now: prepare the profile-card image to appear inside the embed.
            # We'll try to download profile_card_url and, if Pillow is available, compose a small canvas
            # and attach it so the embed shows it as an attachment image (attachment://...).
            profile_card_buf = None
            try:
                card_url = f"{self.profile_card_url}?uid={uid}"
                async with self.session.get(card_url) as card_resp:
                    if card_resp.status == 200:
                        card_bytes = await card_resp.read()
                        if PIL_AVAILABLE:
                            # compose a canvas with the card pasted at bottom-left (small margin)
                            try:
                                card_img = Image.open(io.BytesIO(card_bytes)).convert("RGBA")
                                # determine sizes
                                canvas_w = max(card_img.width + 40, 600)
                                canvas_h = card_img.height + 40
                                canvas = Image.new("RGBA", (canvas_w, canvas_h), (0,0,0,0))
                                # paste card at (20, 20)
                                card_resized = card_img
                                # optionally resize card if too wide
                                max_card_w = 340
                                if card_resized.width > max_card_w:
                                    ratio = max_card_w / card_resized.width
                                    new_h = int(card_resized.height * ratio)
                                    card_resized = card_resized.resize((max_card_w, new_h), Image.LANCZOS)
                                    canvas_h = max(canvas_h, new_h + 40)
                                    canvas = Image.new("RGBA", (max(canvas_w, max_card_w + 40), canvas_h), (0,0,0,0))
                                canvas.paste(card_resized, (20, canvas_h - card_resized.height - 20), card_resized)
                                out_buf = io.BytesIO()
                                canvas.save(out_buf, format="PNG")
                                out_buf.seek(0)
                                profile_card_buf = out_buf
                            except Exception as e_img:
                                # fallback: use raw card bytes
                                profile_card_buf = io.BytesIO(card_bytes)
                        else:
                            profile_card_buf = io.BytesIO(card_bytes)
                    else:
                        profile_card_buf = None
            except Exception as e:
                profile_card_buf = None
                print("Profile card fetch error:", e)

            # If we have a buffer, attach it and reference as attachment in embed
            if profile_card_buf:
                filename = f"profile_card_{uuid.uuid4().hex[:8]}.png"
                file = discord.File(profile_card_buf, filename=filename)
                # set image url to attachment
                embed.set_image(url=f"attachment://{filename}")
                await ctx.send(file=file, embed=embed)
            else:
                # fallback: direct url (may show full-width card)
                embed.set_image(url=f"{self.profile_card_url}?uid={uid}")
                await ctx.send(embed=embed)

            # Finally, send outfit image as separate file (if you still want it)
            try:
                outfit_url = f"{self.profile_url}?uid={uid}"
                async with self.session.get(outfit_url) as outfit_resp:
                    if outfit_resp.status == 200:
                        outfit_bytes = await outfit_resp.read()
                        outfit_buf = io.BytesIO(outfit_bytes)
                        await ctx.send(file=discord.File(outfit_buf, filename=f"outfit_{uuid.uuid4().hex[:8]}.png"))
            except Exception as e:
                print("Outfit fetch error:", e)

        except Exception as e:
            await ctx.send(f"Unexpected error: `{e}`")
        finally:
            gc.collect()

    async def cog_unload(self):
        # session owned by bot; do not close here
        pass

async def setup(bot: commands.Bot):
    await bot.add_cog(InfoCommands(bot, bot.session))
