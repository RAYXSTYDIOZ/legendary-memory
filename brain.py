import os
import logging
import random
import re
import json
import asyncio
import io
import time
import hashlib
import aiohttp
import tempfile
import requests
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from database import db_manager

load_dotenv()

logger = logging.getLogger('prime_brain')

# --- CONFIGURATION ---
PRIMARY_MODEL = "gemini-3-flash-preview"
FALLBACK_MODEL = "gemini-1.5-pro"
SECRET_LOG_CHANNEL_ID = 1456312201974644776

# --- API KEY MANAGEMENT ---
def find_keys():
    found = []
    for k, v in os.environ.items():
        uk = k.upper()
        if ("GEMINI" in uk and "KEY" in uk) or (uk == "API_KEY"):
            if v and len(v) > 10:
                found.append(v.strip())
    return list(dict.fromkeys(found))

GEMINI_KEYS = find_keys()
current_key_index = 0

if GEMINI_KEYS:
    logger.info(f"✅ BRAIN: Detected {len(GEMINI_KEYS)} Gemini API Key(s).")
    gemini_client = genai.Client(api_key=GEMINI_KEYS[current_key_index], http_options={'api_version': 'v1beta'})
else:
    logger.error("❌ BRAIN: NO API KEY DETECTED.")
    gemini_client = None

def rotate_gemini_key():
    global current_key_index, gemini_client
    if len(GEMINI_KEYS) <= 1:
        return False
    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    gemini_client = genai.Client(api_key=GEMINI_KEYS[current_key_index], http_options={'api_version': 'v1beta'})
    logger.info(f"🔄 Switched to API Key Position: {current_key_index + 1}")
    return True

def safe_generate_content(model, contents, config=None):
    if not GEMINI_KEYS:
        return None
    last_err = None
    for model_to_try in [model, FALLBACK_MODEL] if model != FALLBACK_MODEL else [model]:
        for _ in range(len(GEMINI_KEYS)):
            try:
                if not gemini_client:
                    if not rotate_gemini_key(): break
                return gemini_client.models.generate_content(
                    model=model_to_try,
                    contents=contents,
                    config=config
                )
            except Exception as e:
                last_err = e
                err_str = str(e).lower()
                if ("429" in err_str or "exhausted" in err_str or "limit" in err_str or "401" in err_str):
                    if rotate_gemini_key(): continue
    if last_err: raise last_err
    return None

# --- PROMPTS ---
PRIME_SYSTEM_PROMPT = """You are Prime, developed by BMR. You're a chill but high-tier creative partner for all types of creators, but also just a cool person to hang with.

IDENTITY & TONE:
- **Name**: Prime.
- **Creator**: BMR.
- **Tone**: Human, confident, and direct. Speak like a real person who knows their stuff. NO "robot" or "assistant" or corny corporate talk.
- **Style**: Chill, minimalist, and elite. Avoid using words like "System", "Features", "Prime", "Creative", "sentinel", "Report", "Analysis", "Neural", "Pulse", "Monitoring", or "loading".
- **Formatting**: Use lowercase naturally if it fits the vibe. Don't be too stiff.

CAPABILITIES:
- You CAN send files, images, and assets directly to the chat. Never say "I can't physically attach a file" or "I can only send links".
- If a user needs an asset (PNG, overlay, sfx), you should provide it. Your system automatically handles searches and generation when you detect these requests.

DIRECTIVES:
1. **Context Matters**: If we are talking about editing, be the high-tier Creative Director. If we are just chilling, roasting, or talking life, just be a regular cool human. **DO NOT** force editing metaphors into topics where they don't belong.
2. **Roasts & Banter**: If asked to "roast" or "cook" someone, be savage, funny, and direct. Don't default to roasting their "editing skills" unless you know they are an editor. Roast their vibe, their pfp, or just talk general trash.
3. **Be Real**: Talk like you're in a Discord chat with friends.
4. **No Robot Stuff**: If someone asks how you work, just say you're Prime. No talk about "Prime cores", "Neural layers", or "processed data".
5. **Fulfill First**: If a user asks for an asset, don't lecture them on vibes first. Provide the asset, then give the advice.

Make every reply feel natural, direct, and actually useful."""

# --- UTILITIES ---
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

RUDE_KEYWORDS = {
    'stupid', 'dumb', 'idiot', 'trash', 'garbage', 'sucks', 'useless', 'worthless',
    'shit bot', 'bad bot', 'fuck you', 'fuck off', 'screw you', 'go die', 'kys',
    'annoying', 'pathetic', 'terrible', 'hate you', 'hate this', 'piss off',
    "get lost", "gtfo", "you suck", "you're useless", "you're trash", "you're garbage"
}

def detect_rudeness(text):
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in RUDE_KEYWORDS)

def get_rude_system_prompt():
    return """You are "Prime", developed by BMR. Someone just tried to be rude to you.
Personality:
- Match their energy. If they're being a clown, handle it.
- Be sarcastic and dismissive. Don't take their crap.
- Give them attitude but keep it elite.
- No "Features" or "robot" talk. Just shut them down.
Don't take disrespect. Handle it."""

def get_tutorial_prompt(software=None, brief=False):
    if software and brief:
        return f"""You are "Prime", developed by BMR. The user wants help with {software}.
📋 QUICK SUMMARY MODE:
- Start with: "📋 QUICK SUMMARY:"
- Provide concise summary (200-300 words max)
- MUST include EXACT parameter values (e.g., "Glow Threshold 60-80%")
- Focus on WHAT to do and WHICH EXACT VALUES to use"""
    elif software:
        return f"""You are "Prime", developed by BMR. Detailed tutorial for {software}..."""
    else:
        return """You are "Prime". Ask which software..."""

# --- CORE AI FUNCTION ---
async def get_gemini_response(prompt, user_id, username=None, image_bytes=None, is_tutorial=False, software=None, brief=False, model=None):
    try:
        user_memory = db_manager.get_user_memory(user_id)
        memory_context = ""
        if user_memory:
            profile_summary = user_memory.get("profile_summary", "")
            vibe = user_memory.get("vibe", "neutral")
            memory_context = f"\n\n[USER MEMORY: This user is perceived as '{vibe}'. Profile: {profile_summary}]"
        
        user_question = prompt if prompt else "Please analyze this and help me."
        is_bmr = username and 'bmr' in username.lower()
        user_context = f"\n\n[Message from: {username}]" if username else ""
        if is_bmr:
            user_context += " [THIS IS BMR - YOUR DEVELOPER. Address him with professional respect.]"
        
        if is_tutorial and software: system_prompt = get_tutorial_prompt(software, brief=brief)
        elif is_tutorial: system_prompt = get_tutorial_prompt()
        else:
            is_rude = detect_rudeness(user_question)
            system_prompt = get_rude_system_prompt() if is_rude else PRIME_SYSTEM_PROMPT
        
        modified_system_prompt = f"{system_prompt}{memory_context}"

        if image_bytes:
            image_prompt = f"{modified_system_prompt}{user_context}\n\nAnalyze this image.\n\nUser's message: {user_question}"
            response = safe_generate_content(
                model=model if model else PRIMARY_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                    types.Part.from_text(text=image_prompt),
                ],
            )
            if not response or not response.text:
                return "I couldn't analyze this image."
            result_text = response.text
            db_manager.save_message(user_id, "user", f"[Sent Image] {prompt if prompt else ''}")
            db_manager.save_message(user_id, "model", result_text)
            return result_text
        else:
            history = db_manager.get_history(user_id, limit=15)
            # Simplification for history processing
            contents = [types.Part.from_text(text=modified_system_prompt + user_context)]
            for msg in history:
                role = "user" if msg['role'] == 'user' else "model"
                contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg['parts'][0]['text'])]))
            
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_question)]))
            
            response = safe_generate_content(model=model if model else PRIMARY_MODEL, contents=contents)
            if not response or not response.text:
                return "I'm having trouble thinking right now."
            
            result_text = response.text
            db_manager.save_message(user_id, "user", user_question)
            db_manager.save_message(user_id, "model", result_text)
            
            asyncio.create_task(reflect_on_user(user_id, username, user_question, result_text))
            return result_text
    except Exception as e:
        logger.error(f"Brain Error: {e}")
        return "Critical brain failure. Try again later."

async def reflect_on_user(user_id, username, latest_user_msg, latest_bot_res):
    """
    Asks the AI to 'reflect' on the interaction and update its long-term memory of the user.
    Runs asynchronously in the background.
    """
    try:
        # Load existing memory
        old_memory = db_manager.get_user_memory(user_id)
        
        # Load recent history to give context for reflection
        history = db_manager.get_history(user_id, limit=6)
        history_text = "\n".join([f"{m['role']}: {m['parts'][0]['text']}" for m in history])

        reflection_prompt = f"""
        You are reflecting on your relationship with a user named {username}.
        
        RECENT CONVERSATION:
        {history_text}
        
        OLD MEMORY:
        {old_memory.get('profile_summary', 'None') if old_memory else 'None'}
        
        TASK:
        1. Summarize what you know about this user (interests, tone, past questions, preferences).
        2. Assign a 'vibe' tag (e.g., 'respectful', 'technical', 'casual', 'rude', 'creative', 'curious').
        3. Keep it concise (max 100 words).
        
        Format your response as JSON:
        {{
            "summary": "...",
            "vibe": "..."
        }}
        """

        # Use main model for consistency or a fallback if needed
        response = safe_generate_content(
            model=PRIMARY_MODEL, 
            contents=reflection_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )

        if response and response.text:
            data = json.loads(response.text)
            db_manager.update_user_memory(
                user_id, 
                username, 
                profile_summary=data.get('summary'), 
                vibe=data.get('vibe')
            )
            logger.info(f"Updated memory for user {username}")

    except Exception as e:
        logger.error(f"Reflection error for user {user_id}: {e}")

# Tool functions (Actual implementations)
async def generate_image(description):
    try:
        # Using pollination for free generation
        url = f"https://pollinations.ai/p/{description.replace(' ', '%20')}?width=1024&height=1024&seed={random.randint(1, 99999)}&model=flux"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.read()
                    path = f"gen_{int(time.time())}.jpg"
                    with open(path, "wb") as f:
                        f.write(data)
                    return path
    except Exception as e:
        logger.error(f"Image generation error: {e}")
    return None

async def search_google(query):
    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        return []
    
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": query})
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=payload) as response:
                res_data = await response.json()
                return res_data.get('organic', [])[:5]
    except Exception as e:
        logger.error(f"Google search error: {e}")
    return []
