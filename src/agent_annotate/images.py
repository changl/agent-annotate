"""Image dimensions from file headers, with the standard library only.

Pages and finding proof lay out a current-vs-proposed pair by orientation
(decision #16): portrait (phone) shots sit side by side, landscape (desktop)
shots stack full width. Orientation is read once, when the file is stored,
from the PNG, GIF, JPEG or WebP header; nothing is decoded.
"""

from __future__ import annotations

import struct

# Types the review origin serves inline (sync_server._INLINE_UPLOADS, less PDF).
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MAX_IMAGE_BYTES = 10 * 1024 * 1024
LAYOUTS = ("side", "stack")


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from a PNG, GIF, JPEG or WebP header, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L" and data[20:21] == b"\x2f":
            bits = int.from_bytes(data[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if chunk == b"VP8X":
            return (int.from_bytes(data[24:27], "little") + 1,
                    int.from_bytes(data[27:30], "little") + 1)
        return None
    if data[:2] == b"\xff\xd8":
        i, turned = 2, False
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:              # fill byte
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\0\0":
                turned = _exif_orientation(data[i + 10:i + 2 + length]) in (5, 6, 7, 8)
            # SOF0-SOF15 carry the frame size; C4 (DHT), C8 and CC (DAC) do not.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                # Browsers apply EXIF rotation, so a quarter turn swaps the shown size.
                return (h, w) if turned else (w, h)
            i += 2 + length
    return None


def _exif_orientation(tiff: bytes) -> int | None:
    """The Orientation tag (0x0112) from IFD0 of an Exif TIFF block, else None."""
    order = {b"II": "<", b"MM": ">"}.get(tiff[:2])
    if not order or len(tiff) < 8:
        return None
    ifd = struct.unpack(order + "I", tiff[4:8])[0]
    if ifd + 2 > len(tiff):
        return None
    count = struct.unpack(order + "H", tiff[ifd:ifd + 2])[0]
    for k in range(count):
        entry = tiff[ifd + 2 + 12 * k:ifd + 14 + 12 * k]
        if len(entry) < 12:
            return None
        if struct.unpack(order + "H", entry[:2])[0] == 0x0112:
            return struct.unpack(order + "H", entry[8:10])[0]
    return None


def is_portrait(width: int, height: int) -> bool:
    """A phone-shaped shot: taller than it is wide."""
    return height > width


def layout_for(sizes: list[tuple[int, int] | None]) -> str:
    """`side` when every image is portrait, else `stack` (unknown sizes stack)."""
    return "side" if sizes and all(s and is_portrait(*s) for s in sizes) else "stack"
