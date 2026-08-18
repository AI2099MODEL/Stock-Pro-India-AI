import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if present
ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)

class Settings:
    PROJECT_NAME: str = "Stock Pro India Terminal"
    VERSION: str = "3.0.0-ENTERPRISE"
    
    # AI Engine Config
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    # Supabase Configuration
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "https://gshiddtlkiihwnxvxzle.supabase.co")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "sb_publishable_pXsCDcMoReEqNlJ-reXpdg__5ibKw-F")
    
    # Trading & Risk Defaults
    INITIAL_BALANCE: float = float(os.getenv("INITIAL_BALANCE", "500000.0"))
    DEFAULT_SYMBOL: str = os.getenv("DEFAULT_SYMBOL", "NIFTY 50")
    DEFAULT_LEVERAGE: int = int(os.getenv("DEFAULT_LEVERAGE", "5"))
    AUTO_TRADING_ENABLED: bool = False  # Safe default: disabled
    DEFAULT_TRADING_MODE: str = os.getenv("DEFAULT_TRADING_MODE", "PAPER")
    MAX_RISK_PER_TRADE_PCT: float = float(os.getenv("MAX_RISK_PER_TRADE_PCT", "2.0"))
    MAX_DAILY_LOSS_INR: float = float(os.getenv("MAX_DAILY_LOSS_INR", "10000.0"))
    MIN_CONFIDENCE_THRESHOLD: float = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "70.0"))
    
    # Broker Server-Side Credentials (NEVER exposed to frontend)
    SHOONYA_UID: str = os.getenv("SHOONYA_UID", "")
    SHOONYA_ACTID: str = os.getenv("SHOONYA_ACTID", "")
    SHOONYA_CLIENT_ID: str = os.getenv("SHOONYA_CLIENT_ID", "")
    SHOONYA_PROXY_URL: str = os.getenv("SHOONYA_PROXY_URL", os.getenv("HTTPS_PROXY", ""))
    
    DHAN_CLIENT_ID: str = os.getenv("DHAN_CLIENT_ID", "")
    DHAN_ACCESS_TOKEN: str = os.getenv("DHAN_ACCESS_TOKEN", "")

settings = Settings()
