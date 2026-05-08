"""Unit tests for security validations in main.py — no API keys required."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import ALLOWED_MEDIA_TYPES


class TestMediaTypeValidation:
    def test_png_allowed(self):
        assert "image/png" in ALLOWED_MEDIA_TYPES

    def test_jpeg_allowed(self):
        assert "image/jpeg" in ALLOWED_MEDIA_TYPES

    def test_webp_allowed(self):
        assert "image/webp" in ALLOWED_MEDIA_TYPES

    def test_gif_allowed(self):
        assert "image/gif" in ALLOWED_MEDIA_TYPES

    def test_html_not_allowed(self):
        assert "text/html" not in ALLOWED_MEDIA_TYPES

    def test_pdf_not_allowed(self):
        assert "application/pdf" not in ALLOWED_MEDIA_TYPES

    def test_arbitrary_string_not_allowed(self):
        assert "anything/goes" not in ALLOWED_MEDIA_TYPES
