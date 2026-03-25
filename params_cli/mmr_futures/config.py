"""Configuration for exchange API keys (only needed for Binance)."""

import os
from dotenv import load_dotenv

load_dotenv()

BINANCE_API_KEY = os.environ.get("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
