"""Tests for app/max_listener.py — pure helper functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.max_client import MaxMessage
from app.max_listener import (
    _guess_media_kind,
    _has_forwardable_content,
    _human_size,
    _topic_title_for_message,
    create_max_client,
)


# ---------------------------------------------------------------------------
# _human_size
# ---------------------------------------------------------------------------

class TestHumanSize:
    """Tests for the _human_size byte-formatter."""

    # Byte range (< 1024)
    def test_zero_bytes(self):
        assert _human_size(0) == "0 Б"

    def test_single_byte(self):
        assert _human_size(1) == "1 Б"

    def test_max_bytes(self):
        assert _human_size(1023) == "1023 Б"

    # Kilobyte range (1024 – 1024²-1)
    def test_exact_one_kb(self):
        assert _human_size(1024) == "1.0 КБ"

    def test_fractional_kb(self):
        assert _human_size(1536) == "1.5 КБ"

    def test_large_kb(self):
        assert _human_size(1023 * 1024) == "1023.0 КБ"

    # Megabyte range
    def test_exact_one_mb(self):
        assert _human_size(1024 ** 2) == "1.0 МБ"

    def test_fractional_mb(self):
        assert _human_size(int(2.5 * 1024 ** 2)) == "2.5 МБ"

    def test_large_mb(self):
        assert _human_size(500 * 1024 ** 2) == "500.0 МБ"

    # Gigabyte range
    def test_exact_one_gb(self):
        assert _human_size(1024 ** 3) == "1.0 ГБ"

    def test_fractional_gb(self):
        assert _human_size(int(1.5 * 1024 ** 3)) == "1.5 ГБ"

    # Terabyte range (overflow past ГБ loop)
    def test_terabyte(self):
        result = _human_size(1024 ** 4)
        assert "ТБ" in result

    def test_large_terabyte(self):
        result = _human_size(5 * 1024 ** 4)
        assert result.startswith("5")
        assert "ТБ" in result

    # Return type
    def test_returns_string(self):
        assert isinstance(_human_size(42), str)


# ---------------------------------------------------------------------------
# _guess_media_kind
# ---------------------------------------------------------------------------

class TestGuessMediaKind:
    """Tests for the filename-to-media-kind classifier."""

    # Photo extensions
    def test_jpg_is_photo(self):
        assert _guess_media_kind("image.jpg") == "photo"

    def test_jpeg_is_photo(self):
        assert _guess_media_kind("photo.jpeg") == "photo"

    def test_png_is_photo(self):
        assert _guess_media_kind("screenshot.png") == "photo"

    def test_gif_is_photo(self):
        assert _guess_media_kind("anim.gif") == "photo"

    def test_webp_is_photo(self):
        assert _guess_media_kind("sticker.webp") == "photo"

    def test_bmp_is_photo(self):
        assert _guess_media_kind("old.bmp") == "photo"

    # Video extensions
    def test_mp4_is_video(self):
        assert _guess_media_kind("clip.mp4") == "video"

    def test_mov_is_video(self):
        assert _guess_media_kind("recording.mov") == "video"

    def test_avi_is_video(self):
        assert _guess_media_kind("video.avi") == "video"

    def test_mkv_is_video(self):
        assert _guess_media_kind("movie.mkv") == "video"

    def test_webm_is_video(self):
        assert _guess_media_kind("stream.webm") == "video"

    # Document / unknown extensions
    def test_pdf_is_document(self):
        assert _guess_media_kind("report.pdf") == "document"

    def test_zip_is_document(self):
        assert _guess_media_kind("archive.zip") == "document"

    def test_docx_is_document(self):
        assert _guess_media_kind("contract.docx") == "document"

    def test_txt_is_document(self):
        assert _guess_media_kind("notes.txt") == "document"

    def test_no_extension_is_document(self):
        assert _guess_media_kind("README") == "document"

    def test_empty_string_is_document(self):
        assert _guess_media_kind("") == "document"

    # Case-insensitivity
    def test_uppercase_jpg_is_photo(self):
        assert _guess_media_kind("PHOTO.JPG") == "photo"

    def test_mixed_case_mp4_is_video(self):
        assert _guess_media_kind("Video.MP4") == "video"

    def test_mixed_case_png_is_photo(self):
        assert _guess_media_kind("Image.PNG") == "photo"

    # Paths with directories
    def test_full_path_jpg(self):
        assert _guess_media_kind("/tmp/uploads/img.jpg") == "photo"

    def test_full_path_mp4(self):
        assert _guess_media_kind("/home/user/videos/clip.mp4") == "video"

    # Extension appearing in the middle of filename should not trigger false match
    def test_mp4_in_name_not_extension_is_document(self):
        assert _guess_media_kind("mp4_notes.txt") == "document"


# ---------------------------------------------------------------------------
# message forwarding filter
# ---------------------------------------------------------------------------

class TestForwardableContent:
    def test_empty_message_is_not_forwardable(self):
        assert _has_forwardable_content(MaxMessage()) is False

    def test_text_message_is_forwardable(self):
        assert _has_forwardable_content(MaxMessage(text="hello")) is True

    def test_control_only_message_is_not_forwardable(self):
        msg = MaxMessage(attaches=[{"_type": "CONTROL"}])
        assert _has_forwardable_content(msg) is False

    def test_media_message_is_forwardable(self):
        msg = MaxMessage(attaches=[{"_type": "PHOTO", "url": "http://example/img"}])
        assert _has_forwardable_content(msg) is True

    def test_forward_link_is_forwardable(self):
        msg = MaxMessage(link={"type": "FORWARD", "message": {"text": "inner"}})
        assert _has_forwardable_content(msg) is True


class TestTopicTitle:
    def test_dm_uses_sender_name(self):
        msg = MaxMessage(chat_id=42)
        assert _topic_title_for_message(msg, "Alice", "DM:7", True) == "Alice"

    def test_known_group_uses_chat_title(self):
        msg = MaxMessage(chat_id=-100)
        assert _topic_title_for_message(msg, "Alice", "Д/с", False) == "Д/с"

    def test_unknown_group_uses_numeric_placeholder_not_sender_name(self):
        msg = MaxMessage(chat_id=-100)
        assert _topic_title_for_message(msg, "Alice", "-100", False) == "-100"


class TestHandleMessage:
    async def test_empty_system_event_does_not_create_topic_or_send(self):
        sender = MagicMock()
        sender.send = AsyncMock()
        sender.ensure_topic = AsyncMock()
        sender.topic_store = MagicMock()
        sender.topic_store.get_topic.return_value = None

        client = create_max_client(
            max_token="tok",
            max_device_id="dev",
            sender=sender,
        )
        msg = MaxMessage(
            chat_id=-100,
            sender_id=42,
            raw={"chatId": -100, "message": {"sender": 42}},
        )

        await client._on_message_cb(msg)

        sender.ensure_topic.assert_not_called()
        sender.send.assert_not_called()

    async def test_group_message_uses_resolved_chat_title_for_topic(self):
        sender = MagicMock()
        sender.send = AsyncMock()
        sender.ensure_topic = AsyncMock(return_value=777)
        sender.topic_store = MagicMock()
        sender.topic_store.get_topic.return_value = None
        sender.topic_store.get_title.return_value = None

        client = create_max_client(
            max_token="tok",
            max_device_id="dev",
            sender=sender,
        )
        resolver = client.resolver
        resolver.resolve_chat = AsyncMock(return_value="Д/с")
        resolver.resolve_user = AsyncMock(return_value="Анастасия")
        resolver.chat_types[-100] = "GROUP"

        await client._on_message_cb(
            MaxMessage(chat_id=-100, sender_id=42, text="Добрый вечер")
        )

        sender.ensure_topic.assert_awaited_once_with(
            -100,
            "Д/с",
            force_rename=False,
        )

    async def test_existing_topic_named_like_user_is_renamed_to_group_title(self):
        sender = MagicMock()
        sender.send = AsyncMock()
        sender.ensure_topic = AsyncMock(return_value=777)
        sender.topic_store = MagicMock()
        sender.topic_store.get_topic.return_value = 777
        sender.topic_store.get_title.return_value = "Анастасия"

        client = create_max_client(
            max_token="tok",
            max_device_id="dev",
            sender=sender,
        )
        resolver = client.resolver
        resolver.resolve_chat = AsyncMock(return_value="Д/с")
        resolver.resolve_user = AsyncMock(return_value="Юлия Матвеева")
        resolver.chat_types[-100] = "GROUP"
        resolver.users[42] = "Анастасия"
        resolver.users[43] = "Юлия Матвеева"

        await client._on_message_cb(
            MaxMessage(chat_id=-100, sender_id=43, text="Здравствуйте")
        )

        sender.ensure_topic.assert_awaited_once_with(
            -100,
            "Д/с",
            force_rename=True,
        )
