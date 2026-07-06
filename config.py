import os
from dotenv import load_dotenv

load_dotenv()

PANEL_URL = os.getenv("PANEL_URL", "http://remnawave:3000").rstrip("/")
API_TOKEN = os.getenv("API_TOKEN", "")

AUTOROUTING_URL = os.getenv("AUTOROUTING_URL", "https://example.com/routing.json")
UPDATE_INTERVAL = int(os.getenv("UPDATE_INTERVAL_SECONDS", 21600))

TEMPLATE_PATH = os.getenv("TEMPLATE_PATH", "/app/template.json")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "/app/output/routing.json")