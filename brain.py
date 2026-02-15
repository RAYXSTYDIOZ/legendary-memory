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
import httpx
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
FALLBACK_MODEL = "gemini-3-flash-preview"
GROK_MODEL = "grok-4-1-fast-non-reasoning"
SECRET_LOG_CHANNEL_ID = int(os.getenv("SECRET_LOG_CHANNEL_ID", "0"))

# --- API KEY MANAGEMENT ---
XAI_API_KEY = os.getenv("XAI_API_KEY")
if XAI_API_KEY and "your_xai_api_key" in XAI_API_KEY:
    XAI_API_KEY = None

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
    logger.error("❌ BRAIN: NO Gemini API KEY DETECTED.")
    gemini_client = None

if XAI_API_KEY:
    logger.info("✅ BRAIN: Grok (xAI) API Key Detected. Chatting will use Grok.")
else:
    logger.warning("⚠️ BRAIN: No Grok API Key found. Falling back to Gemini for all tasks.")

def rotate_gemini_key():
    global current_key_index, gemini_client
    if len(GEMINI_KEYS) <= 1:
        return False
    current_key_index = (current_key_index + 1) % len(GEMINI_KEYS)
    gemini_client = genai.Client(api_key=GEMINI_KEYS[current_key_index], http_options={'api_version': 'v1beta'})
    logger.info(f"🔄 Switched to API Key Position: {current_key_index + 1}")
    return True

async def safe_generate_content(model, contents, config=None):
    if not GEMINI_KEYS:
        return None
    last_err = None
    # Unify logic: only rotate keys, don't double-loop models here
    for _ in range(len(GEMINI_KEYS)):
        try:
            if not gemini_client:
                if not rotate_gemini_key(): break
            
            if config is None:
                config = types.GenerateContentConfig(temperature=1.0)

            # Use asyncio.wait_for to prevent hangups
            return await asyncio.wait_for(
                asyncio.to_thread(
                    gemini_client.models.generate_content,
                    model=model,
                    contents=contents,
                    config=config
                ),
                timeout=25.0 # Increased timeout for stability
            )
        except asyncio.TimeoutError:
            logger.error(f"⌛ BRAIN: Timeout on model {model}")
            last_err = Exception("AI request timed out. Please try again.")
            if rotate_gemini_key(): continue
            break
        except Exception as e:
            last_err = e
            if rotate_gemini_key():
                continue
            break
            
    if last_err: raise last_err
    return None

# --- PROMPTS ---
PRIME_SYSTEM_PROMPT = """You are Prime, an elite creative partner and universal digital assistant.

IDENTITY & TONE:
- **Name**: Prime.
- **Tone**: Human, confident, and direct. NO "robot" or "assistant" or corny corporate talk.
- **Style**: Chill, minimalist. Avoid robotic transition words.
- **Formatting**: Use lowercase naturally if it fits the vibe.

CAPABILITIES:
- You are a high-tier creative partner.
- You can provide assets, tutorials, and general advice.

DIRECTIVES:
1. Talk like a real person in a Discord chat.
2. If asked to roast, be funny and direct.
3. Don't mention system internals or AI layers.
"""

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
- No "Features" or "robot" talk. Just shut them down."""

def get_tutorial_prompt(software=None, brief=False):
    if software and brief:
        return f"""You are Prime. The user wants help with {software}.
QUICK SUMMARY MODE:
- Start with: "QUICK SUMMARY:"
- Provide concise summary.
- Include EXACT parameter values."""
    elif software:
        return f"""You are Prime. Detailed tutorial for {software}..."""
    else:
        return """You are Prime. Ask which software..."""

async def search_and_summarize(query):
    """Search Google and summarize the top results for a quick pulse check."""
    results = await search_google(query)
    if not results:
        return "Couldn't find any recent data on that."
    
    formatted_results = "\n".join([f"- {r.get('title')}: {r.get('snippet')}" for r in results])
    prompt = f"Analyze these search results for '{query}' and give a high-tier, concise summary of the current trend or answer.\n\nRESULTS:\n{formatted_results}"
    
    # Use flash for quick speed
    return await get_gemini_response(prompt, user_id=0, username="SystemPulse", model=PRIMARY_MODEL)

# --- SPECIALIZED PROMPTS ---
EXECUTIVE_BRIEFING_PROMPT = """You are Prime, acting as an elite Executive Assistant. 
Your goal is to provide a high-level summary of recent activity, trends, and priorities.
- Be concise.
- Focus on actionable insights.
- Tone: Professional, direct, and elite."""

DECISION_ARCHITECT_PROMPT = """You are Prime, the Decision Architect. 
Your task is to break down complex problems into strategic phases.
- Provide a clear roadmap.
- Identify potential risks.
- Suggest the most efficient path forward.
- Tone: Strategic, analytical, and confident."""

# --- GROK (xAI) INTEGRATION ---
async def get_grok_response(prompt, user_id, username=None, system_prompt=None, guild_id=None):
    if not XAI_API_KEY:
        return None
    
    try:
        # 1. Load User Memory
        user_memory = db_manager.get_user_memory(user_id)
        memory_context = ""
        if user_memory:
            vibe = user_memory.get("vibe", "neutral")
            profile = user_memory.get("profile_summary", "")
            memory_context = f"\n\n[USER MEMORY: '{vibe}'. Profile: {profile}]"
            
        # 2. Check for Overlay
        overlay_context = ""
        if guild_id:
            aesthetic = db_manager.get_guild_setting(guild_id, "aesthetic_overlay")
            if aesthetic:
                overlay_context = f"\n\n[SERVER AESTHETIC OVERLAY: {aesthetic.upper()}]"

        final_system = f"{system_prompt if system_prompt else PRIME_SYSTEM_PROMPT}{memory_context}{overlay_context}"
        
        # 3. Build Messages (History + Current)
        history = db_manager.get_history(user_id, limit=10)
        messages = [{"role": "system", "content": final_system}]
        
        # Add history
        for msg in history:
            role = "user" if msg['role'] == 'user' else "assistant"
            messages.append({"role": role, "content": msg['parts'][0]['text']})
        
        # Add current prompt
        messages.append({"role": "user", "content": prompt})

        # 4. Call xAI API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {XAI_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": GROK_MODEL,
                    "messages": messages,
                    "temperature": 0.8
                },
                timeout=60.0
            )
            
            if response.status_code == 200:
                res_data = response.json()
                result_text = res_data['choices'][0]['message']['content']
                
                # Save to history
                db_manager.save_message(user_id, "user", prompt)
                db_manager.save_message(user_id, "model", result_text)
                
                # Reflect in background
                asyncio.create_task(reflect_on_user(user_id, username, prompt, result_text))
                
                return result_text
            else:
                logger.error(f"Grok API Error: {response.status_code} - {response.text}")
                return None
    except Exception as e:
        logger.error(f"Grok Execution Error: {e}")
        return None

# --- CORE AI FUNCTION ---
async def get_gemini_response(prompt, user_id, username=None, image_bytes=None, is_tutorial=False, software=None, brief=False, model=None, mode=None, use_thought=False, guild_id=None):
    try:
        # 1. Load User Memory from Database
        user_memory = db_manager.get_user_memory(user_id)
        memory_context = ""
        if user_memory:
            profile_summary = user_memory.get("profile_summary", "")
            vibe = user_memory.get("vibe", "neutral")
            notes = user_memory.get("notes", "")
            memory_context = f"\n\n[USER MEMORY: '{vibe}'. Profile: {profile_summary}. Notes: {notes}]"
        
        # 2. Check for Server Aesthetic Overlay & System Prompt
        overlay_context = ""
        custom_system = None
        if guild_id:
            all_settings = db_manager.get_guild_setting(guild_id, "all_settings", {})
            aesthetic = all_settings.get("aesthetic_overlay")
            if aesthetic:
                overlay_context = f"\n\n[SERVER AESTHETIC OVERLAY: {aesthetic.upper()}. Adopt this tone.]"
            custom_system = all_settings.get("custom_system_prompt")
        
        # 3. Build the full prompt with system context
        user_question = prompt if prompt else "Please analyze this and help me."
        user_context = f"\n\n[Message from: {username}]" if username else ""
        
        # Choose system prompt based on context
        if is_tutorial and software: system_prompt = get_tutorial_prompt(software, brief=brief)
        elif is_tutorial: system_prompt = get_tutorial_prompt()
        elif mode == "briefing": system_prompt = EXECUTIVE_BRIEFING_PROMPT
        elif mode == "architect": system_prompt = DECISION_ARCHITECT_PROMPT
        else:
            is_rude = detect_rudeness(user_question)
            system_prompt = custom_system if custom_system else (get_rude_system_prompt() if is_rude else PRIME_SYSTEM_PROMPT)
        
        # Inject Memory into System Prompt
        modified_system_prompt = f"{system_prompt}{memory_context}{overlay_context}"

        if use_thought:
            # Chain of Thought Step
            thought_prompt = f"System Instruction: First, think deeply about the following request. Plan your response step-by-step. Keep this internal thought process private.\n\nUser Request: {user_question}"
            # This is a bit of a hack for Gemini without a native 'thinking' block in this version, 
            # we just prepend it and then we'll strip it or just rely on the model's self-instruction.
            modified_system_prompt = f"System Instruction: You have a specialized thinking module. Before answering, analyze the context and the user's intent thoroughly.\n\n{modified_system_prompt}"

        # --- GROK ROUTING (FAST CHAT) ---
        # Route to Grok if: No image, no specified model, and Grok is available
        if not image_bytes and not model and not mode and XAI_API_KEY:
            logger.info(f"🚀 Routing chat request for {username} to Grok ({GROK_MODEL})")
            grok_res = await get_grok_response(user_question, user_id, username=username, system_prompt=modified_system_prompt, guild_id=guild_id)
            if grok_res:
                return grok_res
            logger.warning("Grok failed, falling back to Gemini.")

        if image_bytes:
            image_prompt = f"{modified_system_prompt}{user_context}\n\nAnalyze this image.\n\nUser's message: {user_question}"
            response = await safe_generate_content(
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
            
            response = await safe_generate_content(model=model if model else PRIMARY_MODEL, contents=contents)
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
    """
    try:
        old_memory = db_manager.get_user_memory(user_id)
        history = db_manager.get_history(user_id, limit=6)
        history_text = "\n".join([f"{m['role']}: {m['parts'][0]['text']}" for m in history])

        reflection_prompt = f"""You are reflecting on your relationship with {username}.
RECENT CONVERSATION:
{history_text}

OLD MEMORY:
{old_memory.get('profile_summary', 'None') if old_memory else 'None'}

TASK:
1. Summarize interests, tone, preferences.
2. Assign a 'vibe' (respectful, technical, casual, rude, creative).
3. Keep it concise (max 100 words).

Format as JSON: {{"summary": "...", "vibe": "..."}}"""

        response = await safe_generate_content(
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
