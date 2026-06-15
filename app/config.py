"""
Unified configuration module for Mini Foundry Ontology Runtime.

Loads settings from environment variables and .env file via python-dotenv.
No secrets are hardcoded — all sensitive values come from the environment.
"""

import os
from dotenv import load_dotenv

# Load .env from the project root (parent of app/).
# If .env is absent, load_dotenv silently returns False — the app still starts.
load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/mini_foundry.db")

DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

APP_ENV: str = os.getenv("APP_ENV", "development")

# Convenience flag
IS_DEVELOPMENT: bool = APP_ENV == "development"
