"""
tray.py
TrayIcon - Windows system tray icon for Peripheral Hub.
Uses pystray for the icon + right-click menu.
Icon color reflects overall device battery health:
  Green  = all devices > 50%
  Orange = any device 20-50%
  Red    = any device < 20%
"""

import logging
import threading
from pathlib import Path
from typing import Optional, Callable, Any

try:
    import pystray
    from pystray import MenuItem as item, Menu
    PYSTRAY_OK = True
except ImportError:
    PYSTRAY_OK = False

try:
    from PIL import Image
    PILLOW_OK = True
except ImportError:
    PILLOW_OK = False

logger = logging.getLogger(__name__)

# Battery color thresholds
THRESHOLD_GREEN  = 50
THRESHOLD_ORANGE = 20

# Colors as (R, G, B, A)
COLOR_GREEN  = (76, 175, 80, 255)
COLOR_ORANGE = (255, 152, 0, 255)
COLOR_RED    = (244, 67, 54, 255)
COLOR_ACCENT = (226, 99, 50, 255)
COLOR_DARK   = (36, 36, 36, 255)

ASSETS_DIR = Path(__file__).parent / "assets"


class TrayIcon:
    """
    Manages the Windows system tray icon and its context menu.
    Runs pystray in its own daemon thread.
    """

    def __init__(self,
                 on_open_dashboard: Optional[Callable] = None,
                 on_scan_devices: Optional[Callable] = None,
                 on_eq_profile: Optional[Callable[[str], None]] = None,
                 on_exit: Optional[Callable] = None):
        self._on_open_dashboard = on_open_dashboard
        self._on_scan_devices = on_scan_devices
        self._on_eq_profile = on_eq_profile
        self._on_exit = on_exit

        self._icon: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._current_color = "green"

        self._images = self._load_or_generate_images()

    def _load_or_generate_images(self) -> dict:
        if not PILLOW_OK:
            return {}

        images = {}
        color_map = {
            "green":  ("icon_tray_ok.png",   COLOR_GREEN),
            "orange": ("icon_tray_warn.png",  COLOR_ORANGE),
            "red":    ("icon_tray_low.png",   COLOR_RED),
        }
        for key, (filename, color) in color_map.items():
            path = ASSETS_DIR / filename
            if path.exists():
                try:
                    images[key] = Image.open(str(path)).convert("RGBA")
                    continue
                except Exception:
                    pass
            images[key] = self._generate_icon(color)

        return images

    @staticmethod
    def _generate_icon(dot_color: tuple) -> "Image.Image":
        from PIL import Image, ImageDraw
        size = 32
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Headphone arc
        arc_box = [4, 4, 28, 22]
        draw.arc(arc_box, start=180, end=0, fill=COLOR_ACCENT, width=4)

        # Ear pads
        draw.ellipse([2, 14, 10, 24], fill=COLOR_ACCENT)
        draw.ellipse([22, 14, 30, 24], fill=COLOR_ACCENT)

        # Status dot (bottom-right)
        r = 5
        draw.ellipse([size - r*2 - 1, size - r*2 - 1,
                      size - 1, size - 1], fill=dot_color)

        return img

    def _get_current_image(self) -> Optional["Image.Image"]:
        return self._images.get(self._current_color)

    def _build_menu(self) -> "Menu":
        eq_profiles = [
            item("FPS Step Booster",
                 lambda icon, i: self._on_eq("fps_step_booster")),
            item("Music / Movie",
                 lambda icon, i: self._on_eq("music_movie")),
            item("Flat / Normal",
                 lambda icon, i: self._on_eq("flat")),
            item("Gaming Surround",
                 lambda icon, i: self._on_eq("gaming_surround")),
        ]

        return Menu(
            item("Open Dashboard",
                 self._open_dashboard,
                 default=True),
            item("🔄 Scan Devices",
                 self._scan_devices),
            Menu.SEPARATOR,
            item("Audio Profile", Menu(*eq_profiles)),
            Menu.SEPARATOR,
            item("Exit", self._exit_app),
        )

    def _open_dashboard(self, icon=None, menu_item=None) -> None:
        if self._on_open_dashboard:
            self._on_open_dashboard()

    def _scan_devices(self, icon=None, menu_item=None) -> None:
        if self._on_scan_devices:
            self._on_scan_devices()

    def _on_eq(self, profile_key: str) -> None:
        if self._on_eq_profile:
            self._on_eq_profile(profile_key)

    def _exit_app(self, icon=None, menu_item=None) -> None:
        if self._on_exit:
            self._on_exit()
        if self._icon:
            self._icon.stop()

    def start(self) -> bool:
        if not PYSTRAY_OK:
            logger.warning("pystray not available — tray icon disabled.")
            return False
        if not PILLOW_OK:
            logger.warning("Pillow not available — tray icon disabled.")
            return False

        img = self._get_current_image() or self._generate_icon(COLOR_GREEN)

        self._icon = pystray.Icon(
            name="PeripheralHub",
            icon=img,
            title="Peripheral Hub",
            menu=self._build_menu(),
        )

        self._thread = threading.Thread(
            target=self._icon.run,
            daemon=True,
            name="tray-icon",
        )
        self._thread.start()
        logger.info("Tray icon started.")
        return True

    def update_battery_status(self,
                                mouse_pct: Optional[int],
                                keyboard_pct: Optional[int],
                                headset_pct: Optional[int]) -> None:
        if not self._icon or not PILLOW_OK:
            return

        levels = [p for p in (mouse_pct, keyboard_pct, headset_pct) if p is not None]
        if not levels:
            color = "green"
        else:
            min_pct = min(levels)
            if min_pct < THRESHOLD_ORANGE:
                color = "red"
            elif min_pct < THRESHOLD_GREEN:
                color = "orange"
            else:
                color = "green"

        if color != self._current_color:
            self._current_color = color
            img = self._get_current_image()
            if img and self._icon:
                try:
                    self._icon.icon = img
                except Exception as exc:
                    logger.debug("Tray icon update error: %s", exc)

    def set_tooltip(self, text: str) -> None:
        if self._icon:
            try:
                self._icon.title = text[:127]
            except Exception:
                pass

    def stop(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
