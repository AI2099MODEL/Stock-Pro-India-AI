import sys
import os

# Add parent directory to sys.path so backend imports work seamlessly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import app

# Vercel serverless handler entrypoint
handler = app
