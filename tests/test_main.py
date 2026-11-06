"""Startup of Telegram to MAX routing under the shared reply flag."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from app import main as entrypoint


@pytest.mark.parametrize(
    "reply_enabled,expect_polling", [(False, False), (True, True)],
)
async def test_telegram_polling_routes(
    monkeypatch, reply_enabled, expect_polling,
):
    settings = Settings(
        max_token="tok", max_device_id="dev", tg_bot_token="bot", tg_chat_id="-100",
        reply_enabled=reply_enabled,
    )
    monkeypatch.setattr(entrypoint, "load_settings", lambda: settings)
    monkeypatch.setattr(entrypoint.os, "makedirs", MagicMock())
    monkeypatch.setattr(entrypoint, "RotatingFileHandler", MagicMock())
    monkeypatch.setattr(entrypoint.logging, "basicConfig", MagicMock())
    monkeypatch.setattr(entrypoint.asyncio, "get_running_loop", MagicMock())
    monkeypatch.setattr(entrypoint, "TopicStore", MagicMock())

    sender = MagicMock(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(entrypoint, "TelegramSender", MagicMock(return_value=sender))
    client = MagicMock(run=AsyncMock())
    create_client = MagicMock(return_value=client)
    monkeypatch.setattr(entrypoint, "create_max_client", create_client)
    tg_app = MagicMock(
        initialize=AsyncMock(), start=AsyncMock(), stop=AsyncMock(), shutdown=AsyncMock(),
    )
    tg_app.updater.start_polling = AsyncMock()
    tg_app.updater.stop = AsyncMock()
    build_app = MagicMock(return_value=tg_app)
    monkeypatch.setattr(entrypoint, "build_tg_app", build_app)
    runner = MagicMock(cleanup=AsyncMock())
    monkeypatch.setattr(entrypoint, "start_health_server", AsyncMock(return_value=runner))

    await entrypoint.main()

    assert build_app.called is expect_polling
    if expect_polling:
        assert build_app.call_args.kwargs["reply_enabled"] is reply_enabled
        tg_app.updater.start_polling.assert_awaited_once()
        tg_app.shutdown.assert_awaited_once()
    else:
        tg_app.updater.start_polling.assert_not_awaited()
    sender.stop.assert_awaited_once()
    runner.cleanup.assert_awaited_once()
