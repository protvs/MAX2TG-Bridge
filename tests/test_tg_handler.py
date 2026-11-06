"""Tests for app/tg_handler.py — topic-based reply routing."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from app.tg_handler import (
    ALLOWED_USER_KEY,
    REPLY_ENABLED_KEY,
    MAX_CLIENT_KEY,
    TOPIC_STORE_KEY,
    _on_topic_message,
    _on_topic_media,
    _peer_id_in_dm,
    build_tg_app,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_topic_store(mapping: dict | None = None):
    """A TopicStore stand-in: chat_for_topic(thread_id) → max_chat_id."""
    mapping = mapping or {10: 42}
    store = MagicMock()
    store.chat_for_topic = MagicMock(side_effect=lambda tid: mapping.get(tid))
    return store


def _make_update(text="Hello", thread_id=10, is_topic_message=True, user_id=100):
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = text
    update.message.message_thread_id = thread_id
    update.message.is_topic_message = is_topic_message
    update.message.reply_text = AsyncMock()
    update.message.set_reaction = AsyncMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    return update


def _make_context(max_client=None, topic_store=None, allowed_user_id=None):
    ctx = MagicMock()
    bot_data = {ALLOWED_USER_KEY: allowed_user_id}
    if max_client is not None:
        bot_data[MAX_CLIENT_KEY] = max_client
    if topic_store is not None:
        bot_data[TOPIC_STORE_KEY] = topic_store
    ctx.bot_data = bot_data
    return ctx


# ---------------------------------------------------------------------------
# _peer_id_in_dm
# ---------------------------------------------------------------------------

class TestPeerIdInDm:
    def test_falls_back_to_positive_chat_id_when_participants_unknown(self):
        resolver = MagicMock()
        resolver.chats_raw = {}
        resolver.my_id = 1

        assert _peer_id_in_dm(resolver, 232221597) == 232221597

    def test_does_not_fall_back_to_negative_chat_id(self):
        resolver = MagicMock()
        resolver.chats_raw = {}
        resolver.my_id = 1

        assert _peer_id_in_dm(resolver, -78387493838230) is None


# ---------------------------------------------------------------------------
# _on_topic_message
# ---------------------------------------------------------------------------

class TestOnTopicMessage:
    @pytest.mark.parametrize("thread_id", [None, 1])
    @pytest.mark.parametrize("reply_enabled", [False, True])
    async def test_general_routes_to_favorites_obeys_reply_flag(self, thread_id, reply_enabled):
        client = MagicMock()
        client.send_message = AsyncMock(return_value={"ok": True})
        ctx = _make_context(max_client=client, topic_store=_make_topic_store())
        ctx.bot_data[REPLY_ENABLED_KEY] = reply_enabled
        update = _make_update("Saved text", thread_id=thread_id, is_topic_message=False)

        await _on_topic_message(update, ctx)

        if reply_enabled:
            client.send_message.assert_awaited_once_with(0, "Saved text", elements=[])
        else:
            client.send_message.assert_not_awaited()

    @pytest.mark.parametrize("bot_author, user_id", [(True, 100), (False, 999)])
    async def test_general_rejects_bot_or_unauthorized_user(self, bot_author, user_id):
        client = MagicMock()
        client.send_message = AsyncMock()
        ctx = _make_context(max_client=client, allowed_user_id=100)
        update = _make_update(thread_id=None, is_topic_message=False, user_id=user_id)
        update.message.from_user.is_bot = bot_author

        await _on_topic_message(update, ctx)

        client.send_message.assert_not_awaited()

    async def test_other_topics_keep_their_destination_with_favorites_enabled(self):
        client = MagicMock()
        client.send_message = AsyncMock(return_value={"ok": True})
        ctx = _make_context(max_client=client, topic_store=_make_topic_store({10: 42}))
        await _on_topic_message(_make_update(), ctx)

        client.send_message.assert_awaited_once_with(42, "Hello", elements=[])

    async def test_regular_topic_is_blocked_when_replies_disabled(self):
        client = MagicMock()
        client.send_message = AsyncMock()
        ctx = _make_context(max_client=client, topic_store=_make_topic_store({10: 42}))
        ctx.bot_data[REPLY_ENABLED_KEY] = False

        await _on_topic_message(_make_update(), ctx)

        client.send_message.assert_not_awaited()

    @pytest.mark.parametrize("kind", ["photo", "document"])
    @pytest.mark.parametrize("reply_enabled", [False, True])
    async def test_general_media_routes_to_favorites_obeys_reply_flag(self, kind, reply_enabled):
        client = MagicMock()
        client.send_message = AsyncMock(return_value={"ok": True})
        attach = {"_type": "PHOTO" if kind == "photo" else "FILE", "fileId": 123}
        client.upload_photo = AsyncMock(return_value=attach)
        client.upload_file = AsyncMock(return_value=attach)
        ctx = _make_context(max_client=client)
        ctx.bot_data[REPLY_ENABLED_KEY] = reply_enabled
        update = _make_update(thread_id=None, is_topic_message=False)
        message = update.message
        message.caption = "caption"
        message.caption_entities = []
        for field in ("photo", "voice", "audio", "document", "video"):
            setattr(message, field, None)
        media = MagicMock()
        media.file_name = "note.pdf"
        media.mime_type = "application/pdf"
        media.get_file = AsyncMock()
        media.get_file.return_value.download_as_bytearray = AsyncMock(return_value=b"data")
        setattr(message, kind, [media] if kind == "photo" else media)

        await _on_topic_media(update, ctx)

        if reply_enabled:
            client.send_message.assert_awaited_once_with(
                0, text="caption", elements=[], attaches=[attach],
            )
        else:
            client.send_message.assert_not_awaited()
            client.upload_photo.assert_not_awaited()
            client.upload_file.assert_not_awaited()
            media.get_file.assert_not_awaited()

    async def test_routes_topic_text_to_max(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock(return_value={"ok": True})

        update = _make_update("Hello", thread_id=10)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store({10: 42}))

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_called_once_with(42, "Hello", elements=[])

    async def test_reacts_on_success(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock(return_value={"ok": True})

        update = _make_update()
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store())

        await _on_topic_message(update, ctx)

        update.message.set_reaction.assert_called_once()

    async def test_ignores_general_topic_when_replies_disabled(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock()

        update = _make_update(thread_id=None, is_topic_message=False)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store())
        ctx.bot_data[REPLY_ENABLED_KEY] = False

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_not_called()

    async def test_ignores_unknown_topic(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock()

        update = _make_update(thread_id=999)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store({10: 42}))

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_not_called()

    async def test_ignores_empty_text(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock()

        update = _make_update(text=None)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store())

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_not_called()

    async def test_respects_allowed_user_id(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock()

        update = _make_update(user_id=555)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store(),
                            allowed_user_id=100)

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_not_called()

    async def test_allows_matching_user_id(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock(return_value={"ok": True})

        update = _make_update(user_id=100)
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store(),
                            allowed_user_id=100)

        await _on_topic_message(update, ctx)

        max_client.send_message.assert_called_once()

    async def test_warns_when_max_client_missing(self):
        update = _make_update()
        ctx = _make_context(topic_store=_make_topic_store())

        await _on_topic_message(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]

    async def test_warns_on_send_failure(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock(return_value=None)

        update = _make_update()
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store())

        await _on_topic_message(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]

    async def test_warns_on_exception(self):
        max_client = MagicMock()
        max_client.send_message = AsyncMock(side_effect=RuntimeError("boom"))

        update = _make_update()
        ctx = _make_context(max_client=max_client, topic_store=_make_topic_store())

        await _on_topic_message(update, ctx)

        update.message.reply_text.assert_called_once()
        assert "⚠️" in update.message.reply_text.call_args[0][0]


# ---------------------------------------------------------------------------
# build_tg_app
# ---------------------------------------------------------------------------

class TestBuildTgApp:
    def test_disabled_replies_flag_is_preserved_with_favorites(self):
        app = build_tg_app(
            "123456:AAABBBCCC", MagicMock(), "-100123456",
            _make_topic_store(), reply_enabled=False,
        )
        assert app.bot_data[REPLY_ENABLED_KEY] is False
        assert len(app.handlers[0]) == 2

    def test_wires_bot_data(self):
        max_client = MagicMock()
        topic_store = _make_topic_store()

        app = build_tg_app("123456:AAABBBCCC", max_client, "-100123456",
                            topic_store, allowed_user_id=777)

        assert app.bot_data[MAX_CLIENT_KEY] is max_client
        assert app.bot_data[TOPIC_STORE_KEY] is topic_store
        assert app.bot_data[ALLOWED_USER_KEY] == 777

    def test_allowed_user_id_none_when_unset(self):
        app = build_tg_app("123456:AAABBBCCC", MagicMock(), "-100123456",
                            _make_topic_store())

        assert app.bot_data[ALLOWED_USER_KEY] is None

    def test_registers_message_handler(self):
        app = build_tg_app("123456:AAABBBCCC", MagicMock(), "-100123456",
                            _make_topic_store())

        assert app.handlers[0]
