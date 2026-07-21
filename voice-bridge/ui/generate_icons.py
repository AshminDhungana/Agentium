"""Generate tray icons for the voice bridge UI."""
import struct
import zlib
import os


def _create_png(width: int, height: int, pixels: list) -> bytes:
    """Create a minimal PNG from RGBA pixel data (list of (r,g,b,a) tuples)."""
    raw = b""
    for y in range(height):
        raw += b"\x00"
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += bytes([r, g, b, a])

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _mic_pixels(size: int, color: tuple) -> list:
    """Generate RGBA pixel data for a simple microphone icon."""
    pixels = [(0, 0, 0, 0)] * (size * size)
    cx, cy = size // 2, size // 2
    r = size * 0.3
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy

            body_left = int(cx - r * 0.5)
            body_right = int(cx + r * 0.5)
            body_top = int(cy - r * 1.2)
            body_bottom = int(cy + r * 0.2)

            if body_left <= x <= body_right and body_top <= y <= body_bottom:
                rel_y = (y - body_top) / (body_bottom - body_top)
                capsule_r = r * 0.5 * (1 - rel_y * 0.3)
                if abs(dx) < capsule_r:
                    pixels[y * size + x] = color

            stand_x = cx
            if abs(x - stand_x) < 2 and cy + r * 0.2 <= y <= cy + r * 0.7:
                pixels[y * size + x] = color

            base_y = int(cy + r * 0.7)
            if abs(y - base_y) < 2 and abs(dx) < r * 0.6:
                pixels[y * size + x] = color

    return pixels


def generate_icons():
    out_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(out_dir, exist_ok=True)

    size = 32
    blue = (59, 130, 246, 255)
    white = (255, 255, 255, 255)
    green = (34, 197, 94, 255)

    icons = {
        "tray_idle.png": _mic_pixels(size, blue),
        "tray_listening.png": _mic_pixels(size, green),
        "tray_speaking.png": _mic_pixels(size, white),
    }

    for name, pixels in icons.items():
        png = _create_png(size, size, pixels)
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(png)
        print(f"Created {name}")


if __name__ == "__main__":
    generate_icons()
