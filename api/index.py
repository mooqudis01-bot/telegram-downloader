import os
import sys
from pathlib import Path

# Add project root to sys.path for Vercel Serverless Function
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from app.web.server import app

__all__ = ["app"]
