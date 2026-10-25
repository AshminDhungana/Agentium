import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.celery_app import beat_engine
from sqlalchemy.pool import NullPool

print(f'Pool class: {beat_engine.pool.__class__}')
print(f'Is NullPool: {isinstance(beat_engine.pool, NullPool)}')
attrs = [x for x in dir(beat_engine.pool) if not x.startswith('_')]
print(f'Pool attrs: {attrs}')
print(f'Has _pre_ping: {hasattr(beat_engine.pool, "_pre_ping")}')
print(f'Has _pool_pre_ping: {hasattr(beat_engine.pool, "_pool_pre_ping")}')
if hasattr(beat_engine.pool, '_pre_ping'):
    print(f'_pre_ping: {beat_engine.pool._pre_ping}')
if hasattr(beat_engine.pool, '_pool_pre_ping'):
    print(f'_pool_pre_ping: {beat_engine.pool._pool_pre_ping}')