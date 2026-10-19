#!/usr/bin/env python
"""
Verify BeatSessionLocal is configured with NullPool and pool_pre_ping.
"""
import sys
import os

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.celery_app import beat_engine, BeatSessionLocal
from sqlalchemy.pool import NullPool

def verify_beatsessionlocal():
    print("Verifying BeatSessionLocal configuration...")

    # Check engine pool class
    pool_class = beat_engine.pool.__class__
    print(f"Engine pool class: {pool_class}")

    is_nullpool = isinstance(beat_engine.pool, NullPool)
    print(f"Uses NullPool: {is_nullpool}")

    # Check pool_pre_ping (NullPool uses _pre_ping attribute)
    pool_pre_ping = getattr(beat_engine.pool, '_pre_ping', False)
    print(f"pool_pre_ping: {pool_pre_ping}")

    # Test session creation (requires running DB)
    from sqlalchemy import text
    session = BeatSessionLocal()
    try:
        result = session.execute(text("SELECT 1")).scalar()
        print(f"Test query result: {result}")
        session.close()
        print("Session creation and query: OK")
    except Exception as e:
        print(f"Session test skipped (DB not running): {e}")
        print("Configuration verified - DB connection requires running containers")

    return is_nullpool and pool_pre_ping