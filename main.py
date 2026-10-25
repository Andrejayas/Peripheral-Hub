"""
main.py
Peripheral Hub - Entry point.
Initializes all device drivers, audio controllers, tray icon, and popup manager.
Device polling runs on daemon background threads.
Tkinter mainloop runs on the main thread.
"""

import json
import logging
import signal
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("peripheral_hub")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

# ---------------------------------------------------------------------------
# Poll intervals (seconds)
# ---------------------------------------------------------------------------
POLL_IDLE       = 60
POLL_DASHBOARD  = 5


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config.json; return defaults if missing or corrupt."""
    try:
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        logger.warning("Config load error: %s", exc)
    return {}


def _save_config(cfg: dict) -> None:
    """Persist config.json."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.warning("Config save error: %s", exc)


# ---------------------------------------------------------------------------
# Hub: main application class
# ---------------------------------------------------------------------------

class PeripheralHub:
    """
    Orchestrates all peripheral devices, audio controllers, and UI components.
    """

    def __init__(self):
        self._config = _load_config()
        self._running = False

        # Tk root (hidden — only used for after() scheduling)
        self._tk_root: Optional[tk.Tk] = None

        # Device instances (all failures are swallowed)
        self._mouse = None
        self._keyboard = None
        self._headset = None

        # Audio controllers
        self._eq_apo = None
        self._fxsound = None

        # UI components
        self._tray = None
        self._dashboard = None
        self._popup_manager = None

        # Polling state
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_stop = threading.Event()
        self._last_popup_times: Dict[Any, float] = {}

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_tk(self) -> None:
        """Create hidden root Tk window (required for Toplevel children)."""
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()
        self._tk_root.title("Peripheral Hub (root)")
        # Handle OS close signal gracefully
        self._tk_root.protocol("WM_DELETE_WINDOW", self.shutdown)

    def _init_devices(self) -> None:
        """Initialize all device drivers with silent failure handling."""
        # Mouse
        try:
            from devices.mouse import NoirM1Nex
            self._mouse = NoirM1Nex(
                on_connect=self._on_device_connect,
                on_disconnect=self._on_device_disconnect,
            )
            self._mouse.start()
            logger.info("Mouse driver initialized.")
        except Exception as exc:
            logger.warning("Mouse init failed: %s", exc)

        # Keyboard
        try:
            from devices.keyboard import AulaS75Pro
            self._keyboard = AulaS75Pro(
                on_connect=self._on_device_connect,
                on_disconnect=self._on_device_disconnect,
            )
            logger.info("Keyboard driver initialized.")
        except Exception as exc:
            logger.warning("Keyboard init failed: %s", exc)

        # Headset
        try:
            from devices.headset import KumoGS1XPro
            self._headset = KumoGS1XPro(
                config_path=CONFIG_PATH,
                on_connect=self._on_device_connect,
                on_disconnect=self._on_device_disconnect,
                on_charge_prompt=self._on_headset_charge_prompt,
            )
            logger.info("Headset driver initialized.")
        except Exception as exc:
            logger.warning("Headset init failed: %s", exc)

    def _init_audio(self) -> None:
        """Initialize audio controllers."""
        try:
            from audio.equalizer_apo import EqualizerAPO
            self._eq_apo = EqualizerAPO()
            if self._eq_apo.is_apo_installed():
                logger.info("Equalizer APO found.")
            else:
                logger.warning("Equalizer APO config directory not found.")
        except Exception as exc:
            logger.warning("EqualizerAPO init failed: %s", exc)

        try:
            from audio.fxsound import FxSound
            self._fxsound = FxSound()
            if self._fxsound.is_installed():
                logger.info("FxSound settings found.")
            else:
                logger.warning("FxSound settings file not found.")
        except Exception as exc:
            logger.warning("FxSound init failed: %s", exc)

    def _init_ui(self) -> None:
        """Initialize tray icon, dashboard, and popup manager."""
        # Generate icons if needed
        try:
            from assets.icon_generator import generate_all, ASSETS_DIR
            if not (ASSETS_DIR / "icon_tray.png").exists():
                logger.info("Generating icons...")
                generate_all()
        except Exception as exc:
            logger.warning("Icon generation failed: %s", exc)

        # Popup manager
        try:
            from popup import PopupManager
            self._popup_manager = PopupManager()
            logger.info("Popup manager ready.")
        except Exception as exc:
            logger.warning("Popup manager init failed: %s", exc)

        # Dashboard
        try:
            from dashboard import Dashboard
            self._dashboard = Dashboard(
                mouse=self._mouse,
                keyboard=self._keyboard,
                headset=self._headset,
                eq_apo=self._eq_apo,
                fxsound=self._fxsound,
                on_close=self._on_dashboard_close,
                on_scan=self._update_tray_battery,
            )
            logger.info("Dashboard initialized.")
        except Exception as exc:
            logger.warning("Dashboard init failed: %s", exc)

        # Tray icon
        try:
            from tray import TrayIcon
            self._tray = TrayIcon(
                on_open_dashboard=self._on_open_dashboard_request,
                on_scan_devices=self._on_tray_scan_request,
                on_eq_profile=self._on_tray_eq_profile,
                on_exit=self.shutdown,
            )
            self._tray.start()
            logger.info("Tray icon started.")
        except Exception as exc:
            logger.warning("Tray icon init failed: %s", exc)

    # ------------------------------------------------------------------
    # Device event callbacks (called from background threads)
    # ------------------------------------------------------------------

    _DEVICE_DISPLAY_NAMES = {
        "mouse":    "Noir M1 Nex",
        "keyboard": "AULA S75 Pro",
        "headset":  "Kumo GS1X Pro",
    }

    def _on_device_connect(self, device_key: str) -> None:
        """Called when a device connects. Schedules popup on main thread with 8s debounce."""
        now = time.time()
        last_t = self._last_popup_times.get((device_key, "connected"), 0)
        if now - last_t < 8.0:
            return
        self._last_popup_times[(device_key, "connected")] = now

        name = self._DEVICE_DISPLAY_NAMES.get(device_key, device_key)
        logger.info("Device connected: %s", name)
        battery = self._get_battery(device_key)
        if self._tk_root:
            self._tk_root.after(0, lambda: self._show_popup(name, "connected", battery))
        self._update_tray_battery()

    def _on_device_disconnect(self, device_key: str) -> None:
        """Called when a device disconnects. Schedules popup on main thread with 8s debounce."""
        now = time.time()
        last_t = self._last_popup_times.get((device_key, "disconnected"), 0)
        if now - last_t < 8.0:
            return
        self._last_popup_times[(device_key, "disconnected")] = now

        name = self._DEVICE_DISPLAY_NAMES.get(device_key, device_key)
        logger.info("Device disconnected: %s", name)
        if self._tk_root:
            self._tk_root.after(0, lambda: self._show_popup(name, "disconnected", None))
        self._update_tray_battery()

    def _on_headset_charge_prompt(self) -> None:
        """Called when smart-sleep detects possible headset charge."""
        if self._tk_root:
            self._tk_root.after(0, self._show_charge_prompt_dialog)

    def _show_charge_prompt_dialog(self) -> None:
        """Show a dialog asking user if headset was charged."""
        import tkinter.messagebox as msgbox
        result = msgbox.askyesno(
            title="Peripheral Hub – Headset",
            message=(
                "Headset reconnected after a long pause.\n\n"
                "Was the headset fully charged?"
            ),
        )
        if result and self._headset:
            self._headset.mark_as_charged()
            logger.info("Headset marked as charged via dialog.")
        elif not result and self._headset:
            self._headset.mark_not_charged()

    # ------------------------------------------------------------------
    # UI callbacks
    # ------------------------------------------------------------------

    def _on_open_dashboard_request(self) -> None:
        """Called from tray thread — schedule dashboard.show() on main thread."""
        if self._tk_root and self._dashboard:
            self._tk_root.after(0, self._dashboard.show)

    def _on_tray_scan_request(self) -> None:
        """Called from tray thread — schedule dashboard.scan_all() on main thread."""
        if self._tk_root and self._dashboard:
            self._tk_root.after(0, self._dashboard.scan_all)

    def _on_dashboard_close(self) -> None:
        logger.debug("Dashboard closed.")

    def _on_tray_eq_profile(self, profile_key: str) -> None:
        """Called from tray thread — apply EQ profile."""
        def _apply():
            if self._eq_apo:
                self._eq_apo.apply_profile(profile_key)
                logger.info("EQ profile set from tray: %s", profile_key)
        threading.Thread(target=_apply, daemon=True, name="eq-tray").start()

    def _show_popup(self, device_name: str, event: str,
                    battery_pct: Optional[int]) -> None:
        """Show a connection popup (must be called from main thread)."""
        if self._popup_manager:
            try:
                self._popup_manager.show(device_name, event, battery_pct)
            except Exception as exc:
                logger.debug("Popup show error: %s", exc)

    # ------------------------------------------------------------------
    # Battery helpers
    # ------------------------------------------------------------------

    def _get_battery(self, device_key: str) -> Optional[int]:
        try:
            if device_key == "mouse" and self._mouse:
                return self._mouse.get_status().get("battery_level")
            if device_key == "keyboard" and self._keyboard:
                return self._keyboard.get_status().get("battery_level")
            if device_key == "headset" and self._headset:
                return self._headset.get_battery_estimate()
        except Exception:
            pass
        return None

    def _update_tray_battery(self) -> None:
        """Update tray icon color based on all device battery levels."""
        if self._tray is None:
            return
        try:
            m = self._get_battery("mouse")
            k = self._get_battery("keyboard")
            h = self._get_battery("headset")
            self._tray.update_battery_status(m, k, h)

            # Build tooltip
            parts = []
            if m is not None:
                parts.append(f"Mouse: {m}%")
            if k is not None:
                parts.append(f"KB: {k}%")
            if h is not None:
                parts.append(f"Headset: ~{h}%")
            tooltip = "Peripheral Hub\n" + " | ".join(parts) if parts else "Peripheral Hub"
            self._tray.set_tooltip(tooltip)
        except Exception as exc:
            logger.debug("Tray battery update error: %s", exc)

    # ------------------------------------------------------------------
    # Polling loop (background thread)
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """Background thread: poll all devices periodically."""
        logger.info("Poll loop started.")
        while not self._poll_stop.is_set():
            # Choose interval based on dashboard visibility
            is_open = (self._dashboard is not None and
                       self._dashboard.is_visible())
            interval = POLL_DASHBOARD if is_open else POLL_IDLE

            # Poll all devices
            for dev, name in [(self._mouse, "mouse"),
                               (self._keyboard, "keyboard"),
                               (self._headset, "headset")]:
                if dev is None:
                    continue
                try:
                    dev.poll()
                except Exception as exc:
                    logger.debug("Poll error [%s]: %s", name, exc)

            self._update_tray_battery()

            # Persist headset estimator state
            if self._headset:
                try:
                    self._headset.save_state(self._config)
                    _save_config(self._config)
                except Exception as exc:
                    logger.debug("Config save error: %s", exc)

            # Sleep in small increments so we can respond to stop signal
            for _ in range(interval * 10):
                if self._poll_stop.is_set():
                    break
                time.sleep(0.1)

        logger.info("Poll loop stopped.")

    # ------------------------------------------------------------------
    # Startup / Shutdown
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Initialize everything and start the Tkinter mainloop."""
        logger.info("Peripheral Hub starting...")
        self._running = True

        # Tk MUST be initialized first (creates root before any Toplevel)
        self._init_tk()

        # Device drivers
        self._init_devices()

        # Audio controllers
        self._init_audio()

        # UI components (requires Tk)
        self._init_ui()

        # Initial battery update
        self._update_tray_battery()

        # Display dashboard on initial launch
        if self._dashboard:
            self._dashboard.show()

        # Start background poll thread
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="device-poll",
        )
        self._poll_thread.start()

        logger.info("Peripheral Hub running. Tray icon active.")

        # Register signal handlers for graceful shutdown
        try:
            signal.signal(signal.SIGINT, lambda s, f: self.shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: self.shutdown())
        except (OSError, ValueError):
            pass  # Signal handlers not supported in all environments

        # Run Tkinter main loop (BLOCKS until root is destroyed)
        try:
            self._tk_root.mainloop()
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self) -> None:
        """Gracefully stop all components and exit."""
        if not self._running:
            return
        self._running = False
        logger.info("Shutting down Peripheral Hub...")

        # Stop poll loop
        self._poll_stop.set()

        # Stop devices
        for dev in [self._mouse, self._keyboard, self._headset]:
            if dev:
                try:
                    dev.stop()
                except Exception:
                    pass

        # Persist state
        if self._headset:
            try:
                self._headset.save_state(self._config)
            except Exception:
                pass
        _save_config(self._config)

        # Stop tray
        if self._tray:
            try:
                self._tray.stop()
            except Exception:
                pass

        # Destroy dashboard
        if self._dashboard:
            try:
                self._dashboard.destroy()
            except Exception:
                pass

        # Destroy Tk root (ends mainloop)
        if self._tk_root:
            try:
                self._tk_root.destroy()
            except Exception:
                pass

        logger.info("Peripheral Hub stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    hub = PeripheralHub()
    hub.run()


if __name__ == "__main__":
    main()
