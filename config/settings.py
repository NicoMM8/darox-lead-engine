import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables
load_dotenv(BASE_DIR / ".env")

# Data directories
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# Google Places API
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip()

# Database Path
DB_PATH = BASE_DIR / os.getenv("DB_PATH", "data/places_store.db")

# Output CSV files
CSV_BORME_OUTPUT = BASE_DIR / os.getenv("CSV_BORME_OUTPUT", "data/leads_borme_enriquecidos.csv")
CSV_PLACES_OUTPUT = BASE_DIR / os.getenv("CSV_PLACES_OUTPUT", "data/leads_google_places.csv")

# Filter provinces for BORME (empty list means all provinces)
raw_provinces = os.getenv("BORME_PROVINCES", "")
BORME_PROVINCES = [p.strip().upper() for p in raw_provinces.split(",") if p.strip()]

# HTTP headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

# Domains to test in OSINT module
TARGET_TLDS = [".es", ".com"]

