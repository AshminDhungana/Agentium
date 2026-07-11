# backend/tests/unit/test_browser_lifespan.py
import os
from unittest.mock import AsyncMock, patch


def test_browser_service_initialize_called_when_enabled():
    import asyncio
    from backend.core import config

    # config.settings is the live Settings singleton; lifespan reads
    # settings.BROWSER_ENABLED, so patch the attribute on that instance.
    # get_browser_service is patched on its module so the lazy import inside
    # lifespan binds to the mock while the patch is active.
    # TESTING=true skips the heavy (DB/Chroma/idle-governance) boot steps; we
    # also stub init_db so no live database is required for this unit test.
    with patch.object(config.settings, "BROWSER_ENABLED", True), \
         patch("backend.services.browser_service.get_browser_service") as gbs, \
         patch("backend.main.init_db") as mock_init_db, \
         patch.dict(os.environ, {"TESTING": "true"}):
        svc = gbs.return_value
        svc.initialize = AsyncMock()
        svc.shutdown = AsyncMock()
        import backend.main as m
        from backend.main import lifespan

        async def fake():
            async with lifespan(m.app):
                pass

        asyncio.run(fake())
        mock_init_db.assert_called_once()
        svc.initialize.assert_awaited_once()
        svc.shutdown.assert_awaited_once()
