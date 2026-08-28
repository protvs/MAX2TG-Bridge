import logging
import os

from aiohttp import web

log = logging.getLogger(__name__)


async def start_health_server(max_client):
    host = os.environ.get("HEALTH_HOST", "0.0.0.0")
    port_raw = os.environ.get("HEALTH_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise SystemExit(f"HEALTH_PORT must be an integer, got: {port_raw!r}") from exc

    async def health(_request):
        connected = max_client.is_connected
        payload = {
            "status": "ok" if connected else "degraded",
            "max": "connected" if connected else "disconnected",
        }
        return web.json_response(payload, status=200 if connected else 503)

    app = web.Application()
    app.router.add_get("/health", health)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    log.info("Health endpoint listening on http://%s:%d/health", host, port)
    return runner
