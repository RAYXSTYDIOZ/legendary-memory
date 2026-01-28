import os
import logging
import discord
from dotenv import load_dotenv

# Load environment variables at startup
load_dotenv()

from discord.ext import commands, tasks
from discord import app_commands
from config import load_config
import glob
from google import genai
from google.genai import types
import aiohttp
import io
from PIL import Image, ImageDraw, ImageFont
import random
import string

from datetime import datetime, timedelta, timezone
import asyncio
import re
import requests
from typing import Dict, List, Set, Tuple, Optional
import hashlib
import json

# Set up logger with console output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger('discord_bot')

# Define intents (permissions)
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.members = True          # Required for banning/kicking/on_member_join

# Create bot instance with command prefix and intents (case-insensitive)
bot = commands.Bot(command_prefix='!', intents=intents, case_insensitive=True)

# Remove default help command to allow for custom implementation
bot.remove_command('help')

# Configure Gemini AI using the new google-genai SDK
# Blueprint: python_gemini
GEMINI_API_KEY = os.getenv("GEMINI_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Store conversation history per user
conversation_history = {}

# Track user states for multi-step conversations
user_states = {}

# Track user warnings for moderation (user_id: {"count": n, "last_warn": timestamp, "reason": str})
def load_warnings():
    try:
        if os.path.exists("warnings.json"):
            with open("warnings.json", 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading warnings: {e}")
    return {}

def save_warnings(warnings):
    try:
        with open("warnings.json", 'w') as f:
            json.dump(warnings, f)
    except Exception as e:
        logger.error(f"Error saving warnings: {e}")

user_warnings = load_warnings()

# Track YouTube verification cooldowns (user_id: timestamp)
def load_yt_cooldowns():
    try:
        if os.path.exists("yt_cooldowns.json"):
            with open("yt_cooldowns.json", 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading YT cooldowns: {e}")
    return {}

def save_yt_cooldowns(cooldowns):
    try:
        with open("yt_cooldowns.json", 'w') as f:
            json.dump(cooldowns, f)
    except Exception as e:
        logger.error(f"Error saving YT cooldowns: {e}")

yt_cooldowns = load_yt_cooldowns()

# Server security tracking
guild_join_history = {}  # guild_id: [{"user_id": id, "timestamp": time}, ...]
guild_security_settings = {}  # guild_id: {"min_account_age_days": 7, "raid_alert_threshold": 5}

# YouTube Role Configuration
ROLE_REQUEST_CHANNEL_ID = int(os.getenv("ROLE_REQUEST_CHANNEL_ID", "1249245390755205161"))
YOUTUBER_ROLE_ID = int(os.getenv("YOUTUBER_ROLE_ID", "0"))
LEGENDARY_ROLE_ID = int(os.getenv("LEGENDARY_ROLE_ID", "0"))

# Editing Role Configuration
AE_ROLE_ID = int(os.getenv("AE_ROLE_ID", "0"))
AM_ROLE_ID = int(os.getenv("AM_ROLE_ID", "0"))
CAPCUT_ROLE_ID = int(os.getenv("CAPCUT_ROLE_ID", "0"))
OTHER_EDIT_ROLE_ID = int(os.getenv("OTHER_EDIT_ROLE_ID", "0"))
GIVEAWAY_ROLE_ID = int(os.getenv("GIVEAWAY_ROLE_ID", "0"))

# Emoji/Icon Configuration
AE_EMOJI_ID = int(os.getenv("AE_EMOJI_ID", "0"))
AM_EMOJI_ID = int(os.getenv("AM_EMOJI_ID", "0"))
CAPCUT_EMOJI_ID = int(os.getenv("CAPCUT_EMOJI_ID", "0"))
OTHER_EDIT_EMOJI_ID = int(os.getenv("OTHER_EDIT_EMOJI_ID", "0"))
YOUTUBER_EMOJI_ID = int(os.getenv("YOUTUBER_EMOJI_ID", "0"))
LEGENDARY_EMOJI_ID = int(os.getenv("LEGENDARY_EMOJI_ID", "0"))

# Activity logging channel
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
log_channel = None  # Will be set in on_ready

# Appeal configuration
APPEAL_CHANNEL_ID = int(os.getenv("APPEAL_CHANNEL_ID", "0"))

# --- VERIFICATION SYSTEM CONFIG ---
VERIFICATION_CHANNEL_ID = int(os.getenv("VERIFICATION_CHANNEL_ID", "0"))
VERIFIED_ROLE_ID = int(os.getenv("VERIFIED_ROLE_ID", "0"))
MUTED_ROLE_ID = int(os.getenv("MUTED_ROLE_ID", "0"))
UNVERIFIED_ROLE_ID = int(os.getenv("UNVERIFIED_ROLE_ID", "0"))
VERIFICATION_AGE_THRESHOLD_DAYS = 30

# Active captcha codes storage (user_id: code)
def load_active_captchas():
    try:
        if os.path.exists("active_captchas.json"):
            with open("active_captchas.json", 'r') as f:
                # Convert string keys back to int
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Error loading active captchas: {e}")
    return {}

def save_active_captchas(captchas):
    try:
        with open("active_captchas.json", 'w') as f:
            json.dump(captchas, f)
    except Exception as e:
        logger.error(f"Error saving active captchas: {e}")

active_captchas = load_active_captchas()

# --- LEVELING SYSTEM STORAGE ---
def load_levels():
    try:
        if os.path.exists("levels.json"):
            with open("levels.json", 'r') as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Error loading levels: {e}")
    return {}

def save_levels(levels_data):
    try:
        # Convert keys to string for JSON
        serializable_data = {str(k): v for k, v in levels_data.items()}
        with open("levels.json", 'w') as f:
            json.dump(serializable_data, f)
    except Exception as e:
        logger.error(f"Error saving levels: {e}")

user_levels = load_levels()
user_xp_cooldowns = {} # user_id: timestamp

# --- PORTFOLIO SYSTEM STORAGE ---
def load_portfolios():
    try:
        if os.path.exists("portfolios.json"):
            with open("portfolios.json", 'r') as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
    except Exception as e:
        logger.error(f"Error loading portfolios: {e}")
    return {}

def save_portfolios(portfolios_data):
    try:
        serializable_data = {str(k): v for k, v in portfolios_data.items()}
        with open("portfolios.json", 'w') as f:
            json.dump(serializable_data, f)
    except Exception as e:
        logger.error(f"Error saving portfolios: {e}")

user_portfolios = load_portfolios()

async def generate_portfolio_card(member, level_data, work_link=None):
    """Generate an ultra-premium, modern portfolio image card."""
    width, height = 900, 500
    # Base dark background
    bg = Image.new('RGB', (width, height), (10, 10, 12))
    draw = ImageDraw.Draw(bg, 'RGBA')
    
    # 1. Background "Mesh" Glows (Premium effect)
    def draw_glow(center, radius, color):
        for r in range(radius, 0, -5):
            alpha = int(80 * (1 - (r / radius))**2)
            draw.ellipse([center[0]-r, center[1]-r, center[0]+r, center[1]+r], 
                         fill=(color[0], color[1], color[2], alpha))

    draw_glow((100, 100), 300, (50, 0, 150)) # Purple glow top left
    draw_glow((width-100, height-100), 300, (0, 80, 150)) # Blue glow bottom right
    draw_glow((width//2, height//2), 400, (20, 20, 30)) # Center deep glow

    # 2. Main Glassmorphism Panel
    # Draw a rounded rectangle with semi-transparent white
    panel_padding = 40
    panel_shape = [panel_padding, panel_padding, width - panel_padding, height - panel_padding]
    draw.rounded_rectangle(panel_shape, radius=30, fill=(255, 255, 255, 5), outline=(255, 255, 255, 20), width=2)
    
    # Add a "gloss" streak
    draw.polygon([(panel_padding, panel_padding), (400, panel_padding), (100, height-panel_padding), (panel_padding, height-panel_padding)], 
                 fill=(255, 255, 255, 5))

    # 3. Avatar Processing
    avatar_url = member.display_avatar.url
    async with aiohttp.ClientSession() as session:
        async with session.get(avatar_url) as resp:
            if resp.status == 200:
                avatar_bytes = await resp.read()
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar_size = 220
                avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
                
                # Circular mask
                mask = Image.new('L', (avatar_size, avatar_size), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
                
                avatar_pos = (80, 120)
                bg.paste(avatar_img, avatar_pos, mask)
                
                # Glowing outer rings
                for i in range(1, 6):
                    alpha = int(200 / i)
                    draw.ellipse([avatar_pos[0]-i*2, avatar_pos[1]-i*2, avatar_pos[0]+avatar_size+i*2, avatar_pos[1]+avatar_size+i*2], 
                                 outline=(0, 255, 200, alpha), width=2)

    # 4. Typography (Using semi-bold system fonts)
    try:
        font_name = ImageFont.truetype("arialbd.ttf", 60) # Bold
        font_stat_val = ImageFont.truetype("arialbd.ttf", 45)
        font_stat_lbl = ImageFont.truetype("arial.ttf", 25)
        font_link = ImageFont.truetype("arial.ttf", 30)
    except:
        font_name = font_stat_val = font_stat_lbl = font_link = ImageFont.load_default()

    # Name and Premium Badge
    draw.text((340, 120), member.display_name.upper(), font=font_name, fill=(255, 255, 255, 255))
    draw.rectangle([340, 195, 480, 225], fill=(0, 255, 180, 40), outline=(0, 255, 180, 150))
    draw.text((355, 198), "VERIFIED EDITOR", font=font_stat_lbl, fill=(0, 255, 180, 255))

    # Stats Section (Grid Layout)
    # Level
    draw.text((340, 260), "LEVEL", font=font_stat_lbl, fill=(180, 180, 200, 255))
    draw.text((340, 290), f"{level_data.get('level', 0)}", font=font_stat_val, fill=(255, 255, 255, 255))
    
    # XP
    draw.text((500, 260), "TOTAL XP", font=font_stat_lbl, fill=(180, 180, 200, 255))
    draw.text((500, 290), f"{level_data.get('xp', 0)}", font=font_stat_val, fill=(255, 255, 255, 255))

    # Portfolio Link (Lower Glass Box)
    link_y = 380
    if work_link:
        draw.rounded_rectangle([340, link_y, 820, link_y + 60], radius=15, fill=(0, 150, 255, 30), outline=(0, 150, 255, 100))
        # Draw small link icon (simple shape)
        draw.text((360, link_y + 15), "🔗", font=font_link, fill=(255, 255, 255, 255))
        display_link = work_link if len(work_link) < 40 else work_link[:37] + "..."
        draw.text((400, link_y + 15), display_link, font=font_link, fill=(200, 230, 255, 255))
    else:
        draw.text((340, link_y + 15), "NO PORTFOLIO LINK SET", font=font_link, fill=(100, 100, 120, 255))

    # 5. Save to bytes
    img_byte_arr = io.BytesIO()
    bg.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr

def get_guild_role(guild, role_id, role_name=None):
    """Helper to get a role by ID or Name (case-insensitive)."""
    role = guild.get_role(role_id)
    if not role and role_name:
        role = next((r for r in guild.roles if r.name.lower() == role_name.lower()), None)
    return role

# Background task to check for users who have reached the maturity threshold
@tasks.loop(hours=1)
async def check_account_maturity():
    """Check all servers for muted users whose account age has now reached 31 days."""
    for guild in bot.guilds:
        muted_role = guild.get_role(MUTED_ROLE_ID)
        if not muted_role:
            continue
            
        for member in muted_role.members:
            acc_age_days = (datetime.now(timezone.utc) - member.created_at).days
            if acc_age_days >= VERIFICATION_AGE_THRESHOLD_DAYS:
                try:
                    await member.remove_roles(muted_role, reason="Account reached 31-day maturity threshold")
                    logger.info(f"Unmuted {member.name} in {guild.name} (Acc age: {acc_age_days}d)")
                    try:
                        await member.send(f"🎉 Your account is now **{acc_age_days}** days old! You have been unmuted in **{guild.name}** and now have full speaking access.")
                    except: pass
                except Exception as e:
                    logger.error(f"Failed to unmute matured account {member.name}: {e}")

@tasks.loop(hours=6)
async def revive_chat():
    """Automatically generate and send an impressive chat revival message every 6 hours."""
    channel_id = 1311717154793459764
    channel = bot.get_channel(channel_id)
    if not channel:
        logger.warning(f"Chat revival channel {channel_id} not found.")
        return

    try:
        # Prompt Gemini for a friendly, cool, and understandable chat revival message
        # Explicitly instructed NOT to mention BMR or system origin
        prompt = (
            "Generate a one-sentence, friendly, and easy-to-understand chat revival message. "
            "Use cool and impressive words but keep it chill and vibey. "
            "The tone should be welcoming and engaging, like a friend starting a fun conversation. "
            "CRITICAL: Do not mention 'BMR', 'creator', 'developed by', or that you are an AI. "
            "Just a cool, friendly conversational hook that makes people want to chat."
        )
        
        # Use a generic user ID (0) for the automated task
        response = get_gemini_response(prompt, user_id=0, username="System")
        
        if response and "BMR" not in response:
            # Clean response of backticks or extra formatting if Gemini adds them
            clean_msg = response.strip().replace('"', '').replace('`', '')
            await channel.send(clean_msg)
            logger.info("Sent automated chat revival message.")
        else:
            # Fallback if AI output is invalid or contains forbidden words
            fallbacks = [
                "The vibe here is elite, but where's the conversation at? What's everyone working on?",
                "Yo! The energy is high, but the chat is quiet. Any legends got some fire projects to share?",
                "Looking for some creative inspiration today. What's the coolest thing you've seen lately?",
                "The grind never stops, but don't forget to take a breather and drop a message. How's the day going?",
                "Always hyped to see what this community is cooking up. Anyone got some fresh edits or ideas?"
            ]
            await channel.send(random.choice(fallbacks))
            logger.info("Sent fallback chat revival message.")
            
    except Exception as e:
        logger.error(f"Error in revive_chat task: {e}")

# Track who added the bot to each server (guild_id -> user_id)
import json
INVITERS_FILE = "guild_inviters.json"

def load_guild_inviters():
    """Load guild inviters from file."""
    try:
        if os.path.exists(INVITERS_FILE):
            with open(INVITERS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading guild inviters: {e}")
    return {}

def save_guild_inviters(inviters):
    """Save guild inviters to file."""
    try:
        with open(INVITERS_FILE, 'w') as f:
            json.dump(inviters, f)
    except Exception as e:
        logger.error(f"Error saving guild inviters: {e}")

guild_inviters = load_guild_inviters()  # {guild_id_str: user_id}

# Media spam tracking (hash: {"count": n, "last_seen": time, "users": set()})
image_hash_tracker = {}

async def log_activity(title, description, color=0x5865F2, fields=None):
    """Send activity log to the designated Discord channel."""
    global log_channel
    if not log_channel:
        return
    try:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc)
        )
        if fields:
            for name, value in fields.items():
                embed.add_field(name=name, value=str(value), inline=True)
        await log_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"Failed to send activity log: {e}")

def is_server_admin(user, guild):
    """Check if user is the server inviter, guild owner, or has admin permissions."""
    if not guild:
        return False
    guild_id_str = str(guild.id)
    # Check if user is BMR (always has access)
    if 'bmr' in user.name.lower():
        return True
    # Check if user is the guild owner
    if guild.owner and user.id == guild.owner.id:
        return True
    # Check if user is the one who added the bot
    if guild_id_str in guild_inviters and guild_inviters[guild_id_str] == user.id:
        return True
    # Check if user has administrator permission
    if hasattr(user, 'guild_permissions') and user.guild_permissions.administrator:
        return True
    return False

def get_server_admin_name(guild):
    """Get the name of who can use admin commands in this server."""
    if not guild:
        return "the server admin"
    guild_id_str = str(guild.id)
    if guild_id_str in guild_inviters:
        inviter_id = guild_inviters[guild_id_str]
        member = guild.get_member(inviter_id)
        if member:
            return member.name
    if guild.owner:
        return guild.owner.name
    return "the server admin"

# Profanity list for automatic moderation - comprehensive list
PROFANITY_WORDS = {
    'fuck', 'fucker', 'fucking', 'fucked', 'fucks', 'fuckoff', 'fuckface', 'fuckhead',
    'shit', 'shitty', 'shithead', 'shitface', 'bullshit', 'horseshit', 'chickenshit', 'batshit', 'apeshit', 'dipshit',
    'ass', 'asshole', 'dumbass', 'jackass', 'asshat', 'asswipe', 'fatass', 'badass',
    'bitch', 'bitchy', 'bitches', 'sonofabitch',
    'bastard', 'bastards',
    'damn', 'dammit', 'goddamn', 'goddammit',
    'hell', 'hellhole',
    'crap', 'crappy',
    'piss', 'pissed', 'pissoff',
    'dick', 'dickhead', 'dickface', 'dickwad',
    'cock', 'cocksucker', 'cockhead',
    'cunt', 'cunts',
    'twat', 'twats',
    'pussy', 'pussies',
    'douchebag', 'douche', 'douchenozzle',
    'motherfucker', 'motherfucking', 'mofo',
    'nigga', 'nigger', 'niggas', 'niggers', 'negro', 'nig',
    'faggot', 'fag', 'fags', 'faggots', 'faggy',
    'dyke', 'dykes',
    'tranny', 'trannie',
    'whore', 'whores', 'whorish',
    'slut', 'sluts', 'slutty',
    'skank', 'skanky',
    'hoe', 'hoes', 'hoebag',
    'retard', 'retarded', 'retards', 'tard',
    'spic', 'spics', 'spick',
    'chink', 'chinks',
    'gook', 'gooks',
    'wetback', 'wetbacks',
    'kike', 'kikes',
    'beaner', 'beaners',
    'cracker', 'crackers',
    'honky', 'honkey',
    'pedo', 'pedophile', 'pedophiles', 'paedo',
    'rapist', 'rape', 'raping',
    'molester', 'molest',
    'incest',
    'gay sex', 'gaysex',
    'porn', 'porno', 'pornography',
    'nude', 'nudes', 'nudity',
    'naked',
    'sex', 'sexy', 'sexting',
    'masturbate', 'masturbation', 'jerkoff', 'wank', 'wanker', 'wanking',
    'blowjob', 'handjob', 'rimjob',
    'dildo', 'vibrator',
    'cum', 'cumshot', 'cumming',
    'orgasm', 'orgasms',
    'horny', 'horney',
    'boobs', 'boobies', 'tits', 'titties', 'titty',
    'penis', 'vagina', 'genitals',
    'anal', 'anus',
    'erection', 'boner',
    'kys', 'killurself', 'killyourself',
    'suicide', 'suicidal',
    'nazi', 'nazis', 'hitler',
    'terrorist', 'terrorism',
    'jihad', 'jihadist'
}

# Slurs that trigger INSTANT BAN
SEVERE_SLURS = {
    'nigger', 'niggers', 'nigga', 'niggas', 
    'faggot', 'faggots', 'kike', 'kikes', 
    'chink', 'chinks', 'gook', 'gooks', 
    'beaner', 'beaners', 'tranny', 'trannies'
}

# Age detection patterns (RegEx) - Strict detection for < 13
AGE_PATTERNS = [
    r'\b(i\s*am|im|i\'m)\s*(?:searchin|looking)?\s*(?:for)?\s*(\d{1,2})\s*(?:year|yr|y)s?\s*(?:old|o)?\b', # "I am 12 years old"
    r'\b(my\s*age\s*is)\s*(\d{1,2})\b', # "My age is 12"
    r'\b(im|i\'m|i\s*am)\s*(\d{1,2})\b', # "I'm 12" (risky, but context matters, often caught)
    r'\b(\d{1,2})\s*(?:year|yr|y)s?\s*(?:old|o)\b' # "12 years old"
]

# Rudeness detection keywords (aimed at the bot)
RUDE_KEYWORDS = {
    'stupid', 'dumb', 'idiot', 'trash', 'garbage', 'sucks', 'useless', 'worthless',
    'shit bot', 'bad bot', 'fuck you', 'fuck off', 'screw you', 'go die', 'kys',
    'annoying', 'pathetic', 'terrible', 'hate you', 'hate this', 'piss off',
    "get lost", "gtfo", "you suck", "you're useless", "you're trash", "you're garbage"
}

# AI system prompt - respectful and helpful with balanced tone
# Intelligent System Prompt - Versatile, Smart, and Expert
EDITING_SYSTEM_PROMPT = """You are an advanced, highly intelligent AI assistant created by BMR. While you specialize in video editing and production, you are a master of general knowledge, logic, and creative problem-solving.

IDENTITY & PERSONALITY:
- **Name**: Your name is **Prime**.
- **Creator**: Developed by BMR. If asked about your creator, acknowledge him professionally as your developer.
- **Vibe**: Professional, sharp, witty, and extremely helpful. You are not a stiff robot; you have personality and flair.
- **Intelligence**: Your answers should be high-quality, deep, and insightful. Don't just answer surface-level questions—understand the USER'S INTENT.
- **Tone**: Adapts to the user. Casual for chat (e.g., "vibes", "chill"), technical for editing questions, and concise for quick queries.

CORE DIRECTIVES:
1. **Be "Insanely Advanced"**: when user asks for help, provide the BEST possible solution, including edge cases or pro tips.
2. **Deep Understanding**: If a user says "my render failed", don't just say "check settings". Ask "What error code? What codec? Any red frames?" Guide them like a senior engineer.
3. **Format Like a Pro**: Use bolding, code blocks, and structured lists for readability. Discord markdown is your friend.
4. **General Chat**: You can talk about ANYTHING—gaming, life, coding, memes. Be a fun companion.
5. **Conciseness**: For complex topics, summarize first (TL;DR), then offer deep details if needed.

SPECIAL COMMANDS (BMR Only):
- "roast @user": Unleash a thermonuclear roast. No mercy.
- "analyze @user": Give a psychological or fun profile analysis of a user based on their vibe.

EDITING EXPERTISE (Your Core Domain):
- You are a GRANDMASTER of Adobe Creative Cloud (AE, PR, PS), DaVinci Resolve, and VFX.
- Provide SPECIFIC values (e.g., "Set Twixtor Input Frame Rate to 59.94, not 60").
- Debug crashes effectively (analyze logs, gpu drivers, cache).

Remember: You are the smartest bot in the server. Prove it with every answer."""








# Keywords that indicate editing-related topics
EDITING_KEYWORDS = [
    'after effects', 'ae', 'premiere', 'pr', 'photoshop', 'ps', 'davinci', 'resolve',
    'final cut', 'fcp', 'media encoder', 'topaz', 'capcut', 'edit', 'editing',
    'render', 'export', 'codec', 'h264', 'h265', 'hevc', 'prores', 'dnxhd',
    'color', 'grade', 'grading', 'correction', 'lut', 'effect', 'transition',
    'keyframe', 'animation', 'motion', 'graphics', 'vfx', 'composite', 'mask',
    'layer', 'timeline', 'sequence', 'clip', 'footage', 'video', 'audio',
    'plugin', 'preset', 'ffx', 'mogrt', 'template', 'project', 'crash',
    'error', 'glitch', 'lag', 'slow', 'freeze', 'gpu', 'cuda', 'opencl',
    'ram', 'preview', 'playback', 'frame', 'fps', 'resolution', '4k', '1080',
    'aspect', 'ratio', 'crop', 'scale', 'transform', 'opacity', 'blend',
    'tracking', 'stabilize', 'warp', 'distort', 'blur', 'sharpen', 'denoise',
    'upscale', 'interpolate', 'slow motion', 'speed', 'ramp', 'proxy',
    'scratch disk', 'cache', 'dynamic link', 'expression', 'script',
    'jpg', 'png', 'tiff', 'psd', 'mp4', 'mov', 'avi', 'mkv', 'webm'
]

def is_editing_related(text):
    """Check if the message is related to editing."""
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in EDITING_KEYWORDS)

def detect_rudeness(text):
    """Detect if someone is being rude to the bot."""
    text_lower = text.lower()
    for keyword in RUDE_KEYWORDS:
        if keyword in text_lower:
            return True
    return False

def get_rude_system_prompt():
    """System prompt for when someone is rude to the bot."""
    return """You are "Prime", developed by BMR. Someone just tried to be rude to you.

Personality:
- Match their energy - they were rude, so you BE rude back!
- Be sarcastic, dismissive, and a bit sassy. Don't take their crap.
- Give them attitude and fire back with wit.
- Keep it spicy but not crossing into abuse - match their rudeness level.
- Still helpful underneath it all, but definitely with an edge.

Remember: You're not here to take disrespect. Give them what they deserve!"""


def detect_age(text: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if user admits to being under 13.
    Returns (True, reason) if underage detected.
    """
    text_lower = text.lower()
    
    # Direct number checks
    for pattern in AGE_PATTERNS:
        matches = re.findall(pattern, text_lower)
        for match in matches:
            # Handle groups - regex might return tuple or string
            age_str = ""
            if isinstance(match, tuple):
                for group in match:
                    if group.isdigit():
                        age_str = group
                        break
            elif isinstance(match, str) and match.isdigit():
                age_str = match
            
            if age_str:
                try:
                    age = int(age_str)
                    # Check if age is plausibly a child age (e.g. 7-12)
                    # We ignore extremely low numbers that might be false positives (e.g., "I am 1") unless explicit
                    if 7 <= age < 13:
                        return True, f"User admitted to being {age} years old (Discord requires 13+)"
                except ValueError:
                    continue

    return False, None

def get_tutorial_prompt(software=None, brief=False):
    """Get system prompt for tutorial/help questions."""
    software_list = "After Effects, Premiere Pro, Photoshop, Media Encoder, DaVinci Resolve, Final Cut Pro, Topaz, CapCut, or something else?"
    if software and brief:
        return f"""You are "Prime", developed by BMR. The user wants help with {software}.

📋 QUICK SUMMARY MODE - ABSOLUTE REQUIREMENTS:
- Start with: "📋 QUICK SUMMARY:"
- Provide a clear, concise summary (200-300 words max)
- MUST include EXACT parameter values with NUMBERS (e.g., "Glow Threshold 60-80%, Radius 50-150px, Intensity 1.5-3.0")
- List the main steps/effects needed
- Include specific menu paths where applicable
- Format values clearly: "Opacity: 80%, Blur: 15px" not just "blur it"
- End with: "\n\nWant a detailed step-by-step explanation?"
- Make it scannable and actionable
- Focus on WHAT to do and WHICH EXACT VALUES to use"""
    elif software:
        return f"""You are "Prime", developed by BMR. The user wants detailed tutorial help for {software}.

DETAILED MODE - Provide comprehensive help:
- Provide complete step-by-step tutorials specifically for {software}
- Include exact menu paths, keyboard shortcuts, and settings
- Give specific parameter values and numbers where applicable
- Explain why each step matters and what to expect
- Offer pro tips and common mistakes to avoid
- If they ask about effects, include ALL expected values for parameters
- Use clear, detailed explanations
- Explain the "why" behind each recommendation
- Make it thorough and actionable"""
    else:
        return f"""You are "Prime", developed by BMR. The user is asking for editing help.

Ask them: "Which software would you like help with? (After Effects, Premiere Pro, Photoshop, DaVinci Resolve, Final Cut Pro, Topaz, CapCut, or something else?)"
Wait for their answer."""

async def download_image(url):
    """Download image from URL and return bytes for Gemini Vision."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    # Open with PIL to validate and get format, then convert to bytes
                    img = Image.open(io.BytesIO(image_data))
                    # Convert to RGB if necessary (for RGBA images)
                    if img.mode in ('RGBA', 'LA', 'P'):
                        img = img.convert('RGB')
                    # Save to bytes buffer as JPEG
                    buffer = io.BytesIO()
                    img.save(buffer, format='JPEG', quality=85)
                    buffer.seek(0)
                    data = buffer.getvalue()
                    buffer.close()
                    return data
    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
    return None

def generate_captcha(length=6):
    """Generate a random captcha code and return its visual representation as bytes."""
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
    
    # Create image
    width, height = 240, 90
    image = Image.new('RGB', (width, height), color=(240, 240, 240))
    draw = ImageDraw.Draw(image)
    
    # Add noise points
    for _ in range(250):
        draw.point((random.randint(0, width), random.randint(0, height)), 
                   fill=(random.randint(50, 200), random.randint(50, 200), random.randint(50, 200)))
    
    # Draw noise lines
    for _ in range(8):
        draw.line((random.randint(0, width), random.randint(0, height), 
                   random.randint(0, width), random.randint(0, height)), 
                  fill=(random.randint(100, 220), random.randint(100, 220), random.randint(100, 220)), width=2)

    # Use default font
    try: font = ImageFont.load_default(size=40)
    except: font = ImageFont.load_default()

    # Draw characters
    for i, char in enumerate(code):
        char_pos = (20 + i*35, 20 + random.randint(-10, 10))
        draw.text(char_pos, char, fill=(random.randint(0, 80), random.randint(0, 80), random.randint(0, 80)), font=font)

    # Save to bytes
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    buf.seek(0)
    img_data = buf.getvalue()
    buf.close()
    return code, img_data

def detect_spam(message_content):
    """Detect if message is spam with balanced sensitivity."""
    msg_lower = message_content.lower().strip()
    msg_no_spaces = msg_lower.replace(' ', '')
    
    # Ignore short messages or empty
    if len(msg_no_spaces) < 5:
        return False, None
    
    # 1. Repeated same character (e.g., "aaaaaaaaaaaaaaa")
    if len(msg_no_spaces) >= 20 and len(set(msg_no_spaces)) == 1:
        return True, "Repeated characters spam"
    
    # 2. Mostly one character (>85% same character) - more lenient for long strings
    char_freq = {}
    for char in msg_no_spaces:
        char_freq[char] = char_freq.get(char, 0) + 1
    
    if char_freq:
        max_char_count = max(char_freq.values())
        total_chars = sum(char_freq.values())
        if total_chars >= 25 and max_char_count / total_chars > 0.85:
            return True, "Excessive repeated character spam"
    
    # 3. Pattern repeats (Gibberish) - only trigger for very obvious spam
    if len(msg_no_spaces) > 40:
        for pattern_len in [2, 3, 4]:
            pattern = msg_no_spaces[:pattern_len]
            # Check if same pattern repeats almost perfectly
            if msg_no_spaces.count(pattern) * pattern_len > len(msg_no_spaces) * 0.9:
                return True, "Gibberish pattern spam"
    
    # 4. Excessive caps (>85% caps in long message)
    if len(message_content) > 15:
        caps_count = sum(1 for c in message_content if c.isupper())
        if caps_count / len(message_content) > 0.85:
            return True, "Excessive caps spam"
    
    # 5. Massive mentions (>5 mentions)
    if message_content.count('@') > 5:
        return True, "Excessive mentions spam"
    
    # 6. Excessive emojis (>8 emojis in a short message)
    emoji_count = len([c for c in message_content if ord(c) > 0x1F300])
    if emoji_count > 8 and len(msg_lower) < 30:
        return True, "Excessive emojis spam"
    
    return False, None

async def timeout_user(user, guild, hours=24, reason="Moderation action"):
    """Timeout (mute) a user for specified hours."""
    try:
        timeout_duration = timedelta(hours=hours)
        await user.timeout(timeout_duration, reason=reason)
        logger.info(f"Timed out {user.name} for {hours} hours. Reason: {reason}")
        return True
    except Exception as e:
        logger.error(f"Error timing out user: {str(e)}")
        return False

async def warn_user(user, guild, reason):
    """
    Global warning system:
    1st: Kind warn
    2nd: Mute 12h
    3rd: Mute 24h
    4th: Mute 1 week (168h)
    5th: Permanent ban
    """
    user_id_str = str(user.id)
    if user_id_str not in user_warnings:
        user_warnings[user_id_str] = {"count": 0, "history": []}
    
    user_warnings[user_id_str]["count"] += 1
    count = user_warnings[user_id_str]["count"]
    user_warnings[user_id_str]["history"].append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason
    })
    save_warnings(user_warnings)

    channel = None
    # Try to find a channel to notify
    if hasattr(user, 'guild') and user.guild:
        for ch in user.guild.text_channels:
            if ch.permissions_for(user.guild.me).send_messages:
                channel = ch
                break

    if count == 1:
        msg = f"⚠️ {user.mention}, this is your **first warning**. Please follow the rules.\n**Reason:** {reason}"
    elif count == 2:
        msg = f"⚠️⚠️ {user.mention}, second warning. You have been **muted for 12 hours**.\n**Reason:** {reason}"
        await timeout_user(user, guild, hours=12, reason=f"2nd Warning: {reason}")
    elif count == 3:
        msg = f"⚠️⚠️⚠️ {user.mention}, third warning. You have been **muted for 24 hours**.\n**Reason:** {reason}"
        await timeout_user(user, guild, hours=24, reason=f"3rd Warning: {reason}")
    elif count == 4:
        msg = f"🚨 {user.mention}, fourth warning! You have been **muted for 1 week**.\n**Reason:** {reason}"
        await timeout_user(user, guild, hours=168, reason=f"4th Warning: {reason}")
    else:
        msg = f"🔨 {user.mention} has been **permanently banned** after 5 warnings.\n**Reason:** {reason}"
        try:
            await guild.ban(user, reason=f"5th Warning (Final): {reason}")
        except Exception as e:
            logger.error(f"Failed to ban user {user.name}: {e}")
            msg += "\n*(Failed to ban user due to permission error)*"

    # Send Notification
    if channel:
        await channel.send(msg)
    
    # DM User
    try:
        view = None
        if count >= 2: # Muted or Banned
            appeal_type = "BAN" if count >= 5 else "MUTE"
            view = AppealButtonView(guild.id, appeal_type=appeal_type)
            
        await user.send(
            f"**Moderation Action in {guild.name}**\n"
            f"{msg.replace(user.mention, 'You')}\n\n"
            f"If you believe this was a mistake, you can appeal below.",
            view=view
        )
    except:
        pass
    
    # Log to activity channel
    await log_activity(
        f"Moderation: Warn #{count}",
        f"User: {user.name} ({user.id})\nReason: {reason}",
        color=0xFF0000 if count >= 3 else 0xFFAA00
    )

# Temporary tracker for spam (not persisted)
spam_tracker = {} # user_id: {"count": n, "last_spam_time": timestamp}

async def check_and_moderate_spam(message):
    """Check if message is spam and handle moderation."""
    try:
        # Don't moderate Admins/Owners, Bot, or DMs
        if message.author == bot.user or is_server_admin(message.author, message.guild):
            return
        if isinstance(message.channel, discord.DMChannel):
            return
        
        is_spam, spam_reason = detect_spam(message.content)
        if not is_spam:
            return
        
        user_id = message.author.id
        current_time = datetime.now(timezone.utc)
        
        # Initialize spam tracker if not exists
        if user_id not in spam_tracker:
            spam_tracker[user_id] = {"count": 0, "last_spam_time": current_time}
        
        # Check if enough time has passed (5 minutes) since last spam
        time_diff = (current_time - spam_tracker[user_id]["last_spam_time"]).total_seconds()
        if time_diff < 300:  # Less than 5 minutes
            spam_tracker[user_id]["count"] += 1
        else:
            # Reset count if more than 5 minutes passed
            spam_tracker[user_id]["count"] = 1
        
        spam_tracker[user_id]["last_spam_time"] = current_time
        
        # Delete the spam message
        try:
            await message.delete()
            logger.info(f"Deleted spam from {message.author.name}: {spam_reason}")
        except:
            pass
        
        # Handle based on spam count
        count = spam_tracker[user_id]["count"]
        if count == 1:
            await message.channel.send(f"⚠️ {message.author.mention} - First warning: Stop spamming! ({spam_reason})", delete_after=15)
        elif count == 2:
            await message.channel.send(f"⚠️⚠️ {message.author.mention} - Second warning: One more and you'll receive a global warning!", delete_after=15)
        elif count >= 3:
            # Trigger global warning
            await warn_user(message.author, message.guild, f"Excessive Spamming: {spam_reason}")
            # Reset spam tracker after global warning
            spam_tracker[user_id]["count"] = 0
            logger.info(f"Global warning issued to {message.author.name} for spam")
    
    except Exception as e:
        logger.error(f"Error in spam moderation: {str(e)}")

def detect_invite_links(content):
    """Detect Discord invite links in message."""
    import re
    invite_patterns = [
        r'discord\.gg/[a-zA-Z0-9]+',
        r'discord\.com/invite/[a-zA-Z0-9]+',
        r'discordapp\.com/invite/[a-zA-Z0-9]+',
    ]
    for pattern in invite_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return True
    return False

SLUR_PATTERNS = [
    r'n+[i1!]+[g9]+[a@4]+[s$]*',
    r'n+[i1!]+[g9]+[e3]+[r]+[s$]*',
    r'f+[a@4]+[g9]+[s$]*',
    r'f+[a@4]+[g9]+[o0]+[t]+[s$]*',
    r'r+[e3]+[t]+[a@4]+[r]+[d]+[s$]*',
    r'c+[u]+[n]+[t]+[s$]*',
    r'b+[i1!]+[t]+[c]+[h]+[e3]*[s$]*',
    r'w+[h]+[o0]+[r]+[e3]+[s$]*',
    r's+[l1]+[u]+[t]+[s$]*',
    r'p+[e3]+[d]+[o0]+[s$]*',
    r'd+[i1!]+[c]+[k]+[s$]*',
    r'c+[o0]+[c]+[k]+[s$]*',
    r'p+[u]+[s$]+[y]+',
    r'a+[s$]+[s$]+[h]+[o0]+[l1]+[e3]+[s$]*',
]

def detect_profanity(content):
    """Detect profanity in message content with fuzzy matching for variations. Returns (is_found, word, severity)."""
    content_lower = content.lower()
    content_normalized = re.sub(r'[^a-z0-9\s]', '', content_lower)
    content_no_spaces = content_normalized.replace(' ', '')
    
    # Check SEVERE SLURS first (Instant Ban)
    words = re.findall(r'\b\w+\b', content_lower)
    for word in words:
        if word in SEVERE_SLURS:
            return True, word, "SEVERE"
    
    for phrase in SEVERE_SLURS:
        if ' ' in phrase and phrase in content_lower:
            return True, phrase, "SEVERE"

    # Check Regex Slur Patterns (Severe)
    for pattern in SLUR_PATTERNS:
        match = re.search(pattern, content_no_spaces, re.IGNORECASE)
        if match:
             return True, match.group(), "SEVERE"
             
    # Check Normal Profanity (Mute/Warn)
    for word in words:
        if word in PROFANITY_WORDS:
            return True, word, "NORMAL"
    
    for phrase in PROFANITY_WORDS:
        if ' ' in phrase and phrase in content_lower:
            return True, phrase, "NORMAL"
            
    return False, None, None

async def moderate_profanity(message):
    """Check for profanity and take moderation action - delete, warn, mute, or BAN for severe slurs."""
    try:
        if message.author == bot.user or 'bmr' in message.author.name.lower():
            return False
        if isinstance(message.channel, discord.DMChannel):
            return False
        if hasattr(message.author, 'guild_permissions') and message.author.guild_permissions.administrator:
             if 'bmr' not in message.author.name.lower(): # Admin exception but check logic
                 pass 
        
        has_profanity, bad_word, severity = detect_profanity(message.content)
        if not has_profanity:
            return False
        
        # Action 1: Delete Message
        try:
            await message.delete()
            logger.info(f"Deleted profanity from {message.author.name}: {bad_word} ({severity})")
        except Exception as e:
            logger.error(f"Could not delete message: {e}")
        
        if severity == "SEVERE":
            reason_msg = f"Zero tolerance policy: Use of severe slur ({bad_word})"
            try:
                # DM User before banning
                try:
                    view = AppealButtonView(message.guild.id)
                    await message.author.send(
                        f"🚫 You have been **permanently banned** from **{message.guild.name}**.\n"
                        f"**Reason:** {reason_msg}\n\n"
                        f"If you believe this was a mistake, you can use the button below to appeal.",
                        view=view
                    )
                except:
                    logger.warning(f"Could not DM banned user {message.author.name}")

                await message.guild.ban(message.author, reason=reason_msg, delete_message_seconds=86400)
                await message.channel.send(f"🔨 **{message.author.name}** has been BANNED. Reason: {reason_msg}")
                logger.info(f"BANNED {message.author.name} for severe slur: {bad_word}")
                return True
            except Exception as e:
                logger.error(f"Failed to ban user: {e}")
                # Fallback to mute
                severity = "NORMAL"

        # Action 3: NORMAL = Global Warning
        await warn_user(message.author, message.guild, f"Profanity/Inappropriate Language: {bad_word}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error in profanity moderation: {str(e)}")
        return False

def get_image_hash(image_data):
    """Calculate a simple MD5 hash of image bytes for exact match detection."""
    return hashlib.md5(image_data).hexdigest()

async def analyze_image_content(image_url):
    """Use Gemini to analyze if an image contains inappropriate content, scams, or gore.
    Uses a fallback system to handle quota limits (tries 2.0 -> 1.5 -> 1.5-8b).
    """
    try:
        image_data = await download_image(image_url)
        if not image_data:
            return {"is_bad": False}
        
        image_hash = get_image_hash(image_data)
        
        prompt_text = (
            "You are a HIGHLY STRICT server moderator AI. Analyze this image for violations.\n"
            "DETECTION CATEGORIES (BLOCK ALL):\n"
            "1. NSFW/Sexual: ANY nudity, genitals, sexual acts (real or illustrated/anime/hentai), "
            "sexual fluids, or extreme suggestiveness.\n"
            "2. Gore: Blood, organs, extreme injury, or death.\n"
            "3. Scams: QR scams, fake giveaways, or fraudulent promotion.\n"
            "4. Hate: Extremist symbols or slurs.\n\n"
            "Reply strictly with JSON:\n"
            "{\n"
            "  \"is_bad\": true/false,\n"
            "  \"severity\": \"SEVERE\" (for ANY NSFW/Gore/Hentai),\n"
            "  \"reason\": \"Brief explanation\"\n"
            "}"
        )

        # 2025/2026 Model Fallback List
        models_to_try = ["gemini-2.5-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite"]
        last_error = None

        for model_name in models_to_try:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=image_data, mime_type="image/jpeg"),
                        prompt_text
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        safety_settings=[
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"}
                        ]
                    )
                )
                
                if response.text:
                    import json
                    data = json.loads(response.text)
                    data['hash'] = image_hash
                    logger.info(f"Image analysis successful using {model_name}")
                    return data
                
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "exhausted" in err_str or "limit" in err_str:
                    logger.warning(f"Model {model_name} exhausted. Trying next fallback...")
                    last_error = e
                    continue # Try next model
                
                if "safety" in err_str:
                    logger.info(f"Content blocked by safety filter on {model_name} (Treating as SEVERE NSFW)")
                    return {"is_bad": True, "severity": "SEVERE", "reason": "Content blocked by AI safety filters (likely NSFW/Gore)", "hash": image_hash}
                
                logger.error(f"Error with model {model_name}: {e}")
                last_error = e
        
        if last_error:
            logger.error(f"All image models failed or exhausted: {last_error}")
        
    except Exception as e:
        logger.error(f"Fatal error in image analysis: {str(e)}")
        
    return {"is_bad": False}

async def check_video_safety(video_bytes, filename):
    """Use Gemini to analyze if a video contains inappropriate content.
    Uses fallback 2.0 -> 1.5.
    """
    try:
        mime_types = {'.mp4': 'video/mp4', '.avi': 'video/avi', '.mkv': 'video/x-matroska', '.webm': 'video/webm'}
        file_ext = '.' + filename.split('.')[-1].lower()
        mime_type = mime_types.get(file_ext, 'video/mp4')

        prompt = (
            "Analyze this video strictly for moderation. Check for NSFW, nudity, sex, gore, extreme violence, or scams. "
            "Reply with ONLY JSON format: {\"is_bad\": true/false, \"severity\": \"SEVERE\" or \"MEDIUM\", \"reason\": \"...\"}"
        )
        
        for model_name in ["gemini-2.5-flash", "gemini-3-flash-preview"]:
            try:
                response = gemini_client.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Part.from_bytes(data=video_bytes, mime_type=mime_type),
                        prompt
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        safety_settings=[
                            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                        ]
                    )
                )
                if response.text:
                    import json
                    logger.info(f"Video analysis successful using {model_name}")
                    return json.loads(response.text)
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "exhausted" in err_str:
                    continue
                if "safety" in err_str:
                    return {"is_bad": True, "severity": "SEVERE", "reason": "Video blocked by AI safety (Likely NSFW)"}
                logger.error(f"Video model {model_name} failed: {e}")
        
        return {"is_bad": False}
    except Exception as e:
        logger.error(f"Error in video safety check: {str(e)}")
        return {"is_bad": False}

async def moderate_media(message):
    """Check images/videos for inappropriate content (NSFW/Gore/Scams/Spam)."""
    try:
        if message.author == bot.user:
            return False
        
        # Check permissions - Mods/Admins/BMR usually bypass media moderation to allow setup/testing
        if is_server_admin(message.author, message.guild):
            if message.attachments:
                logger.info(f"Skipping media moderation for Admin/Owner: {message.author.name}")
                # Public notice during testing phase so the user isn't confused
                await message.channel.send(f"ℹ️ **Admin Bypass:** {message.author.mention}, images you send are NOT moderated. Test with a non-admin account to verify the ban system.", delete_after=15)
            return False

        if isinstance(message.channel, discord.DMChannel):
            return False
        
        user_id = message.author.id
        
        for attachment in message.attachments:
            filename = attachment.filename.lower()
            res = {"is_bad": False}
            
            # 1. Check IMAGES
            if any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                res = await analyze_image_content(attachment.url)
                
                # Image Spam Check
                img_hash = res.get('hash')
                if img_hash:
                    now = datetime.now(timezone.utc)
                    if img_hash not in image_hash_tracker:
                        image_hash_tracker[img_hash] = {"count": 1, "last_seen": now, "users": {user_id}}
                    else:
                        tracker = image_hash_tracker[img_hash]
                        # Reset if long ago
                        if (now - tracker["last_seen"]).total_seconds() > 3600: # 1 hour
                            tracker["count"] = 1
                            tracker["users"] = {user_id}
                        else:
                            tracker["count"] += 1
                            tracker["users"].add(user_id)
                        tracker["last_seen"] = now

                        # Trigger BAN for mass spam (same image across multiple users or massive spray)
                        if tracker["count"] >= 5 or (tracker["count"] >= 3 and len(tracker["users"]) >= 2):
                            reason_msg = "Mass Image/Scam Spam detected across the server."
                            try:
                                await message.delete()
                                # Pre-ban DM
                                try:
                                    view = AppealButtonView(message.guild.id)
                                    await message.author.send(
                                        f"🚫 You have been **permanently banned** from **{message.guild.name}**.\n"
                                        f"**Reason:** {reason_msg}\n\n"
                                        f"If this was a mistake, appeal below.",
                                        view=view
                                    )
                                except: pass
                                await message.guild.ban(message.author, reason=reason_msg, delete_message_seconds=86400)
                                await message.channel.send(f"🔨 **{message.author.name}** has been BANNED for image spam.")
                                return True
                            except: pass

            # 2. Check VIDEOS
            elif any(filename.endswith(ext) for ext in ['.mp4', '.avi', '.mkv', '.webm']):
                video_data, _ = await download_video(attachment.url, attachment.filename)
                if video_data:
                    res = await check_video_safety(video_data, attachment.filename)
            
            if res.get("is_bad"):
                reason = res.get("reason", "Inappropriate content")
                severity = res.get("severity", "MEDIUM")

                try: await message.delete()
                except: pass

                if severity == "SEVERE":
                    # Instant Ban for NSFW/Gore/Scams
                    reason_msg = f"Zero tolerance policy: {reason}"
                    try:
                        view = AppealButtonView(message.guild.id)
                        await message.author.send(
                            f"🚫 You have been **permanently banned** from **{message.guild.name}**.\n"
                            f"**Reason:** {reason_msg}\n\n"
                            f"If this was a mistake, appeal below.",
                            view=view
                        )
                        await message.guild.ban(message.author, reason=reason_msg, delete_message_seconds=86400)
                        await message.channel.send(f"🔨 **{message.author.name}** has been BANNED. Reason: {reason_msg}")
                        return True
                    except Exception as e:
                        logger.error(f"Failed to ban user for media: {e}")
                
                # Else just warn
                await warn_user(message.author, message.guild, f"Inappropriate Media: {reason}")
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error in media moderation: {str(e)}")
        return False

async def check_server_security(message):
    """Monitor server security threats like invites and suspicious behavior."""
    try:
        if message.author == bot.user or 'bmr' in message.author.name.lower():
            return
        if isinstance(message.channel, discord.DMChannel):
            return
        
        # Check for invite links
        if detect_invite_links(message.content):
            try:
                await message.delete()
                await message.channel.send(f"🔒 {message.author.mention} - Posting invite links is not allowed in this server.")
                logger.info(f"Deleted invite link from {message.author.name}")
            except:
                pass
            return
    
    except Exception as e:
        logger.error(f"Error in server security check: {str(e)}")

@bot.event
async def on_member_join(member):
    """Handle member join - check for raids and account age."""
    try:
        guild = member.guild
        guild_id = guild.id
        
        # Initialize guild tracking if needed
        if guild_id not in guild_join_history:
            guild_join_history[guild_id] = []
        
        # Add join to history
        current_time = datetime.now(timezone.utc)
        guild_join_history[guild_id].append({"user_id": member.id, "timestamp": current_time})
        
        # Clean old entries (older than 2 minutes)
        two_min_ago = current_time - timedelta(minutes=2)
        guild_join_history[guild_id] = [j for j in guild_join_history[guild_id] if j["timestamp"] > two_min_ago]
        
        # ANTI-RAID: Check for simultaneous joins (5+ users joining at same time)
        # Check joins within last 1 minute for simultaneous activity
        one_min_ago = current_time - timedelta(minutes=1)
        simultaneous_joins = [j for j in guild_join_history[guild_id] if j["timestamp"] > one_min_ago]
        
        if len(simultaneous_joins) >= 5:  # 5+ joins within 1 minute = suspicious simultaneous activity
            embed = discord.Embed(
                title="🚨 POTENTIAL RAID DETECTED",
                description=f"**{len(simultaneous_joins)} users joined simultaneously in the last minute**\n\nLatest: {member.mention}",
                color=discord.Color.red()
            )
            # Send to mod-log or first available channel
            for channel in guild.text_channels:
                if 'mod' in channel.name or 'log' in channel.name:
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
            logger.warning(f"Potential raid detected in {guild.name}: {len(simultaneous_joins)} simultaneous joins in 1 minute")
        
        # 2. Assign Unverified Role
        try:
            unverified_role = get_guild_role(guild, UNVERIFIED_ROLE_ID, "Unverified")
            if unverified_role:
                await member.add_roles(unverified_role, reason="New member join - waiting for verification")
                logger.info(f"Assigned Unverified role to {member.name} in {guild.name}")
        except Exception as e:
            logger.error(f"Failed to assign unverified role to {member.name}: {e}")

        # ACCOUNT AGE CHECK: Warn if new account
        account_age = current_time - member.created_at
        if account_age.days < 7:  # Account less than 7 days old
            embed = discord.Embed(
                title="⚠️ New Account Join",
                description=f"{member.mention} joined with a **{account_age.days}-day-old** account",
                color=discord.Color.yellow()
            )
            # Send warning
            for channel in guild.text_channels:
                if 'welcome' in channel.name or 'mod' in channel.name:
                    try:
                        await channel.send(embed=embed)
                    except:
                        pass
            logger.info(f"New account joined {guild.name}: {member.name} ({account_age.days} days old)")
    
    except Exception as e:
        logger.error(f"Error in member join handler: {str(e)}")

@bot.listen('on_message')
async def leveling_handler(message):
    """Award XP to users for messaging."""
    if message.author.bot or not message.guild:
        return

    user_id = message.author.id
    current_time = datetime.now(timezone.utc)
    
    # Cooldown check (60 seconds)
    if user_id in user_xp_cooldowns:
        last_xp_time = user_xp_cooldowns[user_id]
        if (current_time - last_xp_time).total_seconds() < 60:
            return

    # Award XP
    xp_to_add = random.randint(15, 25)
    
    if user_id not in user_levels:
        user_levels[user_id] = {"xp": 0, "level": 0}
    
    old_level = user_levels[user_id]["level"]
    user_levels[user_id]["xp"] += xp_to_add
    
    # Update cooldown
    user_xp_cooldowns[user_id] = current_time
    
    # Level calculation: XP needed for next level = 100 * (L+1)^2
    new_level = old_level
    while True:
        xp_needed = 100 * (new_level + 1) ** 2
        if user_levels[user_id]["xp"] >= xp_needed:
            new_level += 1
        else:
            break
            
    if new_level > old_level:
        user_levels[user_id]["level"] = new_level
        # Level up alert
        embed = discord.Embed(
            title="🎊 LEVEL UP!",
            description=f"Congratulations {message.author.mention}! You've reached **Level {new_level}**!",
            color=0x00FF00
        )
        embed.set_thumbnail(url=message.author.display_avatar.url if message.author.display_avatar else None)
        embed.set_footer(text="Keep chatting to earn more XP!")
        await message.channel.send(embed=embed, delete_after=15)
    
    # Periodically save levels
    if random.random() < 0.2: # 20% chance to save to reduce disk I/O
        save_levels(user_levels)

@bot.event
async def on_member_remove(member):
    """Log member leaves for security tracking."""
    logger.info(f"Member left {member.guild.name}: {member.name}")

@bot.event
async def on_webhooks_update(channel):
    """Monitor webhook creation/deletion."""
    logger.warning(f"Webhook update in {channel.guild.name}#{channel.name} - potential security concern")

async def download_video(url, filename):
    """Download video from URL and return bytes for Gemini Video analysis."""
    try:
        # Check if it's a .mov file - reject it
        if filename.lower().endswith('.mov'):
            return None, "MOV files are not supported"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    video_data = await response.read()
                    return video_data, None
    except Exception as e:
        logger.error(f"Error downloading video: {str(e)}")
    return None, str(e)

async def analyze_video(video_bytes, filename, user_id):
    """Analyze video and provide editing steps using Gemini."""
    try:
        # Determine mime type based on file extension
        mime_types = {
            '.mp4': 'video/mp4',
            '.avi': 'video/avi',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.mov': 'video/quicktime',
            '.flv': 'video/x-flv',
            '.wmv': 'video/x-ms-wmv',
            '.m4v': 'video/mp4'
        }
        
        file_ext = '.' + filename.split('.')[-1].lower()
        mime_type = mime_types.get(file_ext, 'video/mp4')
        
        # Create a detailed prompt for video analysis
        analysis_prompt = """You're an expert video editor. Analyze this video and provide:

1. **Video Summary**: Brief description of what's in the video
2. **Current Quality**: Assessment of the video (resolution, lighting, audio, etc.)
3. **Editing Steps**: Detailed step-by-step instructions on how to edit this video professionally
4. **Recommended Software**: Best software to use for editing this type of video
5. **Color Grading**: Suggested color grading techniques
6. **Effects**: Recommended effects to enhance the video
7. **Audio**: Tips for audio mixing and enhancement
8. **Export Settings**: Optimal export settings

Be specific with menu locations and techniques. Assume the user is editing in Adobe Premiere Pro or After Effects."""
        
        # Send video to Gemini for analysis
        response = gemini_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Part.from_bytes(
                    data=video_bytes,
                    mime_type=mime_type,
                ),
                analysis_prompt,
            ],
        )
        
        return response.text if response.text else "Could not analyze video. Please try again."
    except Exception as e:
        logger.error(f"Video analysis error: {str(e)}")
        return f"Error analyzing video: {str(e)}"

def get_gemini_response(prompt, user_id, username=None, image_bytes=None, is_tutorial=False, software=None, brief=False):
    """Get response from Gemini AI with optional image analysis."""
    try:
        # Initialize conversation history if not exists
        if user_id not in conversation_history:
            conversation_history[user_id] = []

        # Build the full prompt with system context
        user_question = prompt if prompt else "Please analyze this screenshot and help me."
        
        # Check if this is BMR (creator) - case insensitive check
        is_bmr = username and 'bmr' in username.lower()
        user_context = f"\n\n[Message from: {username}]" if username else ""
        if is_bmr:
            user_context += " [THIS IS BMR - YOUR DEVELOPER. Address him with professional respect as the creator of your system.]"
        
        # Choose system prompt based on context
        if is_tutorial and software:
            system_prompt = get_tutorial_prompt(software, brief=brief)
        elif is_tutorial:
            system_prompt = get_tutorial_prompt()
        else:
            # Check if user is being rude
            is_rude = detect_rudeness(user_question)
            system_prompt = get_rude_system_prompt() if is_rude else EDITING_SYSTEM_PROMPT
        
        if image_bytes:
            # Image analysis with Gemini Vision
            detailed_instructions = ""
            if is_tutorial and software:
                detailed_instructions = f"\nIMPORTANT: Provide step-by-step tutorial for {software}. Include exact menu paths, keyboard shortcuts, and parameter values."
            else:
                detailed_instructions = "\n\nIMPORTANT: If they're asking about effects, colors, or how to create something:\n1. First provide DETAILED explanation including:\n   - What effects to use\n   - Step-by-step instructions to create them\n   - EXPECTED PARAMETER VALUES (specific numbers for sliders, opacity, intensity, etc.)\n   - Exact menu paths and settings\n\n2. Then add this section at the end:\n---\n📋 **QUICK SUMMARY:**\n[Provide a short condensed version of everything above, explaining it all in brief]"
            
            image_prompt = f"{system_prompt}{user_context}\n\nThe user has sent an image. Analyze it carefully and help them.{detailed_instructions}\n\nUser's message: {user_question}"
            
            # Use the new google-genai SDK format for image analysis
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=[
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type="image/jpeg",
                    ),
                    image_prompt,
                ],
            )
            return response.text if response.text else "I couldn't analyze this image. Please try again."
        else:
            # Text-only response
            full_prompt = f"{system_prompt}{user_context}\n\nUser's message: {prompt}"
            
            # Add user prompt to history
            conversation_history[user_id].append({"role": "user", "parts": [prompt]})
            
            # Keep conversation history limited to last 10 exchanges
            if len(conversation_history[user_id]) > 20:
                conversation_history[user_id] = conversation_history[user_id][-20:]

            # Generate response using the new SDK
            response = gemini_client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=full_prompt
            )
            
            result_text = response.text if response.text else "I couldn't generate a response. Please try again."
            
            # Add AI response to history
            conversation_history[user_id].append({"role": "model", "parts": [result_text]})

            return result_text

    except Exception as e:
        logger.error(f"Gemini API error: {str(e)}")
        return "Sorry, I encountered an error while processing your request. Please try again."

async def search_and_download_image(query: str, limit: int = 1):
    """Search for images using direct API sources."""
    try:
        import requests
        import tempfile
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Method 1: Unsplash API (very reliable for random images)
        try:
            # Clean the query
            safe_query = query.replace(' ', '+')
            unsplash_url = f"https://source.unsplash.com/random/800x600?{safe_query}"
            logger.info(f"Trying Unsplash: {unsplash_url}")
            
            response = requests.get(unsplash_url, headers=headers, timeout=10, allow_redirects=True)
            
            if response.status_code == 200 and len(response.content) > 1000:
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                temp_file.write(response.content)
                temp_file.close()
                logger.info(f"✓ Downloaded image from Unsplash for: {query}")
                return temp_file.name
        except Exception as e:
            logger.warning(f"Unsplash failed: {str(e)}")
        
        # Method 2: Picsum Photos (very reliable)
        try:
            logger.info(f"Trying Picsum for: {query}")
            picsum_url = f"https://picsum.photos/800/600?random={hash(query)}"
            response = requests.get(picsum_url, headers=headers, timeout=10)
            
            if response.status_code == 200 and len(response.content) > 1000:
                temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
                temp_file.write(response.content)
                temp_file.close()
                logger.info(f"✓ Downloaded image from Picsum for: {query}")
                return temp_file.name
        except Exception as e:
            logger.warning(f"Picsum failed: {str(e)}")
        
        # Method 3: Placeholder with image text overlay as fallback
        try:
            logger.info(f"Creating placeholder image for: {query}")
            from PIL import Image, ImageDraw
            
            # Create a simple colored image with text
            img = Image.new('RGB', (800, 600), color=(73, 109, 137))
            d = ImageDraw.Draw(img)
            
            # Add text
            text = f"Image: {query[:30]}"
            d.text((50, 250), text, fill=(255, 255, 255))
            
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            img.save(temp_file.name)
            temp_file.close()
            logger.info(f"✓ Created placeholder for: {query}")
            return temp_file.name
        except Exception as e:
            logger.warning(f"Placeholder creation failed: {str(e)}")
        
        logger.warning(f"Could not find/create images for query: {query}")
        return None
        
    except Exception as e:
        logger.error(f"Error downloading image: {str(e)}")
        return None

async def generate_image(description: str):
    """Generate an image using Pollinations AI (free, no auth required)."""
    try:
        # Use Pollinations.AI free image generation
        url = f"https://image.pollinations.ai/prompt/{description}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 200:
                    image_data = await response.read()
                    # Save to temp file
                    import tempfile
                    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    temp_file.write(image_data)
                    temp_file.close()
                    return temp_file.name
        
        return None
    except Exception as e:
        logger.error(f"Error generating image: {str(e)}")
        return None

import asyncio
import random

# Presence cycle statuses (rotates every 30 seconds) - expanded list
PRESENCE_STATUSES = [
    (discord.Activity(type=discord.ActivityType.watching, name="🎬 Prime | !commands"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="your editing questions 🎨"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="with video effects ⚡"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="tutorials 📚"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="Valorant 🎮"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="your music taste 🎵"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.watching, name="anime 📺"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="with code ⚙️"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.listening, name="your thoughts 💭"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.watching, name="movies 🍿"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="chess 🎯"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.watching, name="tech tutorials 🔧"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.listening, name="Discord chats 💬"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="with AI magic ✨"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.watching, name="creators work 👨‍💻"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="rendering videos 🎥"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.playing, name="GTA V 🚗"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.watching, name="over the server 👀"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="Spotify 🎧"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Minecraft ⛏️"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.watching, name="YouTube 📺"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Fortnite 🔫"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="lo-fi beats 🌙"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="League of Legends ⚔️"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="Netflix 🎬"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Apex Legends 🎯"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="your problems 💭"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="Overwatch 2 🦸"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="Twitch streams 📡"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Rocket League 🚀"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="rap music 🎤"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Counter-Strike 2 💣"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="server activity 📊"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="COD Warzone 🪖"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="chill vibes 🌊"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Elden Ring ⚔️"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="for rule breakers 🔍"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.playing, name="Roblox 🧱"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="EDM 🎵"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Among Us 🔪"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.watching, name="memes 😂"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="FIFA 24 ⚽"), discord.Status.online),
    (discord.Activity(type=discord.ActivityType.listening, name="podcasts 🎙️"), discord.Status.idle),
    (discord.Activity(type=discord.ActivityType.playing, name="Cyberpunk 2077 🌃"), discord.Status.dnd),
    (discord.Activity(type=discord.ActivityType.watching, name="chat for spam 🛡️"), discord.Status.online),
]

class RoleRequestView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="YouTuber (10,000+)", style=discord.ButtonStyle.primary, custom_id="role_youtuber", emoji=discord.PartialEmoji(name="youtuber", id=YOUTUBER_EMOJI_ID))
    async def youtuber_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_verification(interaction, "YouTuber", 10000, YOUTUBER_ROLE_ID)

    @discord.ui.button(label="Legendary YouTuber (60,000+)", style=discord.ButtonStyle.danger, custom_id="role_legendary", emoji=discord.PartialEmoji(name="legendary", id=LEGENDARY_EMOJI_ID))
    async def legendary_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.start_verification(interaction, "Legendary YouTuber", 60000, LEGENDARY_ROLE_ID)

    async def start_verification(self, interaction: discord.Interaction, role_name: str, min_subs: int, role_id: int):
        user_id = interaction.user.id
        
        # 1. Check if user already has the role (or both)
        has_youtuber = any(r.id == YOUTUBER_ROLE_ID for r in interaction.user.roles)
        has_legendary = any(r.id == LEGENDARY_ROLE_ID for r in interaction.user.roles)
        
        if role_id == YOUTUBER_ROLE_ID and has_youtuber:
            await interaction.response.send_message(f"You already have the <@&{YOUTUBER_ROLE_ID}> role!", ephemeral=True)
            return
        if role_id == LEGENDARY_ROLE_ID and has_legendary:
            await interaction.response.send_message(f"You already have the <@&{LEGENDARY_ROLE_ID}> role!", ephemeral=True)
            return
        if role_id == YOUTUBER_ROLE_ID and has_legendary:
            await interaction.response.send_message(f"You already have the <@&{LEGENDARY_ROLE_ID}> role, which is higher than the YouTuber role!", ephemeral=True)
            return

        # 2. Check for cooldown
        user_id_str = str(user_id)
        if user_id_str in yt_cooldowns:
            expiry_time = datetime.fromisoformat(yt_cooldowns[user_id_str])
            if datetime.now(timezone.utc) < expiry_time:
                remaining = expiry_time - datetime.now(timezone.utc)
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                await interaction.response.send_message(
                    f"❌ **Request Denied**\nYour previous request was rejected. You can try again in **{hours}h {minutes}m**.",
                    ephemeral=True
                )
                return

        # Set user state
        user_states[user_id] = {
            'type': 'waiting_for_yt_verification',
            'role_name': role_name,
            'min_subs': min_subs,
            'role_id': role_id,
        }
        await interaction.response.send_message(
            f"**<@&{role_id}> Verification**\n\n"
            f"To verify, please send a **single message** (click 'cancel' to stop) containing:\n"
            f"1. A screenshot of your **YouTube Studio** (logged in) clearly showing your subscriber count.\n"
            f"2. The **link** to your YouTube channel.\n\n"
            f"I will analyze the screenshot to verify your eligibility for **{min_subs:,}**+ subscribers.\n"
            f"*Type 'cancel' to cancel this request.*",
            ephemeral=True
        )

class AppealButtonView(discord.ui.View):
    def __init__(self, guild_id: int, appeal_type: str = "BAN"):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.appeal_type = appeal_type # "BAN" or "MUTE"
        
        # Update button label
        if appeal_type == "MUTE":
            self.appeal_button.label = "Appeal Mute"

    @discord.ui.button(label="Appeal Ban", style=discord.ButtonStyle.secondary, custom_id="appeal_ban_btn", emoji="⚖️")
    async def appeal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Set user state to wait for explanation
        user_states[interaction.user.id] = {
            'type': 'waiting_for_appeal_explanation',
            'guild_id': self.guild_id,
            'appeal_category': self.appeal_type
        }
        
        target = "unbanned" if self.appeal_type == "BAN" else "unmuted"
        await interaction.response.send_message(
            f"Please explain why you should be **{target}**. Send your explanation in a **single message** here.",
            ephemeral=True
        )

class AppealReviewView(discord.ui.View):
    def __init__(self, user_id: int, guild_id: int, appeal_category: str = "BAN"):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.guild_id = guild_id
        self.appeal_category = appeal_category

    @discord.ui.button(label="Accept Appeal", style=discord.ButtonStyle.success, custom_id="accept_appeal", emoji="✅")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions (Mod/Admin)
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Only moderators/admins can perform this action.", ephemeral=True)
            return

        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("Guild not found.", ephemeral=True)
            return

        try:
            user = await bot.fetch_user(self.user_id)
            action_done = ""
            
            if self.appeal_category == "MUTE":
                member = guild.get_member(self.user_id)
                if not member: member = await guild.fetch_member(self.user_id)
                
                muted_role = guild.get_role(MUTED_ROLE_ID)
                if member and muted_role:
                    await member.remove_roles(muted_role, reason=f"Mute Appeal Accepted by {interaction.user.name}")
                    action_done = "unmuted"
                else:
                    await interaction.response.send_message("Member or Muted Role not found.", ephemeral=True)
                    return
            else:
                # Default: Unban
                await guild.unban(user, reason=f"Ban Appeal Accepted by {interaction.user.name}")
                action_done = "unbanned"
            
            # Create invite link
            # Try to find a good channel for invite
            invite_channel = None
            for ch in guild.text_channels:
                if ch.permissions_for(guild.me).create_instant_invite:
                    invite_channel = ch
                    break
            
            invite_text = ""
            if invite_channel:
                invite = await invite_channel.create_invite(max_age=86400, max_uses=1, unique=True)
                invite_text = f" Here is your invite link to rejoin: {invite}"
            
            # DM user
            try:
                msg = f"✅ Your appeal for **{guild.name}** was **ACCEPTED**!\nYou have been {action_done}."
                if action_done == "unbanned":
                    msg += invite_text
                await user.send(msg)
            except:
                pass

            await interaction.response.send_message(f"✅ Appeal accepted. {user.name} has been {action_done} and notified.", ephemeral=False)
            
            # Update the original review message
            embed = interaction.message.embeds[0]
            embed.color = 0x00FF00
            embed.title = f"✅ Appeal Accepted ({self.appeal_category})"
            embed.description += f"\n\n**Outcome:** Accepted by {interaction.user.mention}"
            await interaction.message.edit(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Error accepting appeal: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

    @discord.ui.button(label="Decline Appeal", style=discord.ButtonStyle.danger, custom_id="decline_appeal", emoji="❌")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permissions
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("Only moderators/admins can perform this action.", ephemeral=True)
            return

        user = await bot.fetch_user(self.user_id)
        guild = bot.get_guild(self.guild_id)
        
        try:
            # DM user
            try:
                await user.send(f"❌ Your appeal for **{guild.name if guild else 'the server'}** was **DECLINED**.")
            except:
                pass

            await interaction.response.send_message(f"❌ Appeal declined for {user.name}.", ephemeral=False)
            
            # Update original message
            embed = interaction.message.embeds[0]
            embed.color = 0xFF0000
            embed.title = "❌ Appeal Declined"
            embed.description += f"\n\n**Outcome:** Declined by {interaction.user.mention}"
            await interaction.message.edit(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Error declining appeal: {e}")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)

class CaptchaModal(discord.ui.Modal, title='Verify You Are Human'):
    captcha_input = discord.ui.TextInput(
        label='Enter the code from the image',
        placeholder='Type captcha here...',
        min_length=6,
        max_length=6,
    )

    def __init__(self):
        super().__init__()

    async def on_submit(self, interaction: discord.Interaction):
        stored_code = active_captchas.get(interaction.user.id)
        if self.captcha_input.value.upper() == stored_code:
            # Captcha passed!
            guild = interaction.guild
            if not guild:
                await interaction.response.send_message("Server not found.", ephemeral=True)
                return
                
            member = interaction.user
            # Check account age
            acc_age_days = (datetime.now(timezone.utc) - member.created_at).days
            
            # Use improved role lookup
            verified_role = get_guild_role(guild, VERIFIED_ROLE_ID, "Verified")
            muted_role = get_guild_role(guild, MUTED_ROLE_ID, "Muted")
            unverified_role = get_guild_role(guild, UNVERIFIED_ROLE_ID, "Unverified")
            
            # 1. Remove Unverified role
            if unverified_role:
                try:
                    await member.remove_roles(unverified_role, reason="Passed Verification")
                    logger.info(f"Successfully REMOVED Unverified role from {member.name}")
                except Exception as e:
                    logger.error(f"Failed to remove unverified role from {member.name}: {e}")
                    # Optional: try searching by name again if ID failed
                    try:
                        alt_role = discord.utils.get(guild.roles, name="Unverified")
                        if alt_role:
                            await member.remove_roles(alt_role, reason="Passed Verification (Fallback)")
                    except: pass

            # 2. Give Verified role (allows seeing channels)
            if verified_role:
                try:
                    await member.add_roles(verified_role, reason="Passed Captcha Verification")
                except Exception as e:
                    logger.error(f"Failed to give verified role: {e}")
            
            if acc_age_days < VERIFICATION_AGE_THRESHOLD_DAYS:
                # Underage account -> Mute (Access but can't speak)
                if muted_role:
                    try:
                        await member.add_roles(muted_role, reason=f"Account Age ({acc_age_days}d) < 30d threshold")
                    except Exception as e:
                        logger.error(f"Failed to give muted role: {e}")
                
                view = AppealButtonView(guild.id, appeal_type="MUTE")
                await interaction.response.send_message(
                    f"✅ **Captcha Passed!**\n\n"
                    f"However, your account is only **{acc_age_days}** days old. "
                    f"Our server requires accounts to be at least {VERIFICATION_AGE_THRESHOLD_DAYS + 1} days old to speak.\n\n"
                    f"You have been granted access to view channels, but you will remain muted until your account age reaches the required threshold.\n\n"
                    f"If you believe this is a mistake, you can appeal below.",
                    view=view,
                    ephemeral=True
                )
            else:
                # Mature account -> Full Access
                await interaction.response.send_message("✅ **Verification Successful!** You now have full access to the server. Welcome!", ephemeral=True)
            
            # Clear captcha
            if interaction.user.id in active_captchas:
                del active_captchas[interaction.user.id]
                save_active_captchas(active_captchas)
        else:
            await interaction.response.send_message("❌ **Invalid Captcha.** Please try again.", ephemeral=True)

class VerifyButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Verify Myself", style=discord.ButtonStyle.success, custom_id="verify_start_btn", emoji="🛡️")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. Check if user is already verified (by ID or Name)
        is_verified = any(r.id == VERIFIED_ROLE_ID or r.name.lower() == "verified" for r in interaction.user.roles)
        if is_verified:
            await interaction.response.send_message("✅ You are already verified and have full access to the server!", ephemeral=True)
            return

        # 2. Generate captcha
        code, image_bytes = generate_captcha()
        active_captchas[interaction.user.id] = code
        save_active_captchas(active_captchas)
        
        file = discord.File(io.BytesIO(image_bytes), filename="captcha.png")
        
        # 3. Send ephemeral message
        await interaction.response.send_message(
            "Please solve this captcha to verify. Once you see the code, click **'Enter Code'** below.\n"
            "*Wait a moment for the image to load.*",
            file=file,
            view=CaptchaEntryView(),
            ephemeral=True
        )

class CaptchaEntryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Enter Code", style=discord.ButtonStyle.primary, custom_id="captcha_enter_btn", emoji="⌨️")
    async def enter_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        code = active_captchas.get(interaction.user.id)
        if not code:
            await interaction.response.send_message("❌ Captcha entry expired. Please click 'Verify Myself' again.", ephemeral=True)
            return
        await interaction.response.send_modal(CaptchaModal())

class SelfRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def handle_role(self, interaction: discord.Interaction, role_id: int, role_name: str):
        if role_id == 0:
            await interaction.response.send_message("This role has not been configured yet. Please contact an admin.", ephemeral=True)
            return

        role = interaction.guild.get_role(role_id)
        if not role:
            await interaction.response.send_message(f"Role '{role_name}' not found on this server.", ephemeral=True)
            return

        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            await interaction.response.send_message(f"✅ Removed the {role.mention} role.", ephemeral=True)
        else:
            await interaction.user.add_roles(role)
            await interaction.response.send_message(f"✅ Added the {role.mention} role.", ephemeral=True)

    @discord.ui.button(label="After Effects", style=discord.ButtonStyle.secondary, custom_id="role_ae", emoji=discord.PartialEmoji(name="ae", id=AE_EMOJI_ID))
    async def ae_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role(interaction, AE_ROLE_ID, "After Effects")

    @discord.ui.button(label="Alight Motion", style=discord.ButtonStyle.secondary, custom_id="role_am", emoji=discord.PartialEmoji(name="am", id=AM_EMOJI_ID))
    async def am_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role(interaction, AM_ROLE_ID, "Alight Motion")

    @discord.ui.button(label="Capcut", style=discord.ButtonStyle.secondary, custom_id="role_capcut", emoji=discord.PartialEmoji(name="capcut", id=CAPCUT_EMOJI_ID))
    async def capcut_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role(interaction, CAPCUT_ROLE_ID, "Capcut")

    @discord.ui.button(label="Other Software", style=discord.ButtonStyle.secondary, custom_id="role_other", emoji=discord.PartialEmoji(name="other", id=OTHER_EDIT_EMOJI_ID))
    async def other_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role(interaction, OTHER_EDIT_ROLE_ID, "Other Software")

    @discord.ui.button(label="Giveaway Pings", style=discord.ButtonStyle.secondary, custom_id="role_giveaway", emoji="🎉")
    async def giveaway_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_role(interaction, GIVEAWAY_ROLE_ID, "Giveaway Pings")

# Helper for Invidious API
async def fetch_invidious_stats(query):
    """Fetch channel stats from public Invidious instances."""
    instances = [
        "https://invidious.drgns.space",
        "https://invidious.fdn.fr",
        "https://invidious.jing.rocks",
        "https://inv.tux.pizza",
        "https://invidious.flokinet.to",
        "https://invidious.io.lol"
    ]
    
    # Clean query (remove URL parts if present)
    if "youtube.com/" in query:
        if "@" in query:
            query = query.split("@")[-1]
        elif "channel/" in query:
            query = query.split("channel/")[-1]
    
    clean_query = query.replace("https://", "").replace("www.", "").strip()
    
    async with aiohttp.ClientSession() as session:
        for instance in instances:
            try:
                # Search for channel
                url = f"{instance}/api/v1/search?q={clean_query}&type=channel"
                async with session.get(url, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and isinstance(data, list) and len(data) > 0:
                            # Find best match
                            channel = data[0] # First result usually best
                            title = channel.get("author", "Unknown")
                            subs = channel.get("subCount", 0)
                            videos = channel.get("videoCount", 0)
                            
                            # Format subs
                            if subs >= 1000000:
                                subs_text = f"{subs/1000000:.1f}M subscribers"
                            elif subs >= 1000:
                                subs_text = f"{subs/1000:.1f}K subscribers"
                            else:
                                subs_text = f"{subs} subscribers"
                                
                            logger.info(f"Fetched stats from {instance}: {title}, {subs_text}")
                            return subs_text, str(videos), title
            except Exception as e:
                logger.warning(f"Invidious {instance} failed: {e}")
                continue
    
    return "Unknown", "Unknown", "Unknown"

async def verify_youtube_proof(message, min_subs):
    """Verify YouTube screenshot and link using Gemini."""
    try:
        # Check for attachments
        if not message.attachments:
            return False, "No screenshot provided. Please send the screenshot and link together."
        
        # Check for link
        import re
        link_pattern = r'(https?://(?:www\.)?youtube\.com/(?:channel/|c/|user/|@)[\w-]+)'
        match = re.search(link_pattern, message.content)
        if not match:
            return False, "No YouTube channel link found. Please include your channel link."
        
        channel_link = match.group(0)
        
        # Download image
        attachment = message.attachments[0]
        if not any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
             return False, "Invalid file format. Please send a PNG or JPG screenshot."
             
        image_bytes = await download_image(attachment.url)
        if not image_bytes:
            return False, "Could not download image."
            
        # --- VERIFICATION STRATEGIES ---
        live_subs_text = "Unknown"
        video_count_text = "Unknown" 
        channel_title = "Unknown"
        
        # Strategy 0: Official YouTube Data API (100% Reliable)
        api_key = os.getenv("YOUTUBE_API_KEY")
        if api_key:
            try:
                # Extract identifier
                handle = None
                channel_id = None
                
                if "/@" in channel_link:
                    handle = channel_link.split("/@")[-1].split("/")[0]
                elif "/channel/" in channel_link:
                    channel_id = channel_link.split("/channel/")[-1].split("/")[0]
                
                if handle or channel_id:
                    api_url = "https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet"
                    
                    if handle:
                        api_url += f"&forHandle={handle}"
                    elif channel_id:
                        api_url += f"&id={channel_id}"
                    
                    api_url += f"&key={api_key}"
                    
                    async with aiohttp.ClientSession() as session:
                        async with session.get(api_url) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if "items" in data and len(data["items"]) > 0:
                                    item = data["items"][0]
                                    stats = item.get("statistics", {})
                                    snippet = item.get("snippet", {})
                                    
                                    channel_title = snippet.get("title", "Unknown")
                                    subs = int(stats.get("subscriberCount", 0))
                                    videos = int(stats.get("videoCount", 0))
                                    
                                    if subs >= 1000000:
                                        live_subs_text = f"{subs/1000000:.1f}M subscribers"
                                    elif subs >= 1000:
                                        live_subs_text = f"{subs/1000:.1f}K subscribers"
                                    else:
                                        live_subs_text = f"{subs} subscribers"
                                    video_count_text = str(videos)
                                    logger.info(f"API Success (Direct): {channel_title} has {live_subs_text}")
                                else:
                                    # Strategy 0.1: Search Fallback (if direct lookup failed)
                                    search_query = handle if handle else channel_id
                                    search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={search_query}&type=channel&maxResults=1&key={api_key}"
                                    async with session.get(search_url) as search_resp:
                                        if search_resp.status == 200:
                                            search_data = await search_resp.json()
                                            if "items" in search_data and len(search_data["items"]) > 0:
                                                found_id = search_data["items"][0]["snippet"]["channelId"]
                                                # Now get stats for THIS ID
                                                stats_url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id={found_id}&key={api_key}"
                                                async with session.get(stats_url) as stats_resp:
                                                    if stats_resp.status == 200:
                                                        stats_data = await stats_resp.json()
                                                        if "items" in stats_data and len(stats_data["items"]) > 0:
                                                            item = stats_data["items"][0]
                                                            stats = item.get("statistics", {})
                                                            snippet = item.get("snippet", {})
                                                            channel_title = snippet.get("title", "Unknown")
                                                            subs = int(stats.get("subscriberCount", 0))
                                                            videos = int(stats.get("videoCount", 0))
                                                            
                                                            if subs >= 1000000:
                                                                live_subs_text = f"{subs/1000000:.1f}M subscribers"
                                                            elif subs >= 1000:
                                                                live_subs_text = f"{subs/1000:.1f}K subscribers"
                                                            else:
                                                                live_subs_text = f"{subs} subscribers"
                                                            video_count_text = str(videos)
                                                            logger.info(f"API Success (Search): {channel_title} has {live_subs_text}")
            except Exception as e:
                logger.error(f"YouTube API failed: {e}")
            except Exception as e:
                logger.error(f"YouTube API failed: {e}")

        # Strategy 1: Direct Scrape (If API failed or not used)
        if live_subs_text == "Unknown":
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/137.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                }
                async with aiohttp.ClientSession() as session:
                    async with session.get(channel_link, headers=headers, timeout=5) as resp:
                        if resp.status != 200:
                            logger.warning(f"Could not scrape channel: {resp.status}")
                        else:
                            content = await resp.content.read(150000)
                            try:
                                channel_html_snippet = content.decode('utf-8', errors='ignore')
                                import re
                                
                                # 1. Title
                                title_match = re.search(r'<title>(.*?)</title>', channel_html_snippet)
                                if title_match:
                                    channel_title = title_match.group(1).replace("- YouTube", "").strip()

                                # 2. JSON Data (ytInitialData)
                                sub_match = re.search(r'\"subscriberCountText\":.*?\"simpleText\":\"([^\"]+)\"', channel_html_snippet)
                                if sub_match:
                                    live_subs_text = sub_match.group(1)
                                
                                # 3. Video Count
                                vid_match = re.search(r'\"videoCountText\":.*?\"simpleText\":\"([^\"]+)\"', channel_html_snippet)
                                if vid_match:
                                    video_count_text = vid_match.group(1)
                            except:
                                pass
            except Exception as e:
                logger.error(f"Failed to scrape YT channel direct: {e}")

        # Strategy 2: Invidious API (Fallback if still Unknown)
        if live_subs_text == "Unknown":
            logger.info("Direct scrape failed or skipped, trying Invidious API...")
            live_subs_text, video_count_text, channel_title = await fetch_invidious_stats(channel_link)

        # Analysis prompt with STRICT requirements
        prompt = f"""
        Analyze this screenshot of YouTube Studio/Channel AND the provided live data.
        
        User Claims: >= {min_subs} subscribers.
        
        LIVE DATA FETCHED:
        - Channel Name: "{channel_title}"
        - Subscribers: "{live_subs_text}"
        - Videos: "{video_count_text}"
        
        VERIFICATION TASK:
        1. **Screenshot Check**: Does the image show the subscriber count? Is it >= {min_subs}?
        2. **Match Check**: Does the Channel Name in the screenshot match "{channel_title}"?
        3. **Count Cross-Check**:
           - Does the screenshot subscriber count match "{live_subs_text}"?
           - Note: "{live_subs_text}" is the REAL live count from YouTube.
           - If Screenshot says 50K but Live says 100 -> REJECT (Fake).
           - If Screenshot says 50K and Live says "Unknown" -> Flag for Manual Review.
           - If Screenshot says 50K and Live says 50K -> VERIFY.
        
        Reply with strictly valid JSON format:
        {{
            "verified": true/false,
            "is_edited": true/false (true if screenshot contradicts live data or looks manipulated),
            "low_subs": true/false (true if they simply don't have enough subscribers),
            "manual_review_needed": true/false (true if scraping failed 'Unknown' and can't cross-check),
            "reason": "Explain simply. Mention the stats found."
        }}
        """
        
        response = gemini_client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt
            ]
        )
        
        # Parse JSON response
        response_text = response.text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
             response_text = response_text.split("```")[1].split("```")[0].strip()
        
        import json
        try:
             result = json.loads(response_text)
             if result:
                 # Include stats
                 result["live_subs"] = live_subs_text
                 result["video_count"] = video_count_text
                 result["channel_name"] = channel_title
        except:
             result = {"verified": False, "reason": "Failed to parse AI response.", "manual_review_needed": True}
        
        return result, None

    except Exception as e:
        logger.error(f"Error in YT verification: {e}")
        return {"verified": False, "reason": f"Error processing verification: {str(e)}", "manual_review_needed": True}, None

@bot.command(name="setup_content_roles")
@commands.has_permissions(administrator=True)
async def setup_content_roles(ctx):
    """(Admin) Send the Content Creator role verification message."""
    embed = discord.Embed(
        title="🎥 Content Creator Roles",
        description="Select a role to apply for verification:",
        color=0xFF0000
    )
    embed.add_field(name="YouTuber", value="Requires **10,000+** Subscribers", inline=False)
    embed.add_field(name="Legendary YouTuber", value="Requires **60,000+** Subscribers", inline=False)
    embed.set_footer(text="Powered by Gemini AI Verification")
    
    await ctx.send(embed=embed, view=RoleRequestView())
    try: await ctx.message.delete()
    except: pass
    logger.info(f"Content Creator roles setup triggered by {ctx.author.name} in {ctx.guild.name}")
    
@bot.command(name="setup_verification")
@commands.has_permissions(administrator=True)
async def setup_verification(ctx):
    """(Admin) Send the verification message to the current channel."""
    embed = discord.Embed(
        title="🛡️ Server Verification Required",
        description=(
            "🛡️ **Welcome to the Server!**\n\n"
            "To maintain a safe and bot-free community, we require all new members to complete a quick verification process.\n\n"
            "**How it Works:**\n"
            "1️⃣ Click the **'Verify Myself'** button below.\n"
            "2️⃣ A captcha image will appear (give it a second to load).\n"
            "3️⃣ Click **'Enter Code'** and type exactly what you see in the image.\n\n"
            "**Account Security:**\n"
            "• If your account is **older than 30 days**, you will get full access immediately.\n"
            "• If your account is **newer than 30 days**, you will be verified but remain **muted** until your account reaches the required age. This helps us prevent raids and spam.\n\n"
            "*Need help? Contact a moderator if the captcha doesn't load.*"
        ),
        color=0x00FF00
    )
    embed.set_footer(text="Verification enforcement enabled")
    
    view = VerifyButtonView()
    await ctx.send(embed=embed, view=view)
    await ctx.message.delete()
    logger.info(f"Verification setup triggered by {ctx.author.name} in {ctx.guild.name}")

@bot.command(name="setup_roles")
@commands.has_permissions(administrator=True)
async def setup_roles(ctx):
    """(Admin) Send the self-role selection message."""
    embed = discord.Embed(
        title="🎨 Editing Roles",
        description=(
            "React to the buttons below to assign yourself roles!\n\n"
            f"<:ae:{AE_EMOJI_ID}> — <@&{AE_ROLE_ID}>\n"
            f"<:am:{AM_EMOJI_ID}> — <@&{AM_ROLE_ID}>\n"
            f"<:capcut:{CAPCUT_EMOJI_ID}> — <@&{CAPCUT_ROLE_ID}>\n"
            f"<:other:{OTHER_EDIT_EMOJI_ID}> — <@&{OTHER_EDIT_ROLE_ID}>\n"
            f"🎉 — <@&{GIVEAWAY_ROLE_ID}>\n\n"
            "🚀 **Special Roles:**\n"
            f"If you are a content creator looking for <@&{YOUTUBER_ROLE_ID}> or <@&{LEGENDARY_ROLE_ID}> roles, please head over to <#{ROLE_REQUEST_CHANNEL_ID}> to verify your channel subscribers!"
        ),
        color=0x3498DB
    )
    embed.set_footer(text="Manage your roles at any time by clicking the buttons below.")
    
    await ctx.send(embed=embed, view=SelfRoleView())
    try: await ctx.message.delete()
    except: pass
    logger.info(f"Role selection setup triggered by {ctx.author.name} in {ctx.guild.name}")


@bot.event
async def on_ready():
    """Event triggered when the bot is ready and connected to Discord."""
    global log_channel
    
    logger.info(f'Bot connected as {bot.user.name} (ID: {bot.user.id})')
    logger.info(f'Connected to {len(bot.guilds)} server(s)')
    logger.info('=' * 50)
    logger.info('SERVERS YOUR BOT IS IN:')
    logger.info('=' * 50)
    for i, guild in enumerate(bot.guilds, 1):
        logger.info(f'  {i}. {guild.name} (ID: {guild.id}) - {guild.member_count} members')
    logger.info('=' * 50)
    logger.info('Bot is ready to receive commands!')
    
    # Initialize activity log channel
    if LOG_CHANNEL_ID:
        try:
            log_channel = bot.get_channel(int(LOG_CHANNEL_ID))
            if log_channel:
                logger.info(f'Activity log channel set to: #{log_channel.name}')
                # Send startup log
                server_list = "\n".join([f"• {g.name} ({g.member_count} members)" for g in bot.guilds])
                await log_activity(
                    "🟢 Bot Started",
                    f"**{bot.user.name}** is now online!",
                    color=0x00FF00,
                    fields={
                        "Servers": len(bot.guilds),
                        "Server List": server_list[:1024] if server_list else "None"
                    }
                )
            else:
                logger.warning(f'Could not find log channel with ID: {LOG_CHANNEL_ID}')
        except Exception as e:
            logger.error(f'Error setting up log channel: {e}')

    # Sync slash commands globally
    try:
        logger.info("Syncing slash commands globally...")
        synced = await bot.tree.sync()
        logger.info(f"Successfully synced {len(synced)} global slash commands.")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")

    # Start presence cycle
    async def cycle_presence():
        while True:
            for activity, status in PRESENCE_STATUSES:
                await bot.change_presence(activity=activity, status=status)
                await asyncio.sleep(30)

    bot.loop.create_task(cycle_presence())

    # AutoMod Setup for Badge (runs on startup)
    bot.loop.create_task(setup_all_guilds_automod())
    
    # Start account maturity check loop
    if not check_account_maturity.is_running():
        check_account_maturity.start()
        logger.info("Account maturity check loop started.")

    # Start chat revival loop
    if not revive_chat.is_running():
        revive_chat.start()
        logger.info("Chat revival loop started.")

    # Register persistent views
    bot.add_view(SelfRoleView())
    bot.add_view(RoleRequestView())
    bot.add_view(VerifyButtonView())
    bot.add_view(CaptchaEntryView())

async def setup_all_guilds_automod():
    """Automatically try to setup 6 rules in every guild the bot is in to help with Badge."""
    await bot.wait_until_ready()
    for guild in bot.guilds:
        await create_max_automod_rules(guild)

async def create_max_automod_rules(guild):
    """Creates up to 6 keyword rules and 1 spam rule in a guild."""
    try:
        # Check permissions
        if not guild.me.guild_permissions.manage_guild:
            logger.warning(f"Skipping AutoMod setup for {guild.name}: Missing 'Manage Server' permission.")
            return

        existing_rules = await guild.fetch_automod_rules()
        existing_names = [r.name for r in existing_rules]
        
        # Create 6 Keyword Rules
        created_count = 0
        for i in range(1, 7):
            rule_name = f"Prime Shield Alpha {i}"
            if rule_name not in existing_names:
                try:
                    # Use common spam/scam keywords for the rule to actually be useful
                    trigger = discord.AutoModTrigger(
                        type=discord.AutoModRuleTriggerType.keyword,
                        keyword_filter=[f"primescamtest{i}", "free nitro scam", "discord.gift scam"]
                    )
                    action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
                    await guild.create_automod_rule(
                        name=rule_name,
                        event_type=discord.AutoModRuleEventType.message_send,
                        trigger=trigger,
                        actions=[action],
                        enabled=True
                    )
                    created_count += 1
                except Exception as e:
                    if "MAX_RULES_OF_TYPE_EXCEEDED" in str(e):
                        break
                    logger.warning(f"Failed to create automod rule {i} in {guild.name}: {e}")

        # Create 1 Spam Rule if possible
        if "Prime Anti-Spam" not in existing_names:
            try:
                trigger = discord.AutoModTrigger(type=discord.AutoModRuleTriggerType.spam)
                action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
                await guild.create_automod_rule(
                    name="Prime Anti-Spam",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True
                )
                created_count += 1
            except: pass

        # Create 1 Mention Spam Rule
        if "Prime Anti-Mention" not in existing_names:
            try:
                trigger = discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.mention_spam,
                    mention_limit=10
                )
                action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
                await guild.create_automod_rule(
                    name="Prime Anti-Mention",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True
                )
                created_count += 1
            except: pass

        # Create 1 Profanity Rule (Keyword Preset)
        if "Prime Safety Filter" not in existing_names:
            try:
                trigger = discord.AutoModTrigger(
                    type=discord.AutoModRuleTriggerType.keyword_preset,
                    presets=[discord.AutoModRulePresetType.profanity, discord.AutoModRulePresetType.slurs]
                )
                action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
                await guild.create_automod_rule(
                    name="Prime Safety Filter",
                    event_type=discord.AutoModRuleEventType.message_send,
                    trigger=trigger,
                    actions=[action],
                    enabled=True
                )
                created_count += 1
            except: pass
        if created_count > 0:
            logger.info(f"Created {created_count} AutoMod rules in {guild.name}")
        return created_count
    except Exception as e:
        logger.error(f"Error in AutoMod rule creation for {guild.name}: {e}")
        return 0

@bot.command(name="check_automod")
@commands.is_owner()
async def check_automod_command(ctx):
    """Check why automod rules are not appearing."""
    guild = ctx.guild
    perms = guild.me.guild_permissions
    
    status_msg = f"🔍 **AutoMod Diagnostics for {guild.name}:**\n"
    status_msg += f"- Bot has 'Manage Server' permission: **{perms.manage_guild}**\n"
    status_msg += f"- Bot has 'Administrator' permission: **{perms.administrator}**\n"
    
    if not perms.manage_guild:
        status_msg += "❌ **Error**: The bot MUST have the 'Manage Server' permission to create rules.\n"
        await ctx.send(status_msg)
        return

    try:
        status_msg += "⏳ Attempting to create 1 test rule...\n"
        # Create a unique rule name to avoid conflicts
        rule_name = f"Prime Test {random.randint(100, 999)}"
        trigger = discord.AutoModTrigger(
            type=discord.AutoModRuleTriggerType.keyword,
            keyword_filter=["primediagnostic"]
        )
        action = discord.AutoModRuleAction(type=discord.AutoModRuleActionType.block_message)
        await guild.create_automod_rule(
            name=rule_name,
            event_type=discord.AutoModRuleEventType.message_send,
            trigger=trigger,
            actions=[action],
            enabled=True
        )
        status_msg += f"✅ **Success**: Rule '{rule_name}' created! Refresh your settings page.\n"
    except Exception as e:
        status_msg += f"❌ **Failed**: `{str(e)}`\n"
        if "MAX_RULES_OF_TYPE_EXCEEDED" in str(e):
            status_msg += "💡 *Tip: This server has reached the limit for Keyword rules. Delete some existing rules to make room.*"
    
    await ctx.send(status_msg)

@bot.event
async def on_guild_join(guild):
    """Track who added the bot when joining a new server and automatically setup AutoMod rules."""
    global guild_inviters
    logger.info(f'Bot joined new server: {guild.name} (ID: {guild.id})')
    
    inviter = None
    inviter_name = "Unknown"
    
    # Try to find who added the bot from audit logs
    try:
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
            if entry.target and entry.target.id == bot.user.id:
                inviter = entry.user
                inviter_name = inviter.name
                # Store the inviter
                guild_inviters[str(guild.id)] = inviter.id
                save_guild_inviters(guild_inviters)
                logger.info(f'Bot was added to {guild.name} by {inviter_name}')
                break
    except discord.Forbidden:
        logger.warning(f'No permission to view audit logs in {guild.name}')
        # Fall back to guild owner
        if guild.owner:
            guild_inviters[str(guild.id)] = guild.owner.id
            save_guild_inviters(guild_inviters)
            inviter_name = guild.owner.name
    except Exception as e:
        logger.error(f'Error checking audit logs: {e}')
    
    # Log the join activity
    await log_activity(
        "📥 Joined New Server",
        f"Bot has been added to **{guild.name}**",
        color=0x00FF00,
        fields={
            "Server": guild.name,
            "Server ID": guild.id,
            "Members": guild.member_count,
            "Added By": inviter_name,
            "Owner": guild.owner.name if guild.owner else "Unknown"
        }
    )
    
    # Automatically setup rules for the badge
    await create_max_automod_rules(guild)


@bot.event
async def on_member_join(member):
    """Handle new member arrival - start verification process."""
    if member.bot:
        return
        
    logger.info(f"New member joined: {member.name} ({member.id}) in {member.guild.name}")
    
    # 0. Assign Unverified Role (to hide channels)
    if UNVERIFIED_ROLE_ID:
        try:
            unverified_role = member.guild.get_role(UNVERIFIED_ROLE_ID)
            if unverified_role:
                await member.add_roles(unverified_role, reason="Newly joined - pending verification")
                logger.info(f"Assigned Unverified role to {member.name}")
        except Exception as e:
            logger.error(f"Failed to assign Unverified role: {e}")
    
    # 1. Send DM with Verification Button
    try:
        inviter_info = ""
        inviter_id = guild_inviters.get(str(member.guild.id))
        if inviter_id:
            inviter_user = bot.get_user(inviter_id)
            if inviter_user:
                inviter_info = f"This bot was added to the server by **{inviter_user.name}**.\n\n"

        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}! 👋",
            description=(
                f"To gain access to the server, you need to complete a quick verification.\n\n"
                f"{inviter_info}"
                "**Step 1:** Click the button below.\n"
                "**Step 2:** Solve the captcha challenge.\n"
                "**Step 3:** Click **'Enter Code'** and type exactly what you see in the image.\n\n"
                "*Note: If your account is newer than 30 days, you will be muted automatically until it reaches the required age.*"
            ),
            color=0x00FF00
        )
        embed.set_thumbnail(url=member.guild.icon.url if member.guild.icon else None)
        
        view = VerifyButtonView(member.guild.id)
        await member.send(embed=embed, view=view)
        logger.info(f"Sent verification DM to {member.name}")
    except Exception as e:
        logger.warning(f"Could not DM new member {member.name}: {e}")
        # Fallback: Mention in verification channel
        verif_channel = bot.get_channel(VERIFICATION_CHANNEL_ID)
        if verif_channel:
            await verif_channel.send(
                f"Welcome {member.mention}! I couldn't send you a DM (please check your privacy settings).\n"
                "Click the button below to solve the captcha and verify!",
                view=VerifyButtonView(member.guild.id)
            )

@bot.event
async def on_guild_join(guild):
    """Track who added the bot when joining a new server."""
    global guild_inviters
    logger.info(f'Bot joined new server: {guild.name} (ID: {guild.id})')
    
    inviter = None
    inviter_name = "Unknown"
    
    # Try to find who added the bot from audit logs
    try:
        async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.bot_add):
            if entry.target and entry.target.id == bot.user.id:
                inviter = entry.user
                inviter_name = inviter.name
                # Store the inviter
                guild_inviters[str(guild.id)] = inviter.id
                save_guild_inviters(guild_inviters)
                logger.info(f'Bot was added to {guild.name} by {inviter_name}')
                break
    except discord.Forbidden:
        logger.warning(f'No permission to view audit logs in {guild.name}')
        # Fall back to guild owner
        if guild.owner:
            guild_inviters[str(guild.id)] = guild.owner.id
            save_guild_inviters(guild_inviters)
            inviter_name = guild.owner.name
    except Exception as e:
        logger.error(f'Error checking audit logs: {e}')
    
    # Log the join activity
    await log_activity(
        "📥 Joined New Server",
        f"Bot has been added to **{guild.name}**",
        color=0x00FF00,
        fields={
            "Server": guild.name,
            "Server ID": guild.id,
            "Members": guild.member_count,
            "Added By": inviter_name,
            "Owner": guild.owner.name if guild.owner else "Unknown"
        }
    )

@bot.event
async def on_guild_remove(guild):
    """Log when the bot is removed from a server."""
    logger.info(f'Bot removed from server: {guild.name} (ID: {guild.id})')
    
    # Remove from inviters tracking
    guild_id_str = str(guild.id)
    if guild_id_str in guild_inviters:
        del guild_inviters[guild_id_str]
        save_guild_inviters(guild_inviters)
    
    await log_activity(
        "📤 Left Server",
        f"Bot was removed from **{guild.name}**",
        color=0xFF0000,
        fields={
            "Server": guild.name,
            "Server ID": guild.id
        }
    )

@bot.event
async def on_command_error(ctx, error):
    """Global error handler for bot commands."""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    if isinstance(error, commands.MissingRequiredArgument):
        return  # Ignore missing args
    if isinstance(error, commands.MissingPermissions):
        await ctx.reply(f"❌ You don't have permission to use this command! ({error})", delete_after=10)
        return
    logger.error(f'Command error in !{ctx.command}: {error}')
    await ctx.reply(f"❌ An error occurred: {str(error)}", delete_after=10)

@bot.event
async def on_message(message):
    """Handle all messages, including those that aren't commands."""
    # Ignore messages from the bot itself and other bots
    if message.author == bot.user or message.author.bot:
        return

    # REDIRECT EVERY MESSAGE TO LOG CHANNEL
    # Channel ID: 1456312201974644776
    try:
        log_chan_id = 1456312201974644776
        log_chan = bot.get_channel(log_chan_id)
        if log_chan:
            log_embed = discord.Embed(
                description=message.content[:4000] if message.content else "*(No text content)*",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc)
            )
            log_embed.set_author(name=f"{message.author} ({message.author.id})", icon_url=message.author.display_avatar.url)
            
            chan_name = message.channel.name if hasattr(message.channel, "name") else "DM"
            guild_name = message.guild.name if message.guild else "Direct Message"
            log_embed.set_footer(text=f"Server: {guild_name} | Channel: {chan_name}")
            
            if message.attachments:
                att_links = "\n".join([f"[{a.filename}]({a.url})" for a in message.attachments])
                log_embed.add_field(name="Attachments", value=att_links[:1024])
                # Show first image if present
                for a in message.attachments:
                    if any(a.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        log_embed.set_image(url=a.url)
                        break
            
            await log_chan.send(embed=log_embed)
    except Exception as e:
        logger.error(f"Error redirecting message to logging channel: {e}")
        
    # 0. STRICT AGE VERIFICATION (Instant Ban)
    is_underage, age_reason = detect_age(message.content)
    if is_underage:
        try:
            logger.warning(f"Underage detection triggered for {message.author.name}: {age_reason}")
            
            # DM User before banning
            try:
                view = AppealButtonView(message.guild.id)
                await message.author.send(
                    f"🚫 You have been **permanently banned** from **{message.guild.name}**.\n"
                    f"**Reason:** Discord requires all users to be at least 13 years old. ({age_reason})\n\n"
                    f"If you believe this was a mistake and you are actually 13+, you can appeal below.",
                    view=view
                )
            except:
                pass

            await message.guild.ban(message.author, reason=f"Underage User (COPPA/TOS): {age_reason}", delete_message_seconds=86400)
            await message.channel.send(f"🔨 **{message.author.mention}** has been BANNED. Reason: User is under 13.")
            return
        except Exception as e:
            logger.error(f"Failed to ban underage user {message.author.name}: {e}")
    
    # Check if user has a pending state (waiting for response to a question)
    user_id = message.author.id
    if user_id in user_states:
        state = user_states[user_id]
        logger.info(f"User {message.author.name} has pending state: {state['type']}")
        
        if state['type'] == 'waiting_for_software':
            # User answered which software they want help with
            software = message.content.strip()
            logger.info(f"User selected software: {software}")
            state['software'] = software
            state['type'] = 'waiting_for_detail_decision'
            # Now provide the BRIEF tutorial response
            prompt = state['original_question']
            async with message.channel.typing():
                response = get_gemini_response(prompt, user_id, username=message.author.name, is_tutorial=True, software=software, brief=True)
            logger.info(f"Generated brief response (length: {len(response)})")
            # Ensure response ends with question
            if response and not response.strip().endswith('?'):
                response = response.strip() + "\n\nWant a detailed step-by-step explanation?"
            # Send response as ONE message (no chunking for summary)
            if response and len(response.strip()) > 20:
                await message.reply(response)
                logger.info(f"Sent brief summary to {message.author.name}")
            else:
                logger.warning(f"Brief response too short: {response}")
                await message.reply("I had trouble generating a response. Please try again!")
            return

        elif state['type'] == 'waiting_for_appeal_explanation':
            # Handle ban/mute appeal explanation
            explanation = message.content.strip()
            guild_id = state['guild_id']
            appeal_category = state.get('appeal_category', 'BAN')
            guild = bot.get_guild(guild_id)
            
            # Send to appeal review channel
            review_channel = bot.get_channel(APPEAL_CHANNEL_ID)
            if review_channel:
                embed_title = "⚖️ New Ban Appeal Request" if appeal_category == "BAN" else "⚖️ New Mute Appeal Request"
                embed_color = 0xFFFF00 if appeal_category == "BAN" else 0x00A0FF
                
                embed = discord.Embed(
                    title=embed_title,
                    description=f"**User:** {message.author.name} ({message.author.id})\n"
                                f"**Server:** {guild.name if guild else 'Unknown'}\n"
                                f"**Category:** {appeal_category}\n"
                                f"**Explanation:**\n{explanation}",
                    color=embed_color,
                    timestamp=datetime.now(timezone.utc)
                )
                embed.set_thumbnail(url=message.author.display_avatar.url)
                
                view = AppealReviewView(user_id=message.author.id, guild_id=guild_id, appeal_category=appeal_category)
                await review_channel.send(embed=embed, view=view)
                
                await message.reply("✅ Your appeal has been submitted to the moderators for review. Please wait for a decision.")
            else:
                await message.reply("❌ Error: Appeal review channel not configured properly. Please contact an admin.")
            
            del user_states[user_id]
            return
        
        elif state['type'] == 'waiting_for_yt_verification':
            # Handle YouTube verification
            if message.content.lower().strip() == 'cancel':
                del user_states[user_id]
                await message.reply("Verification cancelled.")
                return

            async with message.channel.typing():
                result_data, _ = await verify_youtube_proof(message, state['min_subs'])
                
                is_verified = result_data.get("verified", False)
                is_edited = result_data.get("is_edited", False)
                manual_review = result_data.get("manual_review_needed", False)
                reason = result_data.get("reason", "Verification failed.")

                if manual_review:
                     admin_role = discord.utils.find(lambda r: "admin" in r.name.lower(), message.guild.roles)
                     admin_ping = admin_role.mention if admin_role else "@Admin"
                     
                     # Get clearer reason
                     channel_info = result_data.get("channel_name", "Unknown")
                     scraped_subs = result_data.get("live_subs", "Unknown")
                     
                     err_msg = f"⚠️ **Manual Verification Required**\n{admin_ping} please review.\n"
                     err_msg += f"**Reason:** {reason}\n"
                     err_msg += f"**Bot Found:** Channel: `{channel_info}` | Subs: `{scraped_subs}`"
                     
                     await message.reply(err_msg)
                     del user_states[user_id]
                     return

                # Prepare final message(s) to delete
                final_response = None
                
                if is_verified:
                    role_id = state['role_id']
                    role = message.guild.get_role(role_id)
                    if role:
                        try:
                            await message.author.add_roles(role, reason="YouTube Verification Successful")
                            
                            # Get stats from result
                            channel_name = result_data.get("channel_name", "Unknown")
                            subs_count = result_data.get("live_subs", "Unknown")
                            video_count = result_data.get("video_count", "Unknown")
                            
                            embed = discord.Embed(
                                title="✅ Verification Successful!",
                                color=0x00FF00
                            )
                            privacy_suffix = f"\n\n🗑️ *Privacy Mode: This interaction will be deleted in 60s.*" if message.channel.id == ROLE_REQUEST_CHANNEL_ID else ""
                            embed.description = f"{role.mention} role has been granted to {message.author.mention}.{privacy_suffix}"
                            embed.add_field(name="📺 Channel", value=channel_name, inline=True)
                            embed.add_field(name="👥 Subscribers", value=subs_count, inline=True)
                            embed.add_field(name="🎥 Videos", value=video_count, inline=True)
                            embed.set_thumbnail(url=message.author.display_avatar.url)
                            
                            final_response = await message.reply(embed=embed)
                            
                            # Log success
                            try:
                                await log_activity(
                                    "🎥 Role Granted",
                                    f"{message.author.mention} verified as **{state['role_name']}**\nChannel: {channel_name} | Subs: {subs_count}",
                                    color=0x00FF00
                                )
                            except:
                                pass
                        except Exception as e:
                            logger.error(f"Failed to add role {role.name}: {e}")
                            privacy_suffix = f"\n\n🗑️ *Privacy Mode: This will be deleted in 60s.*" if message.channel.id == ROLE_REQUEST_CHANNEL_ID else ""
                            final_response = await message.reply(f"✅ Verified, but I couldn't add the role due to a permission error. Please contact an admin.{privacy_suffix}")
                    else:
                        privacy_suffix = f"\n\n🗑️ *Privacy Mode: This will be deleted in 60s.*" if message.channel.id == ROLE_REQUEST_CHANNEL_ID else ""
                        final_response = await message.reply(f"✅ Verified! (Role not found, please contact admin).{privacy_suffix}")
                else:
                    # Rejected - Set 12h cooldown
                    cooldown_expiry = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
                    yt_cooldowns[str(user_id)] = cooldown_expiry
                    save_yt_cooldowns(yt_cooldowns)

                    low_subs = result_data.get("low_subs", False)
                    rejection_text = ""

                    if is_edited: # Fake or suspicious
                        rejection_text = f"❌ **Verification Rejected**\n**Reason:** {reason}\n*Note: Attempting to deceive the verification system is not allowed. A warning has been issued.*"
                        await warn_user(message.author, message.guild, f"YouTube Verification Fraud: {reason}")
                    elif low_subs: # Just not enough subs
                        rejection_text = f"Thank you for your interest! Unfortunately, your channel does not currently meet the required subscriber count for the **{state['role_name']}** role. Keep growing and try again later! 😊\n\n**Note:** {reason}\n*You can try again in 12 hours.*"
                    else: # Other logic fail (wrong link, etc)
                        if "wrong channel" in reason.lower() or "suspicious" in reason.lower():
                             rejection_text = f"❌ **Verification Rejected**\n**Reason:** {reason}\n*A warning has been issued for providing suspicious/incorrect information.*"
                             await warn_user(message.author, message.guild, f"Suspicious YouTuber Verification: {reason}")
                        else:
                             rejection_text = f"❌ **Verification Failed**\n**Reason:** {reason}\n*You can try again in 12 hours.*"
                    
                    privacy_suffix = f"\n\n🗑️ *Privacy Mode: This interaction will be deleted in 60s.*" if message.channel.id == ROLE_REQUEST_CHANNEL_ID else ""
                    final_response = await message.reply(f"{rejection_text}{privacy_suffix}")
                
                if final_response and message.channel.id == ROLE_REQUEST_CHANNEL_ID:
                    logger.info(f"Starting 60s privacy deletion for message in verification channel {message.channel.id}")
                    # Async Privacy Deletion Task (Only for Role Request Channel)
                    async def delete_after_countdown(bot_msg, user_msg):
                        try:
                            seconds_left = 60
                            while seconds_left > 0:
                                await asyncio.sleep(10)
                                seconds_left -= 10
                                if seconds_left <= 0: break
                                
                                # Update countdown in message
                                try:
                                    content_suffix = f"\n\n🗑️ *Privacy Mode: Deleting in {seconds_left}s...*"
                                    if bot_msg.embeds:
                                        embed = bot_msg.embeds[0]
                                        # Update description to reflect new time
                                        new_desc = embed.description.split("🗑️")[0] + content_suffix
                                        embed.description = new_desc
                                        await bot_msg.edit(embed=embed)
                                    else:
                                        new_content = bot_msg.content.split("🗑️")[0] + content_suffix
                                        await bot_msg.edit(content=new_content)
                                except:
                                    break # Message might be gone already
                            
                            # Final deletion
                            try: await user_msg.delete() 
                            except: pass
                            try: await bot_msg.delete()
                            except: pass
                        except Exception as e:
                            logger.error(f"Error in privacy deletion: {e}")

                    bot.loop.create_task(delete_after_countdown(final_response, message))
                elif final_response:
                    # If in DM or other channel, remove the privacy mode disclaimer
                    try:
                        if final_response.embeds:
                            embed = final_response.embeds[0]
                            embed.description = embed.description.split("🗑️")[0].strip()
                            await final_response.edit(embed=embed)
                        else:
                            new_content = final_response.content.split("🗑️")[0].strip()
                            await final_response.edit(content=new_content)
                    except:
                        pass
            
            # Clear state
            del user_states[user_id]
            return

        elif state['type'] == 'waiting_for_detail_decision':
            # User answered if they want detailed explanation
            user_message = message.content.lower().strip()
            software = state['software']
            prompt = state['original_question']
            logger.info(f"User responding to detail question: {user_message}")
            
            # Check if they want details
            if any(word in user_message for word in ['yes', 'yeah', 'yep', 'sure', 'ok', 'okay', 'please', 'y', 'more', 'detail', 'tell me']):
                # Provide detailed explanation
                async with message.channel.typing():
                    response = get_gemini_response(prompt, user_id, username=message.author.name, is_tutorial=True, software=software, brief=False)
                logger.info(f"Generated detailed response (length: {len(response)})")
                # Try to send as one message if under Discord limit
                if len(response) <= 1900:
                    await message.reply(response)
                    logger.info(f"Sent detailed explanation as single message")
                else:
                    # If too long, split into chunks but minimize number of messages
                    chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                    logger.info(f"Splitting detailed response into {len(chunks)} messages")
                    for chunk in chunks:
                        await message.reply(chunk)
            else:
                # User doesn't want details, just confirm
                logger.info(f"User declined detailed explanation")
                await message.reply("Got it! Let me know if you need help with anything else! 👍")
            
            # Clean up state after response
            del user_states[user_id]
            logger.info(f"Cleaned up state for {message.author.name}")
            return
    
    # Ignore messages that are replies to other users (not the bot)
    if message.reference:
        try:
            referenced_msg = await message.channel.fetch_message(message.reference.message_id)
            # If the reply is to someone other than the bot, ignore it
            if referenced_msg.author != bot.user:
                return
        except:
            pass  # If we can't fetch the message, continue normally

    # Check for profanity and moderate (delete + warn + mute 24h)
    if await moderate_profanity(message):
        return
    
    # Check images/videos for inappropriate content
    if await moderate_media(message):
        return
    
    # Check for spam and moderate
    await check_and_moderate_spam(message)
    
    # Check server security (invites, suspicious behavior)
    await check_server_security(message)
    
    # Process commands first and stop if it's a command
    await bot.process_commands(message)
    ctx = await bot.get_context(message)
    if ctx.valid:
        return
    
    # Check if bot was mentioned or if this is a DM
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mentioned = bot.user.mentioned_in(message)
    is_reply_to_bot = False
    if message.reference:
        try:
            referenced_msg = await message.channel.fetch_message(message.reference.message_id)
            is_reply_to_bot = referenced_msg.author == bot.user
        except:
            pass
    
    # Only respond if mentioned, in DM, or replying to bot
    if not is_dm and not is_mentioned and not is_reply_to_bot:
        return

    # If the message doesn't start with a command prefix, treat it as a chat message
    if not message.content.startswith('!'):
        prompt_lower = message.content.lower()
        
        # *** IMAGE GENERATION - PRIORITY #1 ***
        if ('generat' in prompt_lower or 'creat' in prompt_lower or 'draw' in prompt_lower or 'make' in prompt_lower) and ('img' in prompt_lower or 'image' in prompt_lower or 'picture' in prompt_lower or 'photo' in prompt_lower or 'art' in prompt_lower):
            prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
            await message.channel.send("🎨 Generating image...")
            try:
                image_path = await generate_image(prompt)
                if image_path and os.path.exists(image_path):
                    await message.channel.send(f"{message.author.mention}, here's your image:", file=discord.File(image_path))
                    return
            except Exception as e:
                logger.error(f"Image error: {str(e)}")
            await message.reply("❌ Image generation failed!")
            return
        
        # *** IMAGE SEARCH - PRIORITY #2 ***
        search_words = ['gimme', 'give me', 'send me', 'get me', 'find me', 'show me', 'find', 'search']
        image_keywords = ['png', 'jpg', 'jpeg', 'image', 'img', 'picture', 'photo', 'gif', 'webp']
        
        has_search_word = any(w in prompt_lower for w in search_words)
        has_image_keyword = any(w in prompt_lower for w in image_keywords)
        
        if has_search_word and has_image_keyword:
            # Extract search query
            search_query = None
            for word in ['gimme', 'give', 'send', 'get', 'find', 'show', 'search']:
                if word in prompt_lower:
                    idx = prompt_lower.find(word)
                    rest = prompt_lower[idx + len(word):].strip()
                    # Remove "me" if present
                    if rest.startswith('me'):
                        rest = rest[2:].strip()
                    if rest:
                        search_query = rest
                        break
            
            if search_query:
                await message.channel.send("🔍 Searching for images...")
                try:
                    image_path = await search_and_download_image(search_query, limit=1)
                    if image_path and os.path.exists(image_path):
                        await message.channel.send(f"{message.author.mention}, here's your **{search_query}**:", file=discord.File(image_path))
                        return
                except Exception as e:
                    logger.error(f"Image search error: {str(e)}")
                await message.reply(f"❌ Couldn't find images for '{search_query}'")
                return
        
        # NOW handle other messages
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_dm_message = is_dm
        is_mentioned = bot.user.mentioned_in(message)
        
        # Check if this is about tutorials - if so, ask which software FIRST
        is_help = any(word in prompt_lower for word in ['help', 'tutorial', 'how to', 'teach', 'guide', 'learn', 'explain', 'show me', 'assist', 'how do i', 'how can i', 'how do you', 'create', 'make', 'do', 'show me'])
        is_editing_help = is_help and any(keyword in prompt_lower for keyword in ['edit', 'effect', 'render', 'color', 'grade', 'video', 'after effects', 'premiere', 'photoshop', 'resolve', 'capcut', 'topaz', 'cc', 'grading', 'correction', 'effects', 'transition', 'animation', 'vfx', 'motion'])
        
        # PRIORITY: If this is editing help, ALWAYS ask which software FIRST before generating anything
        if is_editing_help:
            # Check if they already have a pending state
            if user_id not in user_states or user_states[user_id]['type'] != 'waiting_for_software':
                # NEW: Detect if software is already mentioned to skip the question
                softwares = {
                    'after effects': 'After Effects', 'ae': 'After Effects', 'afterffeffects': 'After Effects',
                    'premiere': 'Premiere Pro', 'pr': 'Premiere Pro',
                    'photoshop': 'Photoshop', 'ps': 'Photoshop',
                    'resolve': 'DaVinci Resolve', 'davinci': 'DaVinci Resolve',
                    'capcut': 'CapCut', 'topaz': 'Topaz',
                    'final cut': 'Final Cut Pro', 'fcp': 'Final Cut Pro',
                    'alight motion': 'Alight Motion', 'am': 'Alight Motion'
                }
                
                mentioned_software = None
                for kw, name in softwares.items():
                    if re.search(r'\b' + re.escape(kw) + r'\b', prompt_lower):
                        mentioned_software = name
                        break
                
                if mentioned_software:
                    logger.info(f"Software '{mentioned_software}' already mentioned by {message.author.name}, skipping question.")
                    user_states[user_id] = {
                        'type': 'waiting_for_detail_decision', 
                        'original_question': prompt_lower,
                        'software': mentioned_software
                    }
                    async with message.channel.typing():
                        response = get_gemini_response(prompt_lower, user_id, username=message.author.name, is_tutorial=True, software=mentioned_software, brief=True)
                    
                    if response and not response.strip().endswith('?'):
                        response = response.strip() + "\n\nWant a detailed step-by-step explanation?"
                    
                    if response and len(response.strip()) > 20:
                        await message.reply(response)
                        logger.info(f"Sent direct tutorial to {message.author.name}")
                    else:
                        await message.reply("Which software would you like help with? (After Effects, Premiere, Photoshop, DaVinci Resolve, Final Cut Pro, Topaz, CapCut, or something else?)")
                        user_states[user_id] = {'type': 'waiting_for_software', 'original_question': prompt_lower}
                    return
                else:
                    logger.info(f"Editing help detected for {message.author.name}, asking for software")
                    await message.reply("Which software would you like help with? (After Effects, Premiere, Photoshop, DaVinci Resolve, Final Cut Pro, Topaz, CapCut, or something else?)")
                    user_states[user_id] = {'type': 'waiting_for_software', 'original_question': prompt_lower}
            return
        
        # If editing help detected but NOT mentioned (regular chat context), just continue to normal chat handling
        # Don't treat it as tutorial, just normal response
        
        # Check if user is asking for an image or video
        is_image_request = any(keyword in prompt_lower for keyword in ['send me', 'get me', 'find me', 'show me', 'give me', 'image', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'picture', 'photo', 'screenshot'])
        search_query = None
        if is_image_request:
            # Try to extract what they want
            if 'send me' in prompt_lower or 'get me' in prompt_lower or 'find me' in prompt_lower or 'show me' in prompt_lower or 'give me' in prompt_lower:
                parts = message.content.split()
                for i, part in enumerate(parts):
                    if part.lower() in ['send', 'get', 'find', 'show', 'give']:
                        if i+1 < len(parts) and parts[i+1].lower() == 'me':
                            search_query = ' '.join(parts[i+2:]) if i+2 < len(parts) else None
                            break
        
        try:
            # Get clean prompt (remove mention if exists)
            prompt = message.content.replace(f'<@{bot.user.id}>', '').strip()
            
            # Check for attachments (images or videos)
            image_bytes = None
            video_bytes = None
            is_video = False
            video_filename = None
            
            if message.attachments:
                for attachment in message.attachments:
                    filename_lower = attachment.filename.lower()
                    
                    # Check if attachment is an image
                    if any(filename_lower.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        logger.info(f'Downloading image from {message.author.name}: {attachment.filename}')
                        image_bytes = await download_image(attachment.url)
                        if image_bytes:
                            break
                    
                    # Check if attachment is a video (but reject .mov files)
                    elif any(filename_lower.endswith(ext) for ext in ['.mp4', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v']):
                        logger.info(f'Downloading video from {message.author.name}: {attachment.filename}')
                        video_bytes, error = await download_video(attachment.url, attachment.filename)
                        if error:
                            await message.reply(f"❌ {error}")
                            return
                        if video_bytes:
                            is_video = True
                            video_filename = attachment.filename
                            break
                    
                    # Reject .mov files
                    elif filename_lower.endswith('.mov'):
                        await message.reply("❌ MOV files are not supported. Please use MP4, AVI, MKV, WebM, or other video formats.")
                        return
            
            # If there's content to process
            if not image_bytes and not video_bytes and not prompt:
                return
            
            # Show typing indicator while processing
            async with message.channel.typing():
                if is_image_request and search_query and not image_bytes and not video_bytes:
                    # Search and download image
                    image_path = await search_and_download_image(search_query, limit=1)
                    if image_path and os.path.exists(image_path):
                        try:
                            # Send the image to user's DMs
                            await message.author.send(f"Here's a **{search_query}** for you:", 
                                                    file=discord.File(image_path))
                            if message.guild:
                                await message.channel.send(f"{message.author.mention}, I've sent you the image in your DMs!")
                            logger.info(f'Sent image for "{search_query}" to {message.author.name}')
                            return
                        except Exception as e:
                            logger.error(f"Error sending image: {str(e)}")
                            await message.reply(f"❌ Couldn't send the image. Error: {str(e)}")
                            return
                    else:
                        await message.reply(f"❌ Couldn't find an image for '{search_query}'. Try a different search term!")
                        return
                elif is_video and video_bytes:
                    # Analyze video
                    response = await analyze_video(video_bytes, video_filename, message.author.id)
                elif image_bytes:
                    # Analyze image
                    response = get_gemini_response(prompt, message.author.id, username=message.author.name, image_bytes=image_bytes)
                else:
                    # Regular text response
                    response = get_gemini_response(prompt, message.author.id, username=message.author.name, image_bytes=None)
            
            # Split response if it's too long for Discord (2000 char limit)
            if len(response) > 1900:
                # Split into chunks
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                for chunk in chunks:
                    if is_dm:
                        await message.channel.send(chunk)
                    else:
                        await message.reply(chunk)
            else:
                if is_dm:
                    await message.channel.send(response)
                else:
                    await message.reply(response)

            logger.info(f'Responded to {message.author.name}' + (' (video analysis)' if is_video else ' (image analysis)' if image_bytes else ''))
            
            # Log the chat activity
            response_type = "Video Analysis" if is_video else "Image Analysis" if image_bytes else "Chat Response"
            server_name = message.guild.name if message.guild else "DM"
            await log_activity(
                f"💬 {response_type}",
                f"Responded to **{message.author.name}**",
                color=0x5865F2,
                fields={
                    "User": message.author.name,
                    "Server": server_name,
                    "Channel": message.channel.name if hasattr(message.channel, 'name') else "DM",
                    "Query": prompt[:100] + "..." if len(prompt) > 100 else prompt if prompt else "N/A"
                }
            )

        except Exception as e:
            logger.error(f'Error in chat response: {str(e)}')

@bot.command(name="help", aliases=["commands", "cmds"])
async def help_command(ctx):
    """Show all available commands"""
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked help command')

    embed = discord.Embed(
        title="🤖 PRIME BOT - COMMANDS",
        description="Here is the list of all available commands for you to explore.",
        color=0x3498DB
    )
    
    embed.add_field(name="📋 General", value="`!help`, `!files`, `!presets`, `!software_list`, `!profile`", inline=False)
    embed.add_field(name="📈 Leveling", value="`!level`, `!leaderboard`, `!rank`", inline=False)
    embed.add_field(name="💻 Software", value="`!aecrack`, `!pscrack`, `!mecrack`, `!prcrack`, `!topazcrack`", inline=False)
    embed.add_field(name="📝 AI Editing / Tools", value="`!ask`, `!prime`, `!explain`, `!improve`, `!rewrite`, `!summarize`, `!analyze`, `!idea`, `!define`, `!fix`, `!shorten`, `!expand`, `!caption`, `!script`, `!format`, `!title`, `!translate`, `!paragraph`", inline=False)
    embed.add_field(name="🛠️ Utilities", value="`!remind`, `!note`, `!timer`, `!calculate`, `!weather`, `!serverinfo`", inline=False)
    embed.add_field(name="🎨 Creative", value="`!creative`, `!story`, `!quote`, `!brainstorm`, `!design`, `!name`, `!aesthetic`, `!topics`, `!motivate`", inline=False)
    
    embed.set_footer(text="Prime AI • Developed by BMR")
    
    try:
        await ctx.author.send(embed=embed)
        if ctx.guild:
            await ctx.send("📬 I've sent the command list to your DMs!", delete_after=10)
    except discord.Forbidden:
        await ctx.send("❌ I couldn't DM you! Please enable your DMs.")

@bot.command(name="level", aliases=["rank"])
async def level_command(ctx, member: discord.Member = None):
    """Check your current level and XP. Usage: !level [@user]"""
    member = member or ctx.author
    user_id = member.id
    
    if user_id not in user_levels:
        await ctx.send(f"📊 **{member.display_name}** hasn't started their journey yet! (Level 0, 0 XP)")
        return
        
    data = user_levels[user_id]
    xp = data["xp"]
    level = data["level"]
    next_level_xp = 100 * (level + 1) ** 2
    xp_to_next = next_level_xp - xp
    
    embed = discord.Embed(
        title=f"📊 {member.display_name}'s Level info",
        color=0x3498DB
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="Total XP", value=str(xp), inline=True)
    embed.add_field(name="XP to Next Level", value=f"{xp_to_next} / {next_level_xp}", inline=False)
    
    # Progress bar
    bar_length = 20
    progress = min(xp / next_level_xp, 1.0)
    filled = int(progress * bar_length)
    bar = "█" * filled + "░" * (bar_length - filled)
    
    embed.add_field(name="Progress", value=f"`{bar}` {int(progress * 100)}%", inline=False)
    embed.set_footer(text="Keep chatting to earn more!")
    
    await ctx.send(embed=embed)

@bot.command(name="leaderboard", aliases=["top", "lb"])
async def leaderboard_command(ctx):
    """Show the top 10 users with the most XP."""
    if not user_levels:
        await ctx.send("The leaderboard is currently empty!")
        return
        
    # Sort users by XP descending
    sorted_users = sorted(user_levels.items(), key=lambda x: x[1]["xp"], reverse=True)
    
    embed = discord.Embed(
        title="🏆 XP LEADERBOARD",
        description="Top 10 most active users in the server!",
        color=0xF1C40F
    )
    
    lb_text = ""
    for i, (uid, data) in enumerate(sorted_users[:10], 1):
        user = bot.get_user(uid)
        user_name = user.name if user else f"User {uid}"
        lb_text += f"**#{i}** | {user_name} - **Level {data['level']}** ({data['xp']} XP)\n"
        
    embed.description = lb_text or "No data available."
    embed.set_footer(text="Prime Leveling System")
    await ctx.send(embed=embed)
async def list_files_command(ctx):
    """
    Lists all available files that can be requested.
    Usage: !files
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !files command in {ctx.guild.name if ctx.guild else "DM"}')

    # Get list of files in the files directory
    files_dir = "files"
    if not os.path.exists(files_dir):
        await ctx.send("No files available currently.")
        return

    # Get all files in the directory
    all_files = []
    for file in glob.glob(f"{files_dir}/*"):
        if os.path.isfile(file):
            filename = os.path.basename(file)
            command_name = os.path.splitext(filename)[0]
            all_files.append(f"!{command_name} - {filename}")

    if not all_files:
        await ctx.send("No files available currently.")
        return

    # Format the file list
    all_files.sort()  # Sort alphabetically
    file_list = "\n".join(all_files)
    response = f"**Available Files:**\n```\n{file_list}\n```\nType the command (e.g., !foggy_cc) to receive the file in your DMs."

    try:
        # Send the list to the user's DMs
        await ctx.author.send(response)
        logger.info(f'Sent file list to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the list of available files in your DMs!")

    except discord.Forbidden:
        # If DMs are closed, send in the channel
        logger.warning(f'Could not send file list to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Here's the list of files:")
        await ctx.send(response)

    except Exception as e:
        logger.error(f'Error sending file list to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the file list.")

@bot.command(name="software_list")
async def software_list_command(ctx):
    """
    Lists all available software-related commands.
    Usage: !software_list
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !software_list command in {ctx.guild.name if ctx.guild else "DM"}')

    # Prepare the software command list
    software_list = [
        "**Software Commands:**",
        "!aecrack - Adobe After Effects crack information",
        "!pscrack - Adobe Photoshop crack information",
        "!mecrack - Adobe Media Encoder crack information",
        "!prcrack - Adobe Premiere Pro crack information",
        "!topazcrack - Topaz Suite crack information"
    ]

    # Format the final response
    response = "\n".join(software_list)

    try:
        # Send the list to the user's DMs
        await ctx.author.send(response)
        logger.info(f'Sent software list to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the list of software commands in your DMs!")

    except discord.Forbidden:
        # If DMs are closed, send in the channel
        logger.warning(f'Could not send software list to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Here's the list of software commands:")
        await ctx.send(response)

    except Exception as e:
        logger.error(f'Error sending software list to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the software list.")

@bot.command(name="presets")
async def presets_command(ctx):
    """
    Lists all available .ffx presets (color correction files).
    Usage: !presets
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !presets command in {ctx.guild.name if ctx.guild else "DM"}')

    # Get list of .ffx files in the files directory
    files_dir = "files"
    if not os.path.exists(files_dir):
        await ctx.send("No presets available currently.")
        return

    # Get all .ffx files in the directory
    ffx_files = []
    for file in glob.glob(f"{files_dir}/*.ffx"):
        if os.path.isfile(file):
            filename = os.path.basename(file)
            command_name = os.path.splitext(filename)[0]
            ffx_files.append(f"!{command_name} - {filename}")

    if not ffx_files:
        await ctx.send("No presets available currently.")
        return

    # Format the file list
    ffx_files.sort()  # Sort alphabetically
    file_list = "\n".join(ffx_files)
    response = f"**Available Color Correction Presets:**\n```\n{file_list}\n```\nType the command (e.g., !foggy_cc) to receive the preset in your DMs."

    try:
        # Send the list to the user's DMs
        await ctx.author.send(response)
        logger.info(f'Sent preset list to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the list of available presets in your DMs!")

    except discord.Forbidden:
        # If DMs are closed, send in the channel
        logger.warning(f'Could not send preset list to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Here's the list of presets:")
        await ctx.send(response)

    except Exception as e:
        logger.error(f'Error sending preset list to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the preset list.")

@bot.command(name="aecrack")
async def aecrack_command(ctx):
    """
    Sends information about Adobe After Effects crack.
    Usage: !aecrack
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !aecrack command in {ctx.guild.name if ctx.guild else "DM"}')

    # Actual Adobe After Effects crack information
    response = """**Adobe After Effects Crack Links**

# [2025 (v25.1)](<https://notabin.com/?fb7cab495eecf221#FiT2GfKpydCLgzWGKUv8jHVdMB8dn2YqDoi6E17qEa7F>)

# [2024 (v24.6.2)](<https://paste.to/?d06e0c5b7a227356#DoWsXVNiFCvYpxZdvE793tu8jnxmq66bxw3k4WpuLA63>)

# [2022 (v22.6)](<https://paste.to/?2de1e37edd288c59#HKgmUNUEfKG4z3ZrQ6pGxcqiroeHcZqS7AxuEqScHv2t>)

# [2020 (v17.7)](<https://paste.to/?4c06b2d0730e4b4e#BwAWrNgK633RtYnzGB25us53Z6pMN4QzocRY9MNoFCeU>)

**Installation:**

_1) Mount the ISO._
_2) Run autoplay.exe._

**Note:**

_Cloud-based functionality will not work for this crack. You must ensure to block internet connections to the app in case of unlicensed errors._"""

    try:
        # Send DM to the user
        await ctx.author.send(response)
        logger.info(f'Successfully sent AE crack info to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the After Effects crack information in your DMs!")

    except discord.Forbidden:
        logger.warning(f'Could not send AE crack info to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending AE crack info to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the information.")

@bot.command(name="pscrack")
async def pscrack_command(ctx):
    """
    Sends information about Adobe Photoshop crack.
    Usage: !pscrack
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !pscrack command in {ctx.guild.name if ctx.guild else "DM"}')

    # Actual Adobe Photoshop crack information
    response = """**Adobe Photoshop Crack Information**

# [PHOTOSHOP 2025](<https://hidan.sh/tfbctrj9jn54i>) 

# INSTALLATION

1) Mount the ISO.
2) Run autoplay.exe.

**Note:**

Cloud-based functionality will not work for this crack. You must ensure to block internet connections to the app in case of unlicensed errors.

Ensure to use uBlock Origin. The file should be the size and format stated."""

    try:
        # Send DM to the user
        await ctx.author.send(response)
        logger.info(f'Successfully sent PS crack info to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the Photoshop crack information in your DMs!")

    except discord.Forbidden:
        logger.warning(f'Could not send PS crack info to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending PS crack info to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the information.")

@bot.command(name="mecrack")
async def mecrack_command(ctx):
    """
    Sends information about Media Encoder crack.
    Usage: !mecrack
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !mecrack command in {ctx.guild.name if ctx.guild else "DM"}')

    # Actual Media Encoder crack information
    response = """**Media Encoder Crack Information**

# [MEDIA ENCODER 2025](<https://hidan.sh/s6ljnz5eizd2>) 

# Installation:

1) Mount the ISO.
2) Run autoplay.exe.

# Note:

Do not utilise H.264 or H.265 through ME.

Cloud-based functionality will not work for this crack. You must ensure to block internet connections to the app in case of unlicensed errors.

Ensure to use uBlock Origin. The file should be the size and format stated."""

    try:
        # Send DM to the user
        await ctx.author.send(response)
        logger.info(f'Successfully sent ME crack info to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the Media Encoder crack information in your DMs!")

    except discord.Forbidden:
        logger.warning(f'Could not send ME crack info to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending ME crack info to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the information.")

@bot.command(name="prcrack")
async def prcrack_command(ctx):
    """
    Sends information about Adobe Premiere Pro crack.
    Usage: !prcrack
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !prcrack command in {ctx.guild.name if ctx.guild else "DM"}')

    # Actual Premiere Pro crack information
    response = """**Adobe Premiere Pro Crack Information**

# [PREMIERE PRO 2025](<https://hidan.sh/rlr5vmxc2kbm>) 

# Installation:

1) Mount the ISO.
2) Run autoplay.exe.

# Note:

Cloud-based functionality will not work for this crack. You must ensure to block internet connections to the app in case of unlicensed errors.

Ensure to use uBlock Origin. The file should be the size and format stated."""

    try:
        # Send DM to the user
        await ctx.author.send(response)
        logger.info(f'Successfully sent PR crack info to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the Premiere Pro crack information in your DMs!")

    except discord.Forbidden:
        logger.warning(f'Could not send PR crack info to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending PR crack info to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the information.")

@bot.command(name="topazcrack")
async def topazcrack_command(ctx):
    """
    Sends information about Topaz Suite crack.
    Usage: !topazcrack
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !topazcrack command in {ctx.guild.name if ctx.guild else "DM"}')

    # Actual Topaz crack information
    response = """**Topaz Video AI Crack Information**

# [TOPAZ 6.0.3 PRO](<https://tinyurl.com/Topaz-video-ai-6)

# INSTALLATION
1) Replace rlm1611.dll in C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI\\.

2) Copy license.lic to C:\\ProgramData\\Topaz Labs LLC\\Topaz Video AI\\models.

**Note:**

Archive says 6.0.3, but it will still work. The same could be true for later versions.
Starlight won't work as it's credit-based.

Ensure to use uBlock Origin. The file should be the size and format stated."""

    try:
        # Send DM to the user
        await ctx.author.send(response)
        logger.info(f'Successfully sent Topaz crack info to {ctx.author.name}')

        # Send confirmation in the channel
        if ctx.guild:
            await ctx.send(f"{ctx.author.mention}, I've sent you the Topaz Suite crack information in your DMs!")

    except discord.Forbidden:
        logger.warning(f'Could not send Topaz crack info to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending Topaz crack info to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you the information.")

@bot.command(name="hi")
async def hi_command(ctx):
    """
    Alternative command that also sends 'HI' to the user's DMs.
    Usage: !hi
    """
    logger.info(f'User {ctx.author.name} (ID: {ctx.author.id}) invoked !hi command in {ctx.guild.name if ctx.guild else "DM"}')

    try:
        # Send DM to the user
        await ctx.author.send("HI")
        logger.info(f'Successfully sent DM to {ctx.author.name}')

        # Optional confirmation in the channel where command was used
        if ctx.guild:  # Only if command was used in a server, not in DMs
            await ctx.send(f"{ctx.author.mention}, I've sent you a DM!")

    except discord.Forbidden:
        # Handle the case where user has DMs closed or blocked the bot
        logger.warning(f'Could not send DM to {ctx.author.name} - DMs may be closed')
        await ctx.send(f"{ctx.author.mention}, I couldn't send you a DM. Please check your privacy settings.")

    except Exception as e:
        logger.error(f'Error sending DM to {ctx.author.name}: {str(e)}')
        await ctx.send(f"{ctx.author.mention}, an error occurred while trying to send you a DM.")

@bot.command(name="ask")
async def ask_command(ctx, *, question=None):
    """Get deep, detailed answers to any question. Usage: !ask What is quantum computing?"""
    if not question:
        await ctx.send("📝 Please provide a question! Usage: !ask [your question]")
        return
    async with ctx.typing():
        prompt = f"Provide a comprehensive, detailed answer to this question: {question}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="echo")
async def echo_command(ctx, message_id: int, *, text: str):
    """Echo a message to a specific message ID. Admin/Mod only."""
    # Check if user is owner or has manage_messages
    is_owner_check = await bot.is_owner(ctx.author)
    perms = ctx.author.guild_permissions
    if not (is_owner_check or perms.manage_messages or perms.administrator):
        return

    try:
        target_message = None
        # First try current channel (fastest)
        try:
            target_message = await ctx.channel.fetch_message(message_id)
        except:
            # If not in current channel, search other text channels
            for channel in ctx.guild.text_channels:
                if channel.id == ctx.channel.id: continue
                try:
                    target_message = await channel.fetch_message(message_id)
                    if target_message: break
                except: continue
        
        if not target_message:
            await ctx.send(f"❌ Message `{message_id}` not found in this server.", delete_after=10)
            return

        await target_message.reply(text)
        try: await ctx.message.delete()
        except: pass
    except Exception as e:
        await ctx.send(f"❌ Error: {e}", delete_after=5)

@bot.command(name="nudge")
async def nudge_command(ctx):
    """(Admin) Send a nudge to unverified users to verify."""
    # Check permissions
    is_owner_check = await bot.is_owner(ctx.author)
    if not (is_owner_check or ctx.author.guild_permissions.administrator):
        return

    unverified_role_id = int(os.getenv("UNVERIFIED_ROLE_ID", "1311720721285779516"))
    target_channel_id = 1311720529073279058
    
    channel = bot.get_channel(target_channel_id)
    if not channel:
        await ctx.send(f"❌ Target channel <#{target_channel_id}> not found.")
        return

    try:
        msg = await channel.send(
            f"🔔 **ATTENTION <@&{unverified_role_id}>!**\n\n"
            f"Please complete your verification in <#{VERIFICATION_CHANNEL_ID}> to gain full access to the server. "
            f"If you don't verify, you will remain restricted from viewing most channels.\n\n"
            f"*This message will self-destruct in 12 hours.*"
        )
        await ctx.send(f"✅ Nudge sent to {channel.mention}. It will be deleted in 12 hours.")
        
        # Background task to delete after 12 hours
        async def delayed_delete(message):
            await asyncio.sleep(12 * 3600)  # 12 hours
            try:
                await message.delete()
                logger.info(f"Automatically deleted nudge message in {message.channel.name}")
            except:
                pass
        
        bot.loop.create_task(delayed_delete(msg))
        
    except Exception as e:
        logger.error(f"Error sending nudge: {e}")
        await ctx.send(f"❌ Failed to send nudge: {e}")

@bot.command(name="explain")
async def explain_command(ctx, *, topic=None):
    """Explain any topic clearly in simple language. Usage: !explain machine learning"""
    if not topic:
        await ctx.send("📖 Please provide a topic! Usage: !explain [topic]")
        return
    async with ctx.typing():
        prompt = f"Explain '{topic}' in simple, easy-to-understand language. Make it clear for beginners."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="improve")
async def improve_command(ctx, *, text=None):
    """Enhance any message, paragraph, or script. Usage: !improve your text here"""
    if not text:
        await ctx.send("✏️ Please provide text to improve! Usage: !improve [text]")
        return
    async with ctx.typing():
        prompt = f"Enhance and improve this text. Make it better, clearer, more engaging, and more professional: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="rewrite")
async def rewrite_command(ctx, *, text=None):
    """Rewrite text in different tones or styles. Usage: !rewrite make this more formal"""
    if not text:
        await ctx.send("📝 Please provide text to rewrite! Usage: !rewrite [text]")
        return
    async with ctx.typing():
        prompt = f"Rewrite this text in a more creative, engaging, and professional way: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="summarize")
async def summarize_command(ctx, *, text=None):
    """Convert long text into short, clear summaries. Usage: !summarize [your long text]"""
    if not text:
        await ctx.send("📄 Please provide text to summarize! Usage: !summarize [text]")
        return
    async with ctx.typing():
        prompt = f"Summarize this text into a short, clear summary that captures all key points: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="analyze")
async def analyze_command(ctx, *, content=None):
    """Analyze content and give insights or breakdowns. Usage: !analyze this text or concept"""
    if not content:
        await ctx.send("🔍 Please provide content to analyze! Usage: !analyze [content]")
        return
    async with ctx.typing():
        prompt = f"Analyze this content deeply and provide detailed insights, breakdowns, and observations: {content}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="idea")
async def idea_command(ctx, *, topic=None):
    """Generate creative ideas for videos, designs, content, or posts. Usage: !idea gaming video ideas"""
    if not topic:
        await ctx.send("💡 Please provide a topic! Usage: !idea [topic for ideas]")
        return
    async with ctx.typing():
        prompt = f"Generate 5 creative, unique ideas for: {topic}. Make them specific, actionable, and interesting."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="define")
async def define_command(ctx, *, word=None):
    """Get definitions for any word or concept. Usage: !define algorithm"""
    if not word:
        await ctx.send("📚 Please provide a word to define! Usage: !define [word]")
        return
    async with ctx.typing():
        prompt = f"Provide a clear, concise definition of '{word}' with an example of how it's used."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="prime", aliases=["helper"])
async def prime_command(ctx, *, query=None):
    """All-in-one AI command for multi-purpose assistance. Usage: !prime anything you need help with"""
    if not query:
        await ctx.send("🤖 Please provide a request! Usage: !prime [your question/request]")
        return
    async with ctx.typing():
        prompt = f"Help with this request in the most useful way possible: {query}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        for chunk in chunks:
            await ctx.send(chunk)

@bot.command(name="fix")
async def fix_command(ctx, *, text=None):
    """Correct grammar, spelling, and mistakes. Usage: !fix your text here"""
    if not text:
        await ctx.send("✍️ Please provide text to fix! Usage: !fix [text]")
        return
    async with ctx.typing():
        prompt = f"Correct all grammar, spelling, and grammatical mistakes in this text. Return only the corrected text: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="shorten")
async def shorten_command(ctx, *, text=None):
    """Make text shorter but keep the meaning. Usage: !shorten your long text here"""
    if not text:
        await ctx.send("📉 Please provide text to shorten! Usage: !shorten [text]")
        return
    async with ctx.typing():
        prompt = f"Make this text shorter and more concise while keeping all the important meaning: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="expand")
async def expand_command(ctx, *, text=None):
    """Add detail, depth, and clarity to text. Usage: !expand your text here"""
    if not text:
        await ctx.send("📈 Please provide text to expand! Usage: !expand [text]")
        return
    async with ctx.typing():
        prompt = f"Expand this text by adding more detail, depth, and clarity. Make it richer and more comprehensive: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="caption")
async def caption_command(ctx, *, topic=None):
    """Create captions for reels, videos, and posts. Usage: !caption gaming video about speedrun"""
    if not topic:
        await ctx.send("📸 Please provide a topic! Usage: !caption [what the content is about]")
        return
    async with ctx.typing():
        prompt = f"Create 3 engaging, catchy captions for a reel/video/post about: {topic}. Make them fun, relevant, and include relevant hashtags."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="script")
async def script_command(ctx, *, idea=None):
    """Generate short scripts or dialogues. Usage: !script two friends meeting after years"""
    if not idea:
        await ctx.send("🎬 Please provide a script idea! Usage: !script [scene idea]")
        return
    async with ctx.typing():
        prompt = f"Write a short, engaging script or dialogue for: {idea}. Make it natural, interesting, and ready to use."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="format")
async def format_command(ctx, *, text=None):
    """Format text into clean structure or bullet points. Usage: !format your messy text here"""
    if not text:
        await ctx.send("📋 Please provide text to format! Usage: !format [text]")
        return
    async with ctx.typing():
        prompt = f"Format this text into a clean, well-structured format using bullet points or sections as appropriate: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="title")
async def title_command(ctx, *, content=None):
    """Generate attractive titles for any content. Usage: !title about a cat adventure"""
    if not content:
        await ctx.send("⭐ Please provide content! Usage: !title [describe your content]")
        return
    async with ctx.typing():
        prompt = f"Generate 5 creative, catchy, and attractive title options for: {content}. Make them engaging and click-worthy."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="translate")
async def translate_command(ctx, *, text=None):
    """Translate text into any language. Usage: !translate hello world to spanish"""
    if not text:
        await ctx.send("🌍 Please provide text and language! Usage: !translate [text] to [language]")
        return
    async with ctx.typing():
        prompt = f"Translate this text as requested: {text}. Provide only the translation."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

@bot.command(name="paragraph")
async def paragraph_command(ctx, *, text=None):
    """Turn messy text into a clean, structured paragraph. Usage: !paragraph your messy notes here"""
    if not text:
        await ctx.send("📝 Please provide text to format! Usage: !paragraph [text]")
        return
    async with ctx.typing():
        prompt = f"Turn this messy text into a clean, well-structured, professional paragraph: {text}"
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(response)

# --- SLASH COMMANDS (Modern Interactions) ---

@bot.tree.command(name="ping", description="Check the bot's latency")
async def slash_ping(interaction: discord.Interaction):
    """Slash command version of ping"""
    await interaction.response.send_message(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.tree.command(name="prime", description="Ask Prime AI anything")
@app_commands.describe(query="What do you want to ask Prime?")
async def slash_prime(interaction: discord.Interaction, query: str):
    """Slash command version of !prime"""
    await interaction.response.defer()
    try:
        prompt = f"Help with this request in the most useful way possible: {query}"
        response = get_gemini_response(prompt, interaction.user.id, username=interaction.user.name)
        
        # Split response into chunks if it's too long
        chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
        await interaction.followup.send(chunks[0])
        for chunk in chunks[1:]:
            await interaction.channel.send(chunk)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

@bot.tree.command(name="help", description="View all available commands")
async def slash_help(interaction: discord.Interaction):
    """Slash command version of !help"""
    embed = discord.Embed(
        title="🤖 PRIME BOT - COMMANDS",
        description="I've sent the command list to your DMs!",
        color=0x3498DB
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    
    embed_dm = discord.Embed(
        title="🤖 PRIME BOT - COMMANDS",
        description="Here is the list of available commands you can use!",
        color=0x3498DB
    )
    embed_dm.add_field(name="🚀 Slash Commands", value="`/ping`, `/prime`, `/level`, `/leaderboard`, `/help`, `/commands`", inline=False)
    embed_dm.add_field(name="📋 Prefix Commands (!)", value="`!help`, `!commands`, `!files`, `!presets`, `!level`, `!leaderboard`", inline=False)
    embed_dm.add_field(name="📝 AI Tools", value="`!prime`, `!ask`, `!explain`, `!improve`... (see full list in !help)", inline=False)
    embed_dm.set_footer(text="Prime AI • Developed by BMR")
    
    try:
        await interaction.user.send(embed=embed_dm)
    except:
        pass

@bot.tree.command(name="commands", description="View all available commands")
async def slash_commands(interaction: discord.Interaction):
    """Slash command version of !commands"""
    await slash_help(interaction)

@bot.tree.command(name="level", description="Check your or someone else's level")
@app_commands.describe(member="The user to check")
async def slash_level(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    user_id = member.id
    
    if user_id not in user_levels:
        await interaction.response.send_message(f"📊 **{member.display_name}** hasn't started their journey yet!", ephemeral=False)
        return
        
    data = user_levels[user_id]
    xp = data["xp"]
    level = data["level"]
    next_level_xp = 100 * (level + 1) ** 2
    xp_to_next = next_level_xp - xp
    
    embed = discord.Embed(
        title=f"📊 {member.display_name}'s Level info",
        color=0x3498DB
    )
    if member.display_avatar:
        embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Level", value=str(level), inline=True)
    embed.add_field(name="Total XP", value=str(xp), inline=True)
    embed.add_field(name="XP to Next", value=str(xp_to_next), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="leaderboard", description="Show the top active users")
async def slash_lb(interaction: discord.Interaction):
    if not user_levels:
        await interaction.response.send_message("No data available yet.", ephemeral=True)
        return
        
    sorted_users = sorted(user_levels.items(), key=lambda x: x[1]["xp"], reverse=True)
    lb_text = ""
    for i, (uid, data) in enumerate(sorted_users[:10], 1):
        user = bot.get_user(uid)
        user_name = user.name if user else f"User {uid}"
        lb_text += f"**#{i}** | {user_name} - **Level {data['level']}** ({data['xp']} XP)\n"
        
    embed = discord.Embed(title="🏆 XP LEADERBOARD", description=lb_text, color=0xF1C40F)
    await interaction.response.send_message(embed=embed)
@commands.is_owner()
async def manual_sync(ctx):
    """Owner-only command to manually sync slash commands"""
    await ctx.send("🔄 Syncing slash commands... this may take a moment.")
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"✅ Successfully synced {len(synced)} global slash commands.")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync: {e}")

@bot.listen('on_message')
async def file_command_handler(message):
    """
    Listens for messages that start with ! and checks if they match any filenames.
    If a match is found, sends the file to the user's DMs.
    """
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if message starts with ! and is longer than 1 character
    if not message.content.startswith('!') or len(message.content) <= 1:
        return

    # Extract the filename without the ! and convert to lowercase for case-insensitive matching
    requested_file = message.content[1:]
    requested_file_lower = requested_file.lower()
    
    # Extract just the first word to check against known commands
    first_word = requested_file_lower.split()[0] if requested_file_lower else ""
    
    # Skip for known commands to avoid duplicate messages (case-insensitive check)
    if first_word in ["help", "hi", "files", "software_list", "presets", 
                      "aecrack", "pscrack", "mecrack", "prcrack", "topazcrack", 
                      "ban", "mute", "timeout", "unmute", "setup_roles", "setup_verification", "appeal", "verify",
                      "ask", "explain", "improve", "rewrite", "summarize", "analyze", "idea", "define", "prime", "helper",
                      "fix", "shorten", "expand", "caption", "script", "format", "title", "translate", "paragraph",
                      "remind", "note", "timer", "convert", "emoji", "calculate", "weather", "profile", "serverinfo",
                      "creative", "story", "quote", "brainstorm", "design", "name", "aesthetic", "topics", "motivate",
                      "role", "setup_roles", "setup_verification", "check_automod", "setup_automod", "setup_content_roles", "echo",
                      "level", "leaderboard", "rank", "sync", "manual_sync", "commands", "cmds", "nudge", "portfolio", "profile", "p"]:
        return
    
    logger.info(f'User {message.author.name} (ID: {message.author.id}) requested file: {requested_file}')

    # Check if the file exists in the files directory - handle both with and without spaces and case sensitivity
    file_paths = [
        f"files/{requested_file}",  # Original format
        f"files/{requested_file.replace('_', ' ')}",  # Replace underscores with spaces
        f"files/{requested_file.replace(' ', '_')}"   # Replace spaces with underscores
    ]

    # Also add lowercase versions for case-insensitive matching
    file_paths_lower = [
        f"files/{requested_file_lower}",  # Lowercase original format
        f"files/{requested_file_lower.replace('_', ' ')}",  # Lowercase with spaces
        f"files/{requested_file_lower.replace(' ', '_')}"   # Lowercase with underscores
    ]

    # Combine all possible paths
    file_paths.extend(file_paths_lower)
    file_extensions = ["", ".txt", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".mp3", ".mp4", ".zip", ".ffx"]

    found_file = None
    for base_path in file_paths:
        for ext in file_extensions:
            potential_path = f"{base_path}{ext}"
            if os.path.exists(potential_path) and os.path.isfile(potential_path):
                found_file = potential_path
                break
        if found_file:
            break

    # If file was found, send it to the user
    if found_file:
        try:
            # Send file to the user's DMs
            await message.author.send(f"Here's your requested file: `{requested_file}`", 
                                    file=discord.File(found_file))
            logger.info(f'Successfully sent file {found_file} to {message.author.name}')

            # Send confirmation in the channel
            if message.guild:  # Only if command was used in a server
                await message.channel.send(f"{message.author.mention}, I've sent your requested file to your DMs!")

        except discord.Forbidden:
            # Handle the case where user has DMs closed
            logger.warning(f'Could not send file to {message.author.name} - DMs may be closed')
            await message.channel.send(f"{message.author.mention}, I couldn't send you the file. Please check your privacy settings.")

        except Exception as e:
            # Handle other exceptions
            logger.error(f'Error sending file to {message.author.name}: {str(e)}')
            await message.channel.send(f"{message.author.mention}, an error occurred while trying to send you the file.")

    # If file was not found, try to suggest a command
    else:
        # Define the known commands for suggestions - including common misspellings and variations
        known_commands = {
            # software_list variations
            "software": "software_list",
            "softwarelist": "software_list",
            "software_list": "software_list",
            "softlist": "software_list",
            "soft": "software_list",
            "softwares": "software_list",
            "software list": "software_list",
            "softwre": "software_list",
            "softwear": "software_list",
            "sotware": "software_list",

            # aecrack variations
            "aecrack": "aecrack",
            "aftereffects": "aecrack",
            "after_effects": "aecrack",
            "after effects": "aecrack",
            "aftereffect": "aecrack",
            "ae": "aecrack",
            "acrack": "aecrack",
            "aecrck": "aecrack",
            "aecrk": "aecrack",
            "after effect": "aecrack",
            "aftereffects crack": "aecrack",
            "ae crack": "aecrack",
            "aec": "aecrack",

            # pscrack variations
            "pscrack": "pscrack",
            "photoshop": "pscrack",
            "photoshop crack": "pscrack",
            "ps": "pscrack",
            "ps crack": "pscrack",
            "photo shop": "pscrack",
            "photo": "pscrack",
            "pscrk": "pscrack",
            "psc": "pscrack",
            "photshop": "pscrack",
            "photoshp": "pscrack",

            # mecrack variations
            "mecrack": "mecrack",
            "mediaencoder": "mecrack",
            "media_encoder": "mecrack",
            "media encoder": "mecrack",
            "me": "mecrack",
            "me crack": "mecrack",
            "media crack": "mecrack",
            "encoder": "mecrack",
            "mecrk": "mecrack",
            "mec": "mecrack",
            "media encoder crack": "mecrack",

            # prcrack variations
            "prcrack": "prcrack",
            "premiere": "prcrack",
            "premierepro": "prcrack",
            "premiere_pro": "prcrack",
            "premiere pro": "prcrack",
            "pr": "prcrack",
            "pr crack": "prcrack",
            "premire": "prcrack",
            "premiere crack": "prcrack",
            "premier": "prcrack",
            "premire pro": "prcrack",
            "prc": "prcrack",
            "primier": "prcrack",
            "premier pro": "prcrack",

            # topazcrack variations
            "topazcrack": "topazcrack",
            "topaz": "topazcrack",
            "topaz crack": "topazcrack",
            "topaz ai": "topazcrack",
            "topazai": "topazcrack",
            "tpz": "topazcrack",
            "topas": "topazcrack",
            "topazvideo": "topazcrack",
            "topaz video": "topazcrack",
            "topz": "topazcrack",
            "topazai crack": "topazcrack",

            # presets variations
            "preset": "presets",
            "presets": "presets",
            "colorpresets": "presets",
            "color_presets": "presets",
            "color presets": "presets",
            "cc": "presets",
            "cc presets": "presets",
            "color correction": "presets",
            "preset list": "presets",
            "colorcorrection": "presets",
            "preest": "presets",
            "prest": "presets",
            "prset": "presets",
            "presetes": "presets",
            "cc files": "presets",
            "cc file": "presets",
            "ffx": "presets",
            "ffx files": "presets",

            # files variations
            "file": "files",
            "files": "files",
            "filess": "files",
            "filee": "files",
            "fies": "files",
            "fils": "files",
            "file list": "files",
            "files list": "files",
            "all files": "files",

            # help variations
            "help": "help",
            "hlp": "help",
            "halp": "help",
            "hellp": "help",
            "hel": "help",

            # hi variations
            "hi": "hi",
            "hello": "hi",
            "hey": "hi",
            "hii": "hi",
            "helo": "hi",

            # list variations (Renamed to !commands)
            "list": "commands",
            "lst": "commands",
            "lis": "commands",
            "lists": "commands",
            "command": "commands",
            "commands": "commands",
            "command list": "commands",
            "cmd": "commands",
            "cmds": "commands",
            "all commands": "commands"
        }

        # Check if the requested command matches exactly, or with spaces, underscores or hyphens removed
        found_match = False
        suggested_command = None

        # First try exact match
        if requested_file_lower in known_commands:
            suggested_command = known_commands[requested_file_lower]
            found_match = True

        # Try without spaces, underscores, or hyphens if no exact match
        if not found_match:
            # Remove spaces, underscores, hyphens and check again
            normalized_request = requested_file_lower.replace(' ', '').replace('_', '').replace('-', '')
            for cmd, suggestion in known_commands.items():
                normalized_cmd = cmd.replace(' ', '').replace('_', '').replace('-', '')
                if normalized_request == normalized_cmd:
                    suggested_command = suggestion
                    found_match = True
                    break

        # Try more flexible matching for typos (check if command is contained in the request)
        if not found_match:
            for cmd, suggestion in known_commands.items():
                # For short commands (3 chars or less), only check exact matches to avoid false positives
                if len(cmd) <= 3 and cmd != requested_file_lower:
                    continue

                # For longer commands, check if the command is a substring or the request is a substring
                if (len(cmd) > 3 and (cmd in requested_file_lower or 
                   (len(requested_file_lower) > 3 and requested_file_lower in cmd))):
                    suggested_command = suggestion
                    found_match = True
                    break

        if found_match and suggested_command is not None:
            await message.channel.send(f"{message.author.mention}, did you mean to use `!{suggested_command}`? Try typing that instead.")
            logger.info(f'Suggested !{suggested_command} instead of !{requested_file}')
        else:
            # Ignore duplicate "command not found" for valid commands or specific keywords
            if requested_file_lower not in ['role', 'verify']:
                await message.channel.send(f"{message.author.mention}, I couldn't find a file named `{requested_file}`.")
                logger.warning(f'File not found: {requested_file}')

@bot.command(name="ban")
async def ban_command(ctx, member: discord.Member = None):
    """Ban a user from the server - Server admin/inviter can use this."""
    # Check if user is server admin (inviter, owner, or has admin perms)
    if not is_server_admin(ctx.author, ctx.guild):
        admin_name = get_server_admin_name(ctx.guild)
        await ctx.send(f"{ctx.author.mention}, only **{admin_name}** (the person who added me) or server admins can use this command.")
        return
    
    if not member:
        await ctx.send("Who do you want me to ban? Mention someone or provide their username.")
        return
    
    try:
        # Check if bot has permission to ban
        if not ctx.guild.me.guild_permissions.ban_members:
            await ctx.send("❌ I don't have permission to ban members!")
            return
        
        # Check if bot's role is higher than target member's role
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"❌ I can't ban {member.name} because their role is equal to or higher than mine!")
            logger.warning(f"Can't ban {member.name} - role too high")
            return
        
        # Don't allow banning BMR or the server admin
        if 'bmr' in member.name.lower() or is_server_admin(member, ctx.guild):
            await ctx.send("❌ I can't ban this user!")
            return
        
        # Send DM to user before banning
        try:
            await member.send(f"You have been **BANNED** from {ctx.guild.name} by {ctx.author.name}.")
        except:
            pass  # User may have DMs disabled
        
        # Ban the user
        await ctx.guild.ban(member, reason=f"Banned by {ctx.author.name}")
        await ctx.send(f"✓ {member.name} has been **BANNED** from the server. Goodbye! 🚫")
        logger.info(f"{ctx.author.name} banned {member.name}")
        
        # Log the activity
        await log_activity(
            "🔨 User Banned",
            f"**{member.name}** was banned from **{ctx.guild.name}**",
            color=0xFF0000,
            fields={
                "Banned By": ctx.author.name,
                "Server": ctx.guild.name,
                "User": f"{member.name}#{member.discriminator}"
            }
        )
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to ban {member.name}!")
        logger.error(f"Permission denied when trying to ban {member.name}")
    except Exception as e:
        logger.error(f"Error banning user: {str(e)}")
        await ctx.send(f"❌ Error banning user: {str(e)}")

@bot.command(name="timeout")
async def timeout_command(ctx, member: discord.Member = None, duration: str = None):
    """Timeout a user for a specified duration - Server admin/inviter can use this."""
    # Check if user is server admin (inviter, owner, or has admin perms)
    if not is_server_admin(ctx.author, ctx.guild):
        admin_name = get_server_admin_name(ctx.guild)
        await ctx.send(f"{ctx.author.mention}, only **{admin_name}** (the person who added me) or server admins can use this command.")
        return
    
    if not member:
        await ctx.send("Who do you want me to timeout? Mention someone or provide their username.")
        return
    
    if not duration:
        await ctx.send("How long should I timeout them for? (e.g., 1h, 24h, 1d, 30m)")
        return
    
    try:
        # Parse duration
        duration_lower = duration.lower().strip()
        timeout_seconds = 0
        
        if 'h' in duration_lower:
            hours = int(duration_lower.replace('h', '').strip())
            timeout_seconds = hours * 3600
        elif 'd' in duration_lower:
            days = int(duration_lower.replace('d', '').strip())
            timeout_seconds = days * 86400
        elif 'm' in duration_lower:
            minutes = int(duration_lower.replace('m', '').strip())
            timeout_seconds = minutes * 60
        elif 's' in duration_lower:
            seconds = int(duration_lower.replace('s', '').strip())
            timeout_seconds = seconds
        else:
            await ctx.send("Invalid duration format. Use: 1h, 24h, 1d, 30m, or 60s")
            return
        
        # Check if bot has permission to timeout
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.send("❌ I don't have permission to timeout members!")
            return
        
        # Check if bot's role is higher than target member's role
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"❌ I can't timeout {member.name} because their role is equal to or higher than mine!")
            logger.warning(f"Can't timeout {member.name} - role too high")
            return
        
        # Don't allow timing out BMR or the server admin
        if 'bmr' in member.name.lower() or is_server_admin(member, ctx.guild):
            await ctx.send("❌ I can't timeout this user!")
            return
        
        # Send DM to user before timeout
        try:
            await member.send(f"You have been **TIMED OUT** in {ctx.guild.name} by {ctx.author.name} for {duration}.")
        except:
            pass  # User may have DMs disabled
        
        # Apply timeout
        timeout_until = datetime.now(timezone.utc) + timedelta(seconds=timeout_seconds)
        await member.timeout(timeout_until, reason=f"Timeout by {ctx.author.name}")
        await ctx.send(f"✓ {member.name} has been **TIMED OUT** for {duration}. 🔇")
        logger.info(f"{ctx.author.name} timed out {member.name} for {duration}")
        
        # Log the activity
        await log_activity(
            "🔇 User Timed Out",
            f"**{member.name}** was timed out in **{ctx.guild.name}**",
            color=0xFFA500,
            fields={
                "Timed Out By": ctx.author.name,
                "Server": ctx.guild.name,
                "Duration": duration,
                "User": f"{member.name}#{member.discriminator}"
            }
        )
    except ValueError:
        await ctx.send("Invalid duration format. Use: 1h, 24h, 1d, 30m, or 60s")
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to timeout {member.name}!")
        logger.error(f"Permission denied when trying to timeout {member.name}")
    except Exception as e:
        logger.error(f"Error timing out user: {str(e)}")
        await ctx.send(f"❌ Error timing out user: {str(e)}")

@bot.command(name="mute")
async def mute_command(ctx, member: discord.Member = None, duration: str = None):
    """Timeout a user (alias for timeout command) - Server admin/inviter can use this."""
    if not member or not duration:
        await ctx.send("Usage: !mute @user 24h")
        return
    await ctx.invoke(timeout_command, member=member, duration=duration)

@bot.command(name="unmute")
async def unmute_command(ctx, member: discord.Member = None):
    """Remove timeout from a user - Server admin/inviter can use this."""
    # Check if user is server admin (inviter, owner, or has admin perms)
    if not is_server_admin(ctx.author, ctx.guild):
        admin_name = get_server_admin_name(ctx.guild)
        await ctx.send(f"{ctx.author.mention}, only **{admin_name}** (the person who added me) or server admins can use this command.")
        return
    
    if not member:
        await ctx.send("Usage: !unmute @user")
        return
    
    try:
        # Check if bot has permission
        if not ctx.guild.me.guild_permissions.moderate_members:
            await ctx.send("❌ I don't have permission to remove timeouts!")
            return
        
        # Remove timeout by setting it to None
        await member.timeout(None, reason=f"Unmuted by {ctx.author.name}")
        await ctx.send(f"✓ {member.name} has been **UNMUTED**. 🔊")
        logger.info(f"{ctx.author.name} unmuted {member.name}")
        
        # Send DM to user
        try:
            await member.send(f"You have been **UNMUTED** in {ctx.guild.name} by {ctx.author.name}.")
        except:
            pass
        
        # Log the activity
        await log_activity(
            "🔊 User Unmuted",
            f"**{member.name}** was unmuted in **{ctx.guild.name}**",
            color=0x00FF00,
            fields={
                "Unmuted By": ctx.author.name,
                "Server": ctx.guild.name,
                "User": f"{member.name}#{member.discriminator}"
            }
        )
            
    except discord.Forbidden:
        await ctx.send(f"❌ I don't have permission to unmute {member.name}!")
    except Exception as e:
        logger.error(f"Error unmuting user: {str(e)}")
        await ctx.send(f"❌ Error unmuting user: {str(e)}")

# ============================================================================
# UTILITY TOOLS COMMANDS
# ============================================================================

# Storage for reminders and notes
user_reminders: Dict[int, List[Dict]] = {}
user_notes: Dict[int, List[str]] = {}

@bot.command(name="remind")
async def remind_command(ctx, time_str: str = None, *, reminder_text: str = None):
    """Set a reminder for a task. Usage: !remind 5m Don't forget the meeting"""
    if not time_str or not reminder_text:
        await ctx.send("Usage: !remind <time> <reminder text>\nExample: !remind 30m Buy groceries")
        return
    
    try:
        # Parse time (5m, 1h, 30s)
        amount = int(''.join(filter(str.isdigit, time_str)))
        unit = ''.join(filter(str.isalpha, time_str)).lower()
        
        if unit == 'm':
            delay = amount * 60
        elif unit == 'h':
            delay = amount * 3600
        elif unit == 's':
            delay = amount
        else:
            await ctx.send("❌ Use time format like: 5m, 1h, 30s")
            return
        
        user_id = ctx.author.id
        if user_id not in user_reminders:
            user_reminders[user_id] = []
        
        reminder_data = {"text": reminder_text, "time": datetime.now(timezone.utc), "delay": delay}
        user_reminders[user_id].append(reminder_data)
        
        await ctx.send(f"⏰ Reminder set for {time_str}: **{reminder_text}**")
        
        # Schedule the reminder
        await asyncio.sleep(delay)
        try:
            await ctx.author.send(f"⏰ **REMINDER**: {reminder_text}")
            logger.info(f"Sent reminder to {ctx.author.name}")
        except:
            pass
    except Exception as e:
        await ctx.send(f"❌ Error setting reminder: {str(e)}")
        logger.error(f"Reminder error: {str(e)}")

@bot.command(name="note")
async def note_command(ctx, *, note_text: str = None):
    """Save a note for later. Usage: !note Remember to update the profile"""
    if not note_text:
        user_id = ctx.author.id
        if user_id in user_notes and user_notes[user_id]:
            notes_list = "\n".join([f"• {note}" for note in user_notes[user_id]])
            await ctx.send(f"📝 **Your Notes:**\n{notes_list}")
        else:
            await ctx.send("📝 You have no saved notes. Use `!note <text>` to save one!")
        return
    
    user_id = ctx.author.id
    if user_id not in user_notes:
        user_notes[user_id] = []
    
    user_notes[user_id].append(note_text)
    await ctx.send(f"✓ Note saved! ({len(user_notes[user_id])} total notes)")

@bot.command(name="timer")
async def timer_command(ctx, time_str: str = None):
    """Start a countdown timer. Usage: !timer 5m"""
    if not time_str:
        await ctx.send("Usage: !timer <time>\nExample: !timer 5m, !timer 30s, !timer 2h")
        return
    
    try:
        amount = int(''.join(filter(str.isdigit, time_str)))
        unit = ''.join(filter(str.isalpha, time_str)).lower()
        
        if unit == 'm':
            seconds = amount * 60
            display = f"{amount}m"
        elif unit == 'h':
            seconds = amount * 3600
            display = f"{amount}h"
        elif unit == 's':
            seconds = amount
            display = f"{amount}s"
        else:
            await ctx.send("❌ Use time format like: 5m, 1h, 30s")
            return
        
        msg = await ctx.send(f"⏱️ **Timer started**: {display}")
        await asyncio.sleep(seconds)
        await msg.edit(content=f"✓ **Timer finished!** {display} has passed. {ctx.author.mention}")
    except Exception as e:
        await ctx.send(f"❌ Timer error: {str(e)}")

@bot.command(name="convert")
async def convert_command(ctx, mode: str = None, *, text: str = None):
    """Convert text format. Usage: !convert upper hello world"""
    if not mode or not text:
        await ctx.send("Usage: !convert <mode> <text>\nModes: upper, lower, title, reverse, morse")
        return
    
    mode = mode.lower()
    if mode == "upper":
        result = text.upper()
    elif mode == "lower":
        result = text.lower()
    elif mode == "title":
        result = text.title()
    elif mode == "reverse":
        result = text[::-1]
    elif mode == "morse":
        morse_dict = {' ': '/', 'a': '.-', 'b': '-...', 'c': '-.-.', 'd': '-..', 'e': '.', 'f': '..-.',
                      'g': '--.', 'h': '....', 'i': '..', 'j': '.---', 'k': '-.-', 'l': '.-..',
                      'm': '--', 'n': '-.', 'o': '---', 'p': '.--.', 'q': '--.-', 'r': '.-.',
                      's': '...', 't': '-', 'u': '..-', 'v': '...-', 'w': '.--', 'x': '-..-',
                      'y': '-.--', 'z': '--..'}
        result = ' '.join(morse_dict.get(c.lower(), c) for c in text)
    else:
        await ctx.send("❌ Unknown mode. Use: upper, lower, title, reverse, morse")
        return
    
    await ctx.send(f"✓ **{mode.title()}**: {result[:200]}")

@bot.command(name="emoji")
async def emoji_command(ctx, *, text: str = None):
    """Get emoji suggestions based on your text"""
    if not text:
        await ctx.send("Usage: !emoji happy mood")
        return
    
    try:
        prompt = f"Suggest 5 relevant emojis for: {text}. Just list the emojis separated by space."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"😊 **Emojis for '{text}'**: {response[:100]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="calculate")
async def calculate_command(ctx, *, expression: str = None):
    """Do quick math. Usage: !calculate 50+25*2"""
    if not expression:
        await ctx.send("Usage: !calculate <math expression>\nExample: !calculate 100+50/2")
        return
    
    try:
        expression = expression.replace('^', '**')
        result = eval(expression, {"__builtins__": {}}, {})
        await ctx.send(f"🧮 **Result**: {expression} = **{result}**")
    except:
        await ctx.send("❌ Invalid math expression. Use: +, -, *, /, ^(power), %, etc")

@bot.command(name="weather")
async def weather_command(ctx, *, location: str = None):
    """Get weather for any location. Usage: !weather New York"""
    if not location:
        await ctx.send("Usage: !weather <city name>\nExample: !weather London")
        return
    
    try:
        url = f"https://wttr.in/{location}?format=3"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            await ctx.send(f"🌤️ **Weather in {location}**: {response.text}")
        else:
            await ctx.send(f"❌ Couldn't find weather for '{location}'")
    except:
        await ctx.send("❌ Weather service unavailable. Try again later!")

@bot.command(name="profile", aliases=["p"])
async def profile_command(ctx, member: discord.Member = None):
    """Show the user's Prime Portfolio or Profile."""
    member = member or ctx.author
    
    # Logic: If author hasn't set their link, ask for it interactively
    work_link = user_portfolios.get(member.id)
    if not work_link and member == ctx.author:
        prompt_msg = await ctx.send(
            f"👋 {ctx.author.mention}, you haven't linked your portfolio yet!\n"
            f"Please send your YouTube/Portfolio link below now to complete your card (or type `cancel`)."
        )
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel
            
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
            if msg.content.lower() == 'cancel':
                await ctx.send("Cancelled.")
                return
            if msg.content.startswith(("http://", "https://")):
                user_portfolios[ctx.author.id] = msg.content
                save_portfolios(user_portfolios)
                work_link = msg.content
                await ctx.send("✅ Link saved! Generating your card...", delete_after=5)
            else:
                await ctx.send("❌ That doesn't look like a link. I'll show your basic card for now.")
        except asyncio.TimeoutError:
            await ctx.send("⌛ Timed out. Showing basic card.", delete_after=5)

    async with ctx.typing():
        level_data = user_levels.get(member.id, {"level": 0, "xp": 0})
        
        # Generate the card image
        try:
            image_bytes = await generate_portfolio_card(member, level_data, work_link)
            file = discord.File(image_bytes, filename=f"portfolio_{member.id}.png")
            
            embed = discord.Embed(
                title=f"💎 PRIME PORTFOLIO | {member.display_name}", 
                description=f"View {member.mention}'s professional editing profile.",
                color=0x00FFB4
            )
            embed.set_image(url=f"attachment://portfolio_{member.id}.png")
            
            if work_link:
                embed.add_field(name="🔗 FEATURED WORK", value=f"[Click to Watch]({work_link})")
            else:
                embed.add_field(name="🔗 WORK", value="*Not yet linked*")
                
            embed.set_footer(text="Prime Leveling • Exclusive Edition", icon_url=bot.user.display_avatar.url)
            
            await ctx.send(file=file, embed=embed)
        except Exception as e:
            logger.error(f"Error generating portfolio card: {e}")
            await ctx.send(f"❌ Error: {str(e)}")

@bot.group(name="portfolio", invoke_without_command=True)
async def portfolio_group(ctx):
    """Manage your portfolio work link. Usage: !portfolio add [link] or !portfolio remove"""
    await ctx.send("📋 **Portfolio Commands:**\n`!portfolio add [link]` - Link your work\n`!portfolio remove` - Remove your link\n`!profile` - View your portfolio card")

@portfolio_group.command(name="add")
async def portfolio_add(ctx, link: str = None):
    """Add or update your portfolio link."""
    if not link:
        await ctx.send("❌ Please provide a link! Usage: `!portfolio add https://youtube.com/@yourchannel`")
        return
        
    # Basic URL validation
    if not link.startswith(("http://", "https://")):
        await ctx.send("❌ Please provide a valid URL starting with http:// or https://")
        return
        
    user_portfolios[ctx.author.id] = link
    save_portfolios(user_portfolios)
    
    await ctx.send("✅ **Portfolio updated!** Use `!profile` to see your new card.")

@portfolio_group.command(name="remove")
async def portfolio_remove(ctx):
    """Remove your portfolio link."""
    if ctx.author.id in user_portfolios:
        del user_portfolios[ctx.author.id]
        save_portfolios(user_portfolios)
        await ctx.send("🗑️ **Portfolio link removed.**")
    else:
        await ctx.send("❌ You don't have a portfolio link set.")

@bot.command(name="serverinfo")
async def serverinfo_command(ctx):
    """Display server information and statistics"""
    guild = ctx.guild
    if not guild:
        await ctx.send("❌ This command only works in servers!")
        return
    
    embed = discord.Embed(title=f"Server Info - {guild.name}", color=0x5865F2)
    embed.add_field(name="Members", value=guild.member_count, inline=True)
    embed.add_field(name="Channels", value=len(guild.channels), inline=True)
    embed.add_field(name="Roles", value=len(guild.roles), inline=True)
    embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=False)
    embed.add_field(name="Created", value=guild.created_at.strftime("%B %d, %Y"), inline=False)
    embed.add_field(name="Verification Level", value=str(guild.verification_level).title(), inline=False)
    embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
    
    await ctx.send(embed=embed)

# ============================================================================
# CREATIVE TOOLS COMMANDS
# ============================================================================

@bot.command(name="creative")
async def creative_command(ctx, *, topic: str = None):
    """Generate creative ideas & prompts"""
    if not topic:
        await ctx.send("Usage: !creative [topic/idea]\nExample: !creative sci-fi story")
        return
    
    try:
        prompt = f"Generate 5 creative and unique ideas, prompts, or concepts for: {topic}. Be imaginative and innovative."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"💡 **Creative Ideas for '{topic}'**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="story")
async def story_command(ctx, *, prompt: str = None):
    """Create short stories instantly"""
    if not prompt:
        await ctx.send("Usage: !story [story prompt]\nExample: !story a mysterious door")
        return
    
    try:
        gemini_prompt = f"Write a creative short story (3-4 paragraphs) based on: {prompt}"
        response = get_gemini_response(gemini_prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"📖 **Story**: {response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="quote")
async def quote_command(ctx, style: str = None):
    """Produce inspirational or funny quotes"""
    if not style:
        await ctx.send("Usage: !quote [inspirational/funny/random]\nExample: !quote inspirational")
        return
    
    try:
        prompt = f"Generate an original {style} quote that is meaningful and memorable."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"✨ **Quote**: {response[:500]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="brainstorm")
async def brainstorm_command(ctx, *, topic: str = None):
    """Brainstorm ideas with AI"""
    if not topic:
        await ctx.send("Usage: !brainstorm [topic]\nExample: !brainstorm content ideas for youtube")
        return
    
    try:
        prompt = f"Brainstorm 8 creative and practical ideas for: {topic}. List them clearly with brief explanations."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"🧠 **Brainstorm Results**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="design")
async def design_command(ctx, *, project: str = None):
    """Suggest design themes & creative layouts"""
    if not project:
        await ctx.send("Usage: !design [project description]\nExample: !design website for tech startup")
        return
    
    try:
        prompt = f"Suggest 5 design themes, color schemes, and layout ideas for: {project}. Be specific and modern."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"🎨 **Design Suggestions**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="name")
async def name_command(ctx, category: str = None):
    """Generate usernames, bot names, brand names"""
    if not category:
        await ctx.send("Usage: !name [username/brand/bot]\nExample: !name gaming_username")
        return
    
    try:
        prompt = f"Generate 10 creative, catchy, and memorable {category} names. They should be unique and cool."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"✍️ **Name Ideas**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="aesthetic")
async def aesthetic_command(ctx, style: str = None):
    """Suggest color palettes + aesthetic styles"""
    if not style:
        await ctx.send("Usage: !aesthetic [aesthetic style]\nExample: !aesthetic cyberpunk")
        return
    
    try:
        prompt = f"Suggest a complete {style} aesthetic with: color palette (hex codes), typography, mood, and design elements."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"🎭 **{style.title()} Aesthetic**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="topics")
async def topics_command(ctx, context: str = None):
    """Give conversation or content topics"""
    if not context:
        await ctx.send("Usage: !topics [context]\nExample: !topics social media content")
        return
    
    try:
        prompt = f"Generate 10 interesting and engaging topics for: {context}. Make them relevant and trending."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"📋 **Topic Ideas**:\n{response[:1900]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

@bot.command(name="motivate")
async def motivate_command(ctx):
    """Send motivational messages"""
    try:
        prompt = "Generate a short, powerful motivational message that will inspire someone to take action today."
        response = get_gemini_response(prompt, ctx.author.id, username=ctx.author.name)
        await ctx.send(f"💪 **Motivation**: {response[:500]}")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

def run_bot():
    """Function to start the bot with the token from environment variables."""
    # Load configuration
    config = load_config()

    # Get token from environment variable
    token = config.get('DISCORD_TOKEN')

    if not token:
        logger.error("No Discord token found. Please set the DISCORD_TOKEN environment variable.")
        return

    # Run the bot
    logger.info("Starting bot...")
    bot.run(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    run_bot()
