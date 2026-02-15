from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import httpx
import os
import sys
import uuid
import logging
import asyncio
import json
from pathlib import Path
from dotenv import load_dotenv

# Base Setup
BASE_DIR = Path(__file__).parent
sys.path.append(str(BASE_DIR.parent))

from database import db_manager
import brain

load_dotenv()

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("prime_os")

# Configuration Audit & Sanitization
def get_env_safe(key, default=""):
    val = os.getenv(key, default).strip().replace('"', '').replace("'", "")
    if val:
        # Log masked version for safety and verification
        logger.info(f"✅ CONFIG: Loaded {key} ({val[:4]}...{val[-4:]})")
    else:
        logger.error(f"❌ CONFIG: Variable {key} is MISSING or EMPTY!")
    return val

CLIENT_ID = get_env_safe("DISCORD_CLIENT_ID")
CLIENT_SECRET = get_env_safe("DISCORD_CLIENT_SECRET")
BOT_TOKEN = get_env_safe("DISCORD_TOKEN")
REDIRECT_URI = get_env_safe("DISCORD_REDIRECT_URI")

# Railway Environment Detection
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")

# Smart Overwrite: If it's localhost but we have a Railway domain, it's definitely wrong.
if ("localhost" in REDIRECT_URI or not REDIRECT_URI) and RAILWAY_DOMAIN:
    # Ensure domain has no protocol for a clean join
    clean_domain = RAILWAY_DOMAIN.replace("https://", "").replace("http://", "").rstrip("/")
    REDIRECT_URI = f"https://{clean_domain}/callback"
    logger.info(f"🚀 CLOUD OVERRIDE: Redirect URI forced to {REDIRECT_URI}")

# Final Fallback
if not REDIRECT_URI:
    REDIRECT_URI = "http://localhost:8000/callback"
    logger.warning("⚠️ CONFIG: Defaulting to localhost REDIRECT_URI.")

logger.info(f"🎯 FINAL REDIRECT_URI: {REDIRECT_URI}")

if not CLIENT_ID or not BOT_TOKEN:
    print("\n" + "!"*60)
    print("CRITICAL CONFIG ERROR: Your Discord Client ID or Bot Token is missing.")
    print("Please check your Railway Variables tab immediately!")
    print("!"*60 + "\n")

# SERVER-SIDE STORAGE
SESSIONS = {}
BOT_GUILDS = set()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# BOT UTILS
# --------------------------------------------------------------------------

async def update_bot_guilds():
    """Fetch all guilds the bot is currently in."""
    global BOT_GUILDS
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                "https://discord.com/api/v10/users/@me/guilds",
                headers={"Authorization": f"Bot {BOT_TOKEN}"}
            )
            if res.status_code == 200:
                guilds = res.json()
                BOT_GUILDS = {str(g["id"]) for g in guilds}
                logger.info(f"Bot is in {len(BOT_GUILDS)} servers.")
    except Exception as e:
        logger.error(f"Failed to fetch bot guilds: {e}")

@app.on_event("startup")
async def startup_event():
    await update_bot_guilds()

# --------------------------------------------------------------------------
# AUTH ENGINE
# --------------------------------------------------------------------------

@app.get("/login")
async def login():
    scopes = "identify guilds"
    url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&redirect_uri={REDIRECT_URI}&response_type=code&scope={scopes}"
    return RedirectResponse(url=url)

@app.get("/callback")
async def callback(code: str = None):
    if not code: return RedirectResponse(url="/dashboard/index.html?error=no_code")
    
    async with httpx.AsyncClient() as client:
        token_res = await client.post("https://discord.com/api/oauth2/token", data={
            "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT_URI
        })
        if token_res.status_code != 200: return RedirectResponse(url="/dashboard/index.html?error=auth_failed")
        
        token_data = token_res.json()
        access_token = token_data["access_token"]
        
        user_res = await client.get("https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        guilds_res = await client.get("https://discord.com/api/users/@me/guilds", headers={"Authorization": f"Bearer {access_token}"})
        
        user_info = user_res.json()
        guilds = guilds_res.json()
        
        session_token = str(uuid.uuid4())
        SESSIONS[session_token] = {
            "user": {"id": user_info["id"], "name": user_info["username"], "avatar": user_info.get("avatar")},
            "guilds": guilds
        }
        return RedirectResponse(url=f"/dashboard/index.html?session_token={session_token}")

@app.get("/api/me")
async def api_me(request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: return JSONResponse({"authenticated": False}, status_code=401)
    
    # Refresh bot guilds list on check
    await update_bot_guilds()
    
    data = SESSIONS[token]
    # Enrich guilds with 'bot_present' flag
    enriched_guilds = []
    for g in data["guilds"]:
        g_copy = g.copy()
        g_copy["bot_present"] = str(g["id"]) in BOT_GUILDS
        enriched_guilds.append(g_copy)
    
    return {"authenticated": True, "user": data["user"], "guilds": enriched_guilds}

@app.get("/api/dashboard/stats")
async def dash_stats(request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: return JSONResponse({"error": "Unauthorized"}, status_code=401)
    try:
        with db_manager.get_connection() as conn:
            with db_manager.get_cursor(conn) as cursor:
                cursor.execute("SELECT COUNT(*) FROM user_levels")
                user_count = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM conversation_history")
                msg_count = cursor.fetchone()[0]
                return {"users": user_count, "messages": msg_count, "status": "Healthy", "bot_servers": len(BOT_GUILDS)}
    except: return {"error": "DB Error"}

@app.get("/api/guilds/{guild_id}/settings")
async def get_settings(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    settings = db_manager.get_guild_setting(guild_id, "all_settings", {"prefix": "!", "vibe": "helpful"})
    return settings

@app.get("/api/guilds/{guild_id}/roles")
async def get_roles(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers={"Authorization": f"Bot {BOT_TOKEN}"})
        if res.status_code == 200: return res.json()
    return []

@app.get("/api/guilds/{guild_id}/channels")
async def get_channels(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    async with httpx.AsyncClient() as client:
        res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers={"Authorization": f"Bot {BOT_TOKEN}"})
        if res.status_code == 200: return res.json()
    return []

@app.post("/api/guilds/{guild_id}/ai-suggest")
async def ai_suggest_config(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    
    if not brain.GEMINI_KEYS:
        return {"status": "error", "error": "AI module unavailable."}

    # Fetch context: Channels and Roles
    async with httpx.AsyncClient() as client:
        # Get roles
        r_res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers={"Authorization": f"Bot {BOT_TOKEN}"})
        # Get channels
        c_res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers={"Authorization": f"Bot {BOT_TOKEN}"})
        
        roles = r_res.json() if r_res.status_code == 200 else []
        channels = c_res.json() if c_res.status_code == 200 else []

    # Prepare context for AI
    chan_list = [{"id": c["id"], "name": c["name"], "type": c["type"]} for c in channels if c["type"] in [0, 5]]
    role_list = [{"id": r["id"], "name": r["name"], "color": r["color"]} for r in roles if r["name"] != "@everyone" and not r.get("managed")]

    system_instr = """You are a Discord AI Auditor.
Analyze the provided lists of channels and roles. Map them to the following internal configuration keys based on their names and purpose.
Keys to map:
- welcome_channel: (Channel for welcome messages)
- log_channel: (Channel for logs/audits)
- rules_channel: (Channel for rules)
- roles_channel: (Channel for role selection)
- verification_channel: (Channel for newcomer verification)
- leveling_channel: (Channel for level up alerts)
- general_channel: (Main chat channel)
- verified_role: (Role for verified members)
- unverified_role: (Role for new members)
- muted_role: (Role for muted users)

Also, if a role has the default color (0), suggest a creative hex color that fits its name.

OUTPUT FORMAT: Return ONLY a JSON object:
{
  "mappings": { "key": "id", ... },
  "role_color_suggestions": [ {"id": "...", "suggested_color": "#hex"}, ... ],
  "reasoning": "A very brief explanation of why you chose these."
}
"""

    context_str = f"CHANNELS: {json.dumps(chan_list)}\nROLES: {json.dumps(role_list)}"
    
    try:
        from brain import safe_generate_content, PRIMARY_MODEL, types
        response = await safe_generate_content(
            model=PRIMARY_MODEL, 
            contents=f"{system_instr}\n\nSERVER CONTEXT:\n{context_str}\n\nOutput JSON:",
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2)
        )
        
        if not response or not response.text:
            return {"status": "error", "error": "AI calculation timed out."}
        
        suggestions = json.loads(response.text)
        return {"status": "success", "suggestions": suggestions}
    except Exception as e:
        logger.error(f"AI Suggest Error: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/guilds/{guild_id}/apply-suggestions")
async def apply_suggestions(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    
    data = await request.json()
    color_updates = data.get("color_updates", [])
    
    async with httpx.AsyncClient() as client:
        for update in color_updates:
            role_id = update.get("id")
            hex_color = update.get("suggested_color", "0").replace("#", "")
            if role_id and hex_color != "0":
                try:
                    color_int = int(hex_color, 16)
                    # PATCH role color
                    await client.patch(
                        f"https://discord.com/api/v10/guilds/{guild_id}/roles/{role_id}",
                        headers={"Authorization": f"Bot {BOT_TOKEN}"},
                        json={"color": color_int}
                    )
                except Exception as e:
                    logger.error(f"Failed to update role color {role_id}: {e}")
                    
    return {"status": "success"}

@app.post("/api/guilds/{guild_id}/ai-plan")
async def ai_plan(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    
    if not brain.GEMINI_KEYS:
        return {"status": "error", "error": "CRITICAL: Gemini API Key is missing from .env"}

    data = await request.json()
    user_prompt = data.get("prompt")
    if not user_prompt: return {"error": "No prompt provided"}

    system_instr = """You are a Discord Server Architect.
Interpret the user's request and output a JSON list of actions to structure their server.
Valid Actions:
- {"action": "create_category", "name": "..."}
- {"action": "create_channel", "name": "...", "type": "text|voice", "category": "..."}
- {"action": "create_role", "name": "...", "color": "hex_code", "icon": "emoji"}

RULES:
1. Only return the JSON list. No explanation.
2. If a category is mentioned for a channel, ensure you create_category first.
3. Be CREATIVE with icons/emojis for roles based on the user's suggestion.
4. If the user mentions a color (e.g. 'navy blue'), find the hex code.
5. Limit to max 12 actions per plan.
"""

    try:
        from brain import safe_generate_content, PRIMARY_MODEL, types
        full_prompt = f"Context: Creating a Discord server structure.\nUser Goal: {user_prompt}\n\nInstruction: {system_instr}\n\nOutput JSON Action List:"

        response = await safe_generate_content(
            model=PRIMARY_MODEL,
            contents=full_prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
        )
        
        if not response or not response.text:
            return {"status": "error", "error": "AI failed to generate a plan. Try be more specific."}
        
        raw_text = response.text.strip()
        if raw_text.startswith("```json"): raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif raw_text.startswith("```"): raw_text = raw_text.split("```")[1].split("```")[0].strip()

        try:
            plan = json.loads(raw_text)
            if not isinstance(plan, list): plan = [plan]
            return {"status": "success", "plan": plan}
        except Exception as json_err:
            logger.error(f"AI Plan JSON Parse Error: {json_err} | Raw: {raw_text}")
            return {"status": "error", "error": "AI returned invalid data format."}
    except Exception as e:
        logger.error(f"AI Plan Critical Error: {e}")
        return {"status": "error", "error": str(e)}

@app.post("/api/guilds/{guild_id}/ai-execute")
async def ai_execute(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    data = await request.json()
    plan = data.get("plan", [])
    if not plan: return {"error": "No plan provided"}

    results = []
    categories = {}
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bot {BOT_TOKEN}", "Content-Type": "application/json"}
        for task in plan:
            action = task.get("action")
            name = task.get("name")
            if action == "create_category":
                res = await client.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json={"name": name, "type": 4})
                if res.status_code == 201: categories[name] = res.json()["id"]; results.append(f"Created category: {name}")
            elif action == "create_channel":
                c_type = 0 if task.get("type") == "text" else 2
                payload = {"name": name, "type": c_type}
                cat_name = task.get("category"); 
                if cat_name in categories: payload["parent_id"] = categories[cat_name]
                res = await client.post(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers, json=payload)
                if res.status_code == 201: results.append(f"Created channel: {name}")
            elif action == "create_role":
                name = task.get("name")
                icon = task.get("icon", "")
                full_name = f"{icon} {name}".strip() if icon else name
                color_hex = task.get("color", "0").replace("#", "")
                color_int = int(color_hex, 16) if color_hex != "0" else 0
                res = await client.post(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers, json={"name": full_name, "color": color_int})
                if res.status_code in [200, 201]: results.append(f"Created role: {full_name}")
    return {"status": "success", "results": results}

@app.post("/api/guilds/{guild_id}/settings")
async def save_settings(guild_id: str, request: Request):
    token = request.headers.get("X-Session-Token")
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    data = await request.json()
    db_manager.save_guild_setting(guild_id, "all_settings", data)
    return {"status": "success"}

@app.post("/api/guilds/{guild_id}/trigger")
async def trigger_action(guild_id: str, request: Request, token: str = None):
    if not token or token not in SESSIONS: raise HTTPException(status_code=401)
    data = await request.json()
    action = data.get("action")
    
    settings = db_manager.get_guild_setting(guild_id, "all_settings", {})
    
    async with httpx.AsyncClient() as client:
        if action == "verification":
            chan_id = settings.get("verification_channel")
            if not chan_id: return {"error": "Verification channel not set"}
            
            payload = {
                "embeds": [{
                    "title": "🛡️ ACCOUNT VERIFICATION",
                    "description": (
                        "Welcome! To prevent automated bot accounts, we require all members to complete a quick verification check.\n\n"
                        "**How it Works:**\n"
                        "1️⃣ Click the **'Verify Myself'** button below.\n"
                        "2️⃣ A captcha image will appear.\n"
                        "3️⃣ Click **'Enter Code'** and type what you see.\n\n"
                        "*Need help? Contact a moderator.*"
                    ),
                    "color": 65280 # Green
                }],
                "components": [{
                    "type": 1,
                    "components": [{
                        "type": 2, "style": 3, "label": "Verify Myself", "custom_id": "verify_start_btn", "emoji": {"name": "🛡️"}
                    }]
                }]
            }
            res = await client.post(f"https://discord.com/api/v10/channels/{chan_id}/messages", 
                                   headers={"Authorization": f"Bot {BOT_TOKEN}"}, json=payload)
            return {"status": "success", "message": "DONE!"} if res.status_code == 200 else {"status": "failed"}

        if action == "roles":
            chan_id = settings.get("roles_channel") or settings.get("role_request_channel")
            if not chan_id: return {"error": "Roles channel not set"}
            
            async with httpx.AsyncClient() as client:
                # Fetch REAL roles from Discord to make it dynamic
                r_res = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers={"Authorization": f"Bot {BOT_TOKEN}"})
                if r_res.status_code != 200: return {"error": "Failed to fetch guild roles"}
                
                all_roles = r_res.json()
                # Filter out @everyone, bot roles, and managed roles
                valid_roles = [r for r in all_roles if r["name"] != "@everyone" and not r.get("managed", False)]
                # Take top 5 roles for the interactive menu (Discord limit per row)
                display_roles = valid_roles[:5]

                role_mentions = "\n".join([f"✨ <@&{r['id']}> - {r['name']}" for r in display_roles])
                
                payload = {
                    "embeds": [{
                        "title": "🎭 COMMUNITY SECTORS",
                        "description": (
                            "Select your sectors below to unlock restricted access and specialized channels.\n\n"
                            f"{role_mentions}\n\n"
                            "*Click buttons to toggle access.*"
                        ),
                        "color": 11468718 # Blurple
                    }],
                    "components": [
                        {
                            "type": 1,
                            "components": [
                                {"type": 2, "style": 2, "label": r["name"][:32], "custom_id": f"role_{r['id']}"} 
                                for r in display_roles
                            ]
                        }
                    ]
                }
                res = await client.post(f"https://discord.com/api/v10/channels/{chan_id}/messages", 
                                       headers={"Authorization": f"Bot {BOT_TOKEN}"}, json=payload)
                return {"status": "success", "message": "DONE!"} if res.status_code == 200 else {"status": "failed"}

    return {"error": "Invalid action"}


# --------------------------------------------------------------------------
# STATIC
# --------------------------------------------------------------------------
@app.get("/api/invite-url")
async def get_invite(guild_id: str = None):
    base_url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions=8&scope=bot%20applications.commands"
    if guild_id:
        base_url += f"&guild_id={guild_id}&disable_guild_select=true"
    return {"url": base_url}

app.mount("/dashboard", StaticFiles(directory=BASE_DIR / "dashboard"), name="dashboard")
@app.get("/{path:path}")
async def catch_all(path: str):
    p = BASE_DIR / path
    if p.is_file(): return FileResponse(p)
    return FileResponse(BASE_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
