from __future__ import annotations

from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
BRAND_DIR = ROOT / "custom_components" / "nutri_points" / "brand"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(path: Path) -> tuple[int, int]:
    image = path.read_bytes()
    assert image.startswith(PNG_SIGNATURE)
    assert image[12:16] == b"IHDR"
    return struct.unpack(">II", image[16:24])


def test_home_assistant_brand_icons_have_required_dimensions() -> None:
    assert _png_dimensions(BRAND_DIR / "icon.png") == (256, 256)
    assert _png_dimensions(BRAND_DIR / "icon@2x.png") == (512, 512)
