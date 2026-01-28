
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
try:
    client = genai.Client(api_key=os.getenv("GEMINI_KEY"))
    print("Listing models...")
    for m in client.models.list(config={"page_size": 100}):
        print(f"Model: {m.name}")
except Exception as e:
    print(f"Error: {e}")
