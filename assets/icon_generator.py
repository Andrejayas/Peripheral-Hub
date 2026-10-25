"""
assets/icon_generator.py
Generate PNG icons for Peripheral Hub using Pillow.
Icons: tray, mouse, keyboard, headset — in dark-theme accent colors.
Run this script directly to (re)generate all icons.
"""

import math
from pathlib import Path
from typing import Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("Pillow not installed. Run: pip install Pillow")

# Output directory = same folder as this script
ASSETS_DIR = Path(__file__).parent

# Color palette
BG_COLOR        = (26, 26, 26, 0)       # transparent background
ACCENT          = (226, 99, 50, 255)    # #e26332 orange
WHITE           = (255, 255, 255, 255)
GRAY            = (136, 136, 136, 255)  # #888888
GREEN           = (76, 175, 80, 255)    # #4caf50
ORANGE_BATT     = (255, 152, 0, 255)    # #ff9800
RED_BATT        = (244, 67, 54, 255)    # #f44336

ICON_SIZE = (64, 64)
TRAY_SIZE = (32, 32)


def _new_canvas(size: Tuple[int, int] = ICON_SIZE) -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    return img, draw


def _draw_rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width=2):
    """Draw a rounded rectangle."""
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle([x0, y0, x1, y1], radius=radius, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------------------
# Individual icon generators
# ---------------------------------------------------------------------------

def generate_mouse_icon(size: Tuple[int, int] = ICON_SIZE, color=ACCENT) -> Image.Image:
    """Draw a stylized gaming mouse silhouette."""
    img, draw = _new_canvas(size)
    W, H = size
    cx = W // 2

    # Mouse body (rounded rectangle)
    bx0, bx1 = int(W * 0.25), int(W * 0.75)
    by0, by1 = int(H * 0.15), int(H * 0.88)
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(W * 0.18), fill=color)

    # Scroll wheel
    sw = int(W * 0.08)
    sh = int(H * 0.22)
    sx0 = cx - sw // 2
    sy0 = int(H * 0.22)
    draw.rounded_rectangle([sx0, sy0, sx0 + sw, sy0 + sh],
                            radius=2, fill=(0, 0, 0, 200))

    # Left/right button divider
    draw.line([(cx, by0 + 2), (cx, by0 + int(H * 0.38))],
              fill=(0, 0, 0, 180), width=2)

    return img


def generate_keyboard_icon(size: Tuple[int, int] = ICON_SIZE, color=ACCENT) -> Image.Image:
    """Draw a stylized keyboard silhouette."""
    img, draw = _new_canvas(size)
    W, H = size

    # Keyboard body
    kx0, kx1 = int(W * 0.08), int(W * 0.92)
    ky0, ky1 = int(H * 0.28), int(H * 0.78)
    draw.rounded_rectangle([kx0, ky0, kx1, ky1], radius=6, fill=color)

    # Key rows (3 rows of keys)
    key_colors = (0, 0, 0, 160)
    key_w = int(W * 0.09)
    key_h = int(H * 0.10)
    gap = int(W * 0.04)

    for row in range(3):
        n_keys = 8 - row
        total_w = n_keys * key_w + (n_keys - 1) * gap
        start_x = (W - total_w) // 2 + row * int(W * 0.04)
        row_y = ky0 + int(H * 0.06) + row * (key_h + gap)
        for k in range(n_keys):
            kx = start_x + k * (key_w + gap)
            draw.rounded_rectangle([kx, row_y, kx + key_w, row_y + key_h],
                                    radius=2, fill=key_colors)

    # Spacebar
    sb_w = int(W * 0.50)
    sb_h = key_h
    sb_x = (W - sb_w) // 2
    sb_y = ky1 - int(H * 0.06) - sb_h
    draw.rounded_rectangle([sb_x, sb_y, sb_x + sb_w, sb_y + sb_h],
                            radius=2, fill=key_colors)

    return img


def generate_headset_icon(size: Tuple[int, int] = ICON_SIZE, color=ACCENT) -> Image.Image:
    """Draw a headset/headphone silhouette."""
    img, draw = _new_canvas(size)
    W, H = size
    cx = W // 2

    # Headband arc
    band_box = [int(W * 0.10), int(H * 0.08), int(W * 0.90), int(H * 0.65)]
    draw.arc(band_box, start=180, end=0, fill=color, width=int(W * 0.12))

    # Left ear cup
    lx, ly = int(W * 0.08), int(H * 0.48)
    draw.ellipse([lx, ly, lx + int(W * 0.22), ly + int(H * 0.30)], fill=color)

    # Right ear cup
    rx = W - lx - int(W * 0.22)
    draw.ellipse([rx, ly, rx + int(W * 0.22), ly + int(H * 0.30)], fill=color)

    # Mic boom (left side)
    mic_x0 = lx + int(W * 0.08)
    mic_y0 = ly + int(H * 0.25)
    draw.line([(mic_x0, mic_y0), (mic_x0 - int(W * 0.06), mic_y0 + int(H * 0.18))],
              fill=color, width=3)
    # Mic capsule
    draw.ellipse([mic_x0 - int(W * 0.12), mic_y0 + int(H * 0.14),
                  mic_x0 - int(W * 0.01), mic_y0 + int(H * 0.26)],
                 fill=color)

    return img


def generate_tray_icon(battery_color=GREEN,
                       size: Tuple[int, int] = TRAY_SIZE) -> Image.Image:
    """
    Generate the system-tray icon: a small headphone/controller symbol
    with a colored status dot indicating overall battery health.
    """
    img, draw = _new_canvas(size)
    W, H = size

    # Simple headphone arc
    band_box = [int(W * 0.12), int(H * 0.08), int(W * 0.88), int(H * 0.65)]
    draw.arc(band_box, start=180, end=0, fill=ACCENT, width=max(2, int(W * 0.14)))

    # Ear pads
    pad_w = int(W * 0.20)
    pad_h = int(H * 0.28)
    lx = int(W * 0.10)
    rx = W - lx - pad_w
    py = int(H * 0.45)
    draw.ellipse([lx, py, lx + pad_w, py + pad_h], fill=ACCENT)
    draw.ellipse([rx, py, rx + pad_w, py + pad_h], fill=ACCENT)

    # Battery status dot (bottom-right)
    dot_r = max(3, int(W * 0.18))
    dx = W - dot_r - 1
    dy = H - dot_r - 1
    draw.ellipse([dx - dot_r, dy - dot_r, dx + dot_r, dy + dot_r],
                 fill=battery_color)

    return img


def generate_battery_ring(percent: int, size: int = 64,
                           fg_color=GREEN, bg_color=(50, 50, 50, 255)) -> Image.Image:
    """
    Generate a circular battery ring gauge for the mouse card.
    percent: 0-100
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = size // 2
    r = size // 2 - 4
    ring_w = max(3, size // 10)

    # Background ring
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=0, end=360,
             fill=bg_color, width=ring_w)

    # Foreground arc (progress), start at top (-90°)
    end_angle = -90 + (360 * percent / 100)
    if percent > 0:
        draw.arc([cx - r, cy - r, cx + r, cy + r],
                 start=-90, end=end_angle,
                 fill=fg_color, width=ring_w)

    # Center text
    pct_text = f"{percent}%"
    # Use default bitmap font (no TTF needed)
    try:
        from PIL import ImageFont
        font = ImageFont.load_default()
        bbox = font.getbbox(pct_text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), pct_text,
                  fill=WHITE, font=font)
    except Exception:
        pass

    return img


# ---------------------------------------------------------------------------
# Main generator entry point
# ---------------------------------------------------------------------------

def generate_all() -> None:
    """Generate all icon files and save to the assets directory."""
    if not PILLOW_AVAILABLE:
        print("Pillow not available — skipping icon generation.")
        return

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    icons = {
        "icon_mouse.png":    generate_mouse_icon(),
        "icon_keyboard.png": generate_keyboard_icon(),
        "icon_headset.png":  generate_headset_icon(),
        "icon_tray.png":     generate_tray_icon(battery_color=GREEN),
        "icon_tray_ok.png":  generate_tray_icon(battery_color=GREEN),
        "icon_tray_warn.png": generate_tray_icon(battery_color=ORANGE_BATT),
        "icon_tray_low.png": generate_tray_icon(battery_color=RED_BATT),
    }

    for filename, img in icons.items():
        out_path = ASSETS_DIR / filename
        img.save(str(out_path), "PNG")
        print(f"Saved: {out_path}")

    print(f"\nAll {len(icons)} icons generated in: {ASSETS_DIR}")


if __name__ == "__main__":
    generate_all()
