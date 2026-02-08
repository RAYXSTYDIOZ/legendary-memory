from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
import httpx
import os
from dotenv import load_dotenv
from database import db_manager
import logging
import psutil
import time
import brain

load_dotenv()

# Track start time for uptime
START_TIME = time.time()

# Discord Configuration
CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8000/callback")
SESSION_SECRET = os.getenv("SESSION_SECRET", "super-secret-prime-key")

app = FastAPI(title="Prime AI Dashboard API")

# Middleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=SESSION_SECRET,
    session_cookie="prime_session"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dashboard_server")

@app.get("/")
async def root():
    return FileResponse("index.html")

@app.get("/index.html")
async def index():
    return FileResponse("index.html")

@app.get("/terms.html")
async def terms():
    return FileResponse("terms.html")

@app.get("/privacy.html")
async def privacy():
    return FileResponse("privacy.html")

@app.get("/landing.css")
async def landing_css():
    return FileResponse("landing.css")

@app.get("/logo.png")
async def logo_png():
    return FileResponse("logo.png")

@app.get("/status.html")
async def status_page():
    return FileResponse("status.html")

@app.get("/playground.html")
async def playground_page():
    return FileResponse("playground.html")

@app.get("/login")
async def login():
    if not CLIENT_ID:
        return JSONResponse({"error": "DISCORD_CLIENT_ID not configured in .env"}, status_code=500)
    
    discord_auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify%20guilds"
    )
    return RedirectResponse(discord_auth_url)

@app.get("/callback")
async def callback(request: Request, code: str):
    if not code:
        raise HTTPException(status_code=400, detail="Missing code")

    async with httpx.AsyncClient() as client:
        # Exchange code for token
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        response = await client.post("https://discord.com/api/oauth2/token", data=data, headers=headers)
        if response.status_code != 200:
            logger.error(f"Failed to exchange code: {response.text}")
            return JSONResponse({"error": "Failed to login with Discord"}, status_code=response.status_code)
        
        token_data = response.json()
        access_token = token_data.get("access_token")

        # Get user info
        user_headers = {"Authorization": f"Bearer {access_token}"}
        user_response = await client.get("https://discord.com/api/users/@me", headers=user_headers)
        
        if user_response.status_code != 200:
            return JSONResponse({"error": "Failed to fetch user info"}, status_code=user_response.status_code)
        
        user_info = user_response.json()

        # Get user guilds
        guilds_response = await client.get("https://discord.com/api/users/@me/guilds", headers=user_headers)
        guilds = guilds_response.json() if guilds_response.status_code == 200 else []
        
        # Store in session
        request.session["user"] = user_info
        request.session["guilds"] = guilds
        
        # Redirect back to dashboard
        return RedirectResponse(url="/dashboard/index.html")

@app.get("/api/me")
async def get_me(request: Request):
    user = request.session.get("user")
    if not user:
        return JSONResponse({"authenticated": False}, status_code=401)
    
    user_id = int(user["id"])
    guilds = request.session.get("guilds", [])
    
    # Enrich with database info
    memory = db_manager.get_user_memory(user_id)
    levels = db_manager.get_levels().get(user_id, {"xp": 0, "level": 0})
    notes = db_manager.get_notes(user_id)
    
    return {
        "authenticated": True,
        "discord": user,
        "guilds": guilds,
        "internal": {
            "memory": memory,
            "levels": levels,
            "notes_count": len(notes)
        }
    }

@app.get("/api/stats")
async def get_stats():
    # Real system stats
    process = psutil.Process(os.getpid())
    
    # Calculate uptime
    uptime_seconds = int(time.time() - START_TIME)
    
    # System stats
    cpu_usage = psutil.cpu_percent()
    ram_usage = psutil.virtual_memory().percent
    
    # DB stats
    levels = db_manager.get_levels()
    total_users = len(levels)
    
    return {
        "total_users": total_users,
        "system_status": "ONLINE",
        "cpu_load": cpu_usage,
        "ram_usage": ram_usage,
        "uptime_seconds": uptime_seconds,
        "process_id": os.getpid()
    }

@app.post("/api/chat")
async def api_chat(request: Request):
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        user_id = data.get("user_id", 999) # Default for playground
        username = data.get("username", "Guest")

        if not message:
            return JSONResponse({"error": "Message is empty"}, status_code=400)

        # Basic command handling for the playground
        if message.startswith("!"):
            cmd = message.split(" ")[0].lower()
            if cmd == "!vibe":
                res = random.choice([
                    "the grid is pulsing with elite energy right now.",
                    "keep your focus sharp. the architecture depends on it.",
                    "current vibe: ultra-silver and high-performance."
                ])
                return {"response": res}
            elif cmd == "!roast":
                target = message.split(" ")[1] if len(message.split(" ")) > 1 else "you"
                res = f"roasting {target}... stay tuned for the burn."
                # Call gemini for a real roast
                prompt = f"Roast this person/thing: {target}. Be savage but elite. No robot talk."
                res = await brain.get_gemini_response(prompt, user_id, username=username)
                return {"response": res}
            elif cmd == "!help":
                return {"response": "Available playground protocols: !vibe, !roast, !help, or just chat naturally with Prime."}

        # Otherwise, regular chat
        response = await brain.get_gemini_response(message, user_id, username=username)
        return {"response": response}

    except Exception as e:
        logger.error(f"Chat API Error: {e}")
        return JSONResponse({"response": "System Error: Failed to process neural link."}, status_code=500)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/dashboard/index.html")

# Serve the dashboard files
app.mount("/dashboard", StaticFiles(directory="dashboard"), name="dashboard")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
