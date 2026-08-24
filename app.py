"""
app.py - FastAPI Application Entry Point
Telegram Downloader API & Web GUI
"""

import os
import sys
from pathlib import Path

root_dir = Path(__file__).parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from app.web.server import app

__all__ = ["app"]
