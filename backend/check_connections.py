import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load env variables
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=ROOT_DIR / ".env")
load_dotenv(dotenv_path=ROOT_DIR / "backend" / ".env")

sys.path.insert(0, str(ROOT_DIR))

import requests
from backend.config import settings
from backend.brokers.shoonya import shoonya_client
from backend.brokers.dhan import dhan_client

def main():
    print("================================================================")
    print("  Stock Pro India AI Terminal - Broker & Database Health Check")
    print("================================================================")

    # 1. Supabase Ping
    print("\n[1/3] Testing Supabase Database Connectivity...")
    sb_ok = False
    try:
        url = f"{settings.SUPABASE_URL}/rest/v1/network_table?select=id&limit=1"
        headers = {"apikey": settings.SUPABASE_KEY, "Authorization": f"Bearer {settings.SUPABASE_KEY}"}
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            print("  [PASS] Supabase: Connected to Cloud Database")
            sb_ok = True
        else:
            print(f"  [FAIL] Supabase: HTTP {r.status_code}")
    except Exception as e:
        print(f"  [FAIL] Supabase: {e}")

    # 2. Shoonya Connectivity
    print("\n[2/3] Testing Shoonya Finvasia Connectivity...")
    shoonya_res = shoonya_client.test_connection()
    shoonya_ok = shoonya_res.get("success", False)
    if shoonya_ok:
        print("  [PASS] Shoonya: Session Operational")
    else:
        print(f"  [STANDBY] Shoonya: {shoonya_res.get('error') or 'Session inactive'}")

    # 3. Dhan Connectivity
    print("\n[3/3] Testing Dhan HQ Open API v2 Connectivity...")
    dhan_res = dhan_client.test_connection()
    dhan_ok = dhan_res.get("success", False)
    if dhan_ok:
        print("  [PASS] Dhan HQ: Session Operational")
    else:
        print(f"  [STANDBY] Dhan HQ: {dhan_res.get('error') or 'Credentials not set'}")

    print("\n================================================================")
    print(f"  Summary: Supabase: {'PASS' if sb_ok else 'FAIL'} | Shoonya: {'PASS' if shoonya_ok else 'STANDBY'} | Dhan: {'PASS' if dhan_ok else 'STANDBY'}")
    print("================================================================")

if __name__ == "__main__":
    main()
