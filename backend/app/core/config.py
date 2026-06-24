"""
Central configuration. Loads the .env file once and exposes all settings, so
the rest of the app never reads environment variables directly.

Importing this module is what loads .env -- import it before anything that needs
config (main.py does this first).
"""

import os
from pathlib import Path
from dotenv import load_dotenv, find_dotenv

# Load .env -- search upward from the current working directory so it works
# whether you run from backend/ or the repo root.
_dotenv = find_dotenv(usecwd=True)
if _dotenv:
    load_dotenv(_dotenv)

# backend/ directory (this file is backend/app/core/config.py -> parents[2])
BACKEND_DIR = Path(__file__).resolve().parents[2]

# ---- LLM (Ollama / Qwen) ----
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
CHAT_MODEL = os.getenv("CHAT_MODEL", "qwen2.5:7b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# ---- Vector store (kept under backend/ so it's predictable) ----
CHROMA_PATH = str(BACKEND_DIR / "chroma_db")

# ---- Supabase (read lazily in tools/db.py; surfaced here for visibility) ----
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
