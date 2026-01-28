
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_KEY"))

print("Listing models...")
for model in client.models.list():
    print(f"- {model.name}")
