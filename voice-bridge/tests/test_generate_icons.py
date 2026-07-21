import sys
import os
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..")
    ),
)


class TestGenerateIcons:
    def test_mic_pixels_returns_correct_length(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(32, (59, 130, 246, 255))
        assert len(pixels) == 32 * 32

    def test_mic_pixels_all_blue_pixels_have_alpha(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(32, (59, 130, 246, 255))
        for p in pixels:
            if p[3] > 0:
                assert p[0] == 59
                assert p[1] == 130
                assert p[2] == 246
                assert p[3] == 255

    def test_mic_pixels_different_color(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(32, (34, 197, 94, 255))
        has_green = False
        for p in pixels:
            if p[3] > 0:
                assert p[0] == 34
                assert p[1] == 197
                assert p[2] == 94
                has_green = True
        assert has_green, "expected at least one non-transparent green pixel"

    def test_mic_pixels_white(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(32, (255, 255, 255, 255))
        has_white = False
        for p in pixels:
            if p[3] > 0:
                assert p[0] == 255
                assert p[1] == 255
                assert p[2] == 255
                has_white = True
        assert has_white, "expected at least one non-transparent white pixel"

    def test_mic_pixels_size_16_works(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(16, (59, 130, 246, 255))
        assert len(pixels) == 16 * 16

    def test_mic_pixels_size_48_works(self):
        from ui.generate_icons import _mic_pixels

        pixels = _mic_pixels(48, (59, 130, 246, 255))
        assert len(pixels) == 48 * 48

    def test_create_png_returns_valid_png(self):
        from ui.generate_icons import _create_png

        pixels = [(255, 0, 0, 255)] * (4 * 4)
        png = _create_png(4, 4, pixels)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_create_png_contains_required_chunks(self):
        from ui.generate_icons import _create_png

        pixels = [(0, 0, 0, 0)] * (2 * 2)
        png = _create_png(2, 2, pixels)
        assert b"IHDR" in png
        assert b"IDAT" in png
        assert b"IEND" in png

    def test_create_png_different_sizes(self):
        from ui.generate_icons import _create_png

        for size in [1, 2, 4, 8, 16]:
            pixels = [(0, 0, 0, 0)] * (size * size)
            png = _create_png(size, size, pixels)
            assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_generate_icons_creates_files(self, tmp_path):
        from ui.generate_icons import generate_icons

        assets_dir = tmp_path / "assets"
        assets_dir.mkdir(exist_ok=True)

        with patch("ui.generate_icons.os.path.dirname", return_value=str(tmp_path)):
            generate_icons()

        assert (assets_dir / "tray_idle.png").exists()
        assert (assets_dir / "tray_listening.png").exists()
        assert (assets_dir / "tray_speaking.png").exists()

    def test_generated_pngs_have_correct_dimensions(self, tmp_path):
        import struct

        from ui.generate_icons import _mic_pixels, _create_png

        def read_png_size(png_bytes):
            ihdr_start = png_bytes.find(b"IHDR") + 4
            w, h = struct.unpack(">II", png_bytes[ihdr_start : ihdr_start + 8])
            return w, h

        size = 32
        for color in [(59, 130, 246, 255), (34, 197, 94, 255), (255, 255, 255, 255)]:
            pixels = _mic_pixels(size, color)
            png = _create_png(size, size, pixels)
            w, h = read_png_size(png)
            assert w == size
            assert h == size
