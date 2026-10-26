"""
dashboard.py
Peripheral Hub - Modern Universal Gaming Peripheral Controller.
Inspired by Coucou (sleek pill navigation tabs, 60fps sliding active pill lerp animation,
smooth rounded cards, deep obsidian dark aesthetic, and clean telemetry).

Features:
- Free-floating draggable Windows desktop window with native Dark Mode title bar.
- Modern In-Window Header with Title, Status Dot, Quick Scan & Info pills (Zero white menu bar).
- Coucou-style 60fps smooth sliding pill navigation tabs with non-blocking re-targeting.
- Dedicated Mouse Noir M1 Nex customizer: button remapping, macros, independent LED color, DPI, battery mV/%.
- Interactive real-time Button Mapping test feedback badge with RawInput + Async polling dual-engine.
- Keyboard AULA S75 Pro: 20 lighting modes, custom RGB palette, Brightness (1-5), Speed (1-5).
- Headset dbE Kumo GS1X Pro: Smart battery tracker, Windows master volume.
- Native Win32 status bar at bottom with crisp anti-aliased typography.
- Window remembers last moved position on screen.
"""

import ctypes
from ctypes import byref, c_int, sizeof
import json
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional, Callable, Dict, Any, Tuple, List
from PIL import Image, ImageTk

logger = logging.getLogger(__name__)

# UI Color Palette (Deep Obsidian / Dark Glass aesthetic)
BG           = "#141416"
CARD         = "#1c1c20"
CARD_HOVER   = "#24242a"
BORDER       = "#2c2c34"
BORDER_LIGHT = "#3c3c46"
ACCENT       = "#e26332"
ACCENT_HOVER = "#f27342"
TEXT         = "#ffffff"
TEXT_MUTED   = "#a0a0a8"
DIM          = "#666670"
GREEN        = "#4caf50"
ORANGE       = "#ff9800"
RED          = "#f44336"
BLUE         = "#3b82f6"

WIN_W = 500
WIN_H = 640
CONFIG_PATH = Path(__file__).parent / "config.json"


def _battery_color(pct: Optional[int]) -> str:
    if pct is None:
        return DIM
    if pct >= 50:
        return GREEN
    if pct >= 20:
        return ORANGE
    return RED


def _pct_text(pct: Optional[int]) -> str:
    return f"{pct}%" if pct is not None else "N/A"


class _BatteryBar(tk.Canvas):
    """Modern horizontal battery bar widget with rounded corners and cell nub."""
    def __init__(self, parent, width=160, height=14, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=CARD, highlightthickness=0, **kwargs)
        self._bar_w = width
        self._bar_h = height
        self._draw(0, DIM)

    def set_value(self, pct: Optional[int]) -> None:
        if pct is None:
            self._draw(0, DIM)
        else:
            self._draw(pct, _battery_color(pct))

    def _draw(self, pct: int, color: str) -> None:
        self.delete("all")
        # Background bar
        self.create_rectangle(0, 0, self._bar_w - 6, self._bar_h - 1,
                              outline=BORDER, fill=BG, width=1)
        # Positive terminal nub
        self.create_rectangle(self._bar_w - 5, (self._bar_h - 6) // 2,
                              self._bar_w - 1, (self._bar_h + 6) // 2,
                              fill=BORDER, outline="")
        fill_w = int((self._bar_w - 8) * max(0, min(100, pct)) / 100)
        if fill_w > 0:
            self.create_rectangle(1, 1, fill_w, self._bar_h - 2,
                                  fill=color, outline="")


class SmoothTabBar(tk.Canvas):
    """
    Coucou-inspired hardware navigation tab bar with smooth 60fps sliding pill animation.
    Interpolates active pill position and width across hardware tabs using an ease-out lerp curve.
    Safely re-targets on rapid tab clicks without stutter or freeze.
    """
    def __init__(self, parent, tabs: List[Tuple[str, str]], on_tab_change: Callable[[str], None],
                 height: int = 40, bg: str = BG, bar_bg: str = CARD, active_bg: str = ACCENT,
                 text_color: str = TEXT, muted_color: str = TEXT_MUTED, **kwargs):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, **kwargs)
        self.tabs = tabs  # list of (tab_id, label)
        self.on_tab_change = on_tab_change
        self.bar_bg = bar_bg
        self.active_bg = active_bg
        self.text_color = text_color
        self.muted_color = muted_color

        self.current_idx = 0
        self.target_idx = 0
        self.anim_x = 4.0
        self.anim_w = 140.0
        self.target_x = 4.0
        self.target_w = 140.0
        self.is_animating = False

        self.pill_h = height - 8
        self.pill_y = 4
        self.num_tabs = len(tabs)
        self.tab_w = 140.0

        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", self._on_resize)
        self.configure(cursor="hand2")

    def _round_rect(self, x1: float, y1: float, x2: float, y2: float, r: float = 6, **kwargs):
        r = min(r, max(1, (x2 - x1) / 2), max(1, (y2 - y1) / 2))
        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _on_resize(self, event):
        w = max(50, event.width)
        self.tab_w = (w - 8) / max(1, self.num_tabs)
        self.target_x = 4 + self.tab_w * self.target_idx
        self.target_w = self.tab_w
        if not self.is_animating:
            self.anim_x = self.target_x
            self.anim_w = self.target_w
        self._draw()

    def _on_click(self, event):
        if self.tab_w <= 0:
            return
        x = event.x - 4
        idx = int(x // self.tab_w)
        if 0 <= idx < self.num_tabs and idx != self.target_idx:
            self.select_tab_index(idx)

    def select_tab_id(self, tab_id: str) -> None:
        for i, (tid, _) in enumerate(self.tabs):
            if tid == tab_id:
                if i != self.target_idx:
                    self.select_tab_index(i)
                break

    def select_tab_index(self, idx: int) -> None:
        self.target_idx = idx
        self.target_x = 4 + self.tab_w * idx
        self.target_w = self.tab_w
        self.on_tab_change(self.tabs[idx][0])

        if not self.is_animating:
            self.is_animating = True
            self._animate_step()

    def _animate_step(self) -> None:
        if not self.is_animating:
            return
        dx = self.target_x - self.anim_x
        dw = self.target_w - self.anim_w
        if abs(dx) < 0.6 and abs(dw) < 0.6:
            self.anim_x = self.target_x
            self.anim_w = self.target_w
            self.current_idx = self.target_idx
            self.is_animating = False
            self._draw()
            return

        # 60fps Ease-out lerp interpolation with continuous re-targeting
        self.anim_x += dx * 0.42
        self.anim_w += dw * 0.42
        self._draw()
        self.after(16, self._animate_step)

    def _draw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        # 1. Tab Bar Background Container
        self._round_rect(2, 2, w - 2, h - 2, r=8, fill=self.bar_bg, outline="")

        # 2. Sliding Active Pill with rounded corners
        px1 = self.anim_x + 2
        py1 = self.pill_y
        px2 = self.anim_x + self.anim_w - 2
        py2 = self.pill_y + self.pill_h
        if px2 > px1:
            self._round_rect(px1, py1, px2, py2, r=6, fill=self.active_bg, outline="")

        # 3. Clean Anti-Aliased Tab Labels
        for i, (tid, label) in enumerate(self.tabs):
            cx = 4 + self.tab_w * i + (self.tab_w / 2)
            cy = self.pill_y + (self.pill_h / 2)
            is_active = (i == self.target_idx)
            fg = self.text_color if is_active else self.muted_color
            font_weight = "bold" if is_active else "normal"
            self.create_text(cx, cy, text=label, fill=fg,
                             font=("Segoe UI", 9, font_weight))


class _DpiPill(tk.Label):
    """Compact selectable DPI pill."""
    def __init__(self, parent, dpi: int, on_click: Callable, **kwargs):
        super().__init__(parent,
                         text=str(dpi) if dpi < 1000 else f"{dpi//1000}K",
                         font=("Segoe UI", 8),
                         fg=DIM, bg=BORDER,
                         padx=8, pady=4,
                         cursor="hand2",
                         relief="flat",
                         **kwargs)
        self._dpi = dpi
        self._on_click = on_click
        self.bind("<Button-1>", lambda e: on_click(dpi))

    def set_active(self, active: bool) -> None:
        self.configure(
            fg=TEXT if active else DIM,
            bg=ACCENT if active else BORDER,
            font=("Segoe UI", 8, "bold" if active else "normal")
        )


class Dashboard:
    """
    Peripheral Hub main desktop application window.
    Features:
    - Freely draggable native window with Windows 10/11 Dark Title Bar.
    - Coucou-style smooth 60fps sliding pill tab navigation for Mouse, Keyboard, and Headset.
    - Full customizer suite for Noir M1 Nex, AULA S75 Pro, and dbE Kumo.
    - Interactive real-time Button Mapping test feedback badge.
    - Status bar with connected device counts and battery summary.
    """

    def __init__(self,
                 mouse=None,
                 keyboard=None,
                 headset=None,
                 eq_apo=None,
                 fxsound=None,
                 on_close: Optional[Callable] = None,
                 on_scan: Optional[Callable] = None):
        self._mouse = mouse
        self._keyboard = keyboard
        self._headset = headset
        self._eq_apo = eq_apo
        self._fxsound = fxsound
        self._on_close = on_close
        self._on_scan = on_scan

        self._root: Optional[tk.Toplevel] = None
        self._visible = False
        self._refresh_job = None
        self._current_tab = "mouse"

        # Tab pages & smooth tabs
        self._smooth_tabs: Optional[SmoothTabBar] = None
        self._tab_pages: Dict[str, tk.Frame] = {}

        # Mouse controls
        self._dpi_buttons: Dict[int, _DpiPill] = {}

        # Noir M1 Nex official assets
        self._noir_img_online: Optional[ImageTk.PhotoImage] = None
        self._noir_img_offline: Optional[ImageTk.PhotoImage] = None
        self._load_noir_assets()

        # Connect button event callback for live physical feedback
        if self._mouse:
            self._mouse.set_button_event_callback(self._on_mouse_button_press)

        self._build()

    def _load_noir_assets(self) -> None:
        """Pre-load authentic Noir M1 Nex mouse graphics extracted from official software."""
        try:
            base_noir = Path(__file__).parent / "assets" / "noir" / "1HomePage"
            p_on = base_noir / "dev1online.png"
            p_off = base_noir / "dev1offline.png"
            if p_on.exists():
                im_on = Image.open(p_on)
                im_on.thumbnail((90, 115), Image.Resampling.LANCZOS)
                self._noir_img_online = ImageTk.PhotoImage(im_on)
            if p_off.exists():
                im_off = Image.open(p_off)
                im_off.thumbnail((90, 115), Image.Resampling.LANCZOS)
                self._noir_img_offline = ImageTk.PhotoImage(im_off)
        except Exception as exc:
            logger.debug("Failed loading Noir mouse assets: %s", exc)

    # ------------------------------------------------------------------
    # Window lifecycle & positioning
    # ------------------------------------------------------------------

    def _build(self) -> None:
        root = tk.Toplevel()
        self._root = root
        root.title("Peripheral Hub")
        root.configure(bg=BG)
        root.resizable(False, False)

        # Apply dark ttk styling for Comboboxes and controls (eliminates white dropdowns & white text highlights)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TCombobox",
                        fieldbackground=CARD,
                        background=CARD,
                        foreground=TEXT,
                        darkcolor=BORDER,
                        lightcolor=BORDER,
                        arrowcolor=ACCENT,
                        bordercolor=BORDER,
                        padding=(6, 4))
        style.map("TCombobox",
                  fieldbackground=[("readonly", CARD), ("focus", CARD), ("active", CARD_HOVER)],
                  foreground=[("readonly", TEXT), ("focus", TEXT)],
                  background=[("readonly", CARD), ("active", CARD_HOVER)],
                  selectbackground=[("readonly", CARD), ("focus", CARD), ("active", CARD)],
                  selectforeground=[("readonly", TEXT), ("focus", TEXT)],
                  arrowcolor=[("active", ACCENT_HOVER)])

        # Ensure combobox dropdown listbox popups are deep obsidian
        root.option_add("*TCombobox*Listbox.background", CARD)
        root.option_add("*TCombobox*Listbox.foreground", TEXT)
        root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        root.option_add("*TCombobox*Listbox.selectForeground", TEXT)
        root.option_add("*TCombobox*Listbox.relief", "flat")
        root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 9))

        # Variables initialized after root exists
        self._mouse_btn4_var = tk.StringVar(root, value="Next Track")
        self._mouse_btn5_var = tk.StringVar(root, value="Browser Backward")
        self._mouse_rgb_mode_var = tk.StringVar(root, value="Breathing")

        # Keyboard controls
        self._kb_light_var = tk.StringVar(root, value="Colourful")
        self._kb_br_var = tk.IntVar(root, value=5)
        self._kb_sp_var = tk.IntVar(root, value=3)

        # Headset controls
        self._hs_vol_var = tk.IntVar(root, value=50)

        # Load saved position or center on primary screen
        pos_x, pos_y = self._load_window_pos()
        if pos_x is None or pos_y is None:
            sw = root.winfo_screenwidth()
            sh = root.winfo_screenheight()
            pos_x = max(50, (sw - WIN_W) // 2)
            pos_y = max(50, (sh - WIN_H) // 2)

        root.geometry(f"{WIN_W}x{WIN_H}+{pos_x}+{pos_y}")

        # Bind window drag / move events to remember position
        root.bind("<Configure>", self._on_window_configure)

        # Enable Windows 10/11 Immersive Dark Mode for Title Bar
        root.after(10, self._apply_windows_dark_titlebar)

        # Native protocol for close button (hides to tray)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        # Build UI layout (NO legacy white menu bar!)
        self._build_top_header()
        self._build_pill_tabs()
        self._build_pages_container()
        self._build_bottom_status_bar()

        # Select initial tab
        self.select_tab("mouse")

        # Initially hidden until tray icon or user opens it
        root.withdraw()

    def _apply_windows_dark_titlebar(self) -> None:
        """Call DwmSetWindowAttribute to make the native Windows titlebar dark."""
        if not self._root:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self._root.winfo_id())
            if not hwnd:
                hwnd = self._root.winfo_id()
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            val = c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, byref(val), sizeof(val)
            )
        except Exception as e:
            logger.debug("Dark title bar hook error: %s", e)

    def _load_window_pos(self) -> Tuple[Optional[int], Optional[int]]:
        try:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    pos = cfg.get("window_pos")
                    if pos and isinstance(pos, list) and len(pos) == 2:
                        return int(pos[0]), int(pos[1])
        except Exception:
            pass
        return None, None

    def _save_window_pos(self, x: int, y: int) -> None:
        try:
            cfg = {}
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["window_pos"] = [x, y]
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            pass

    def _on_window_configure(self, event=None) -> None:
        if self._root and self._visible and event and event.widget == self._root:
            x = self._root.winfo_x()
            y = self._root.winfo_y()
            if x > 0 and y > 0:
                self._save_window_pos(x, y)

    # ------------------------------------------------------------------
    # Top Header & Coucou Smooth Sliding Tabs (No White Menu Bar)
    # ------------------------------------------------------------------

    def _show_about(self) -> None:
        messagebox.showinfo(
            "About Peripheral Hub",
            "Peripheral Hub v1.2.0\n\n"
            "An ultra-lightweight universal gaming peripheral controller for Windows.\n"
            "Supports Noir M1 Nex, AULA S75 Pro, and dbE Kumo GS1X Pro.\n\n"
            "Created by Andrejayas."
        )

    def _open_github(self) -> None:
        import webbrowser
        webbrowser.open("https://github.com/Andrejayas/Peripheral-Hub")

    def _on_full_exit(self) -> None:
        if self._on_close:
            self._on_close()
        self._root.quit()

    def _build_top_header(self) -> None:
        hdr_frame = tk.Frame(self._root, bg=BG, padx=16, pady=12)
        hdr_frame.pack(fill="x")

        # App Brand & Status Dot
        brand_frame = tk.Frame(hdr_frame, bg=BG)
        brand_frame.pack(side="left")

        self._brand_dot = tk.Label(brand_frame, text="●", font=("Segoe UI", 12),
                                   fg=GREEN, bg=BG)
        self._brand_dot.pack(side="left", padx=(0, 6))

        tk.Label(brand_frame, text="Peripheral Hub", font=("Segoe UI", 13, "bold"),
                 fg=TEXT, bg=BG).pack(side="left")

        actions_frame = tk.Frame(hdr_frame, bg=BG)
        actions_frame.pack(side="right")

        # Info Button Pill
        info_btn = tk.Label(actions_frame, text="Info", font=("Segoe UI", 9, "bold"),
                            fg=TEXT_MUTED, bg=CARD, cursor="hand2", padx=12, pady=4)
        info_btn.pack(side="right", padx=(6, 0))
        info_btn.bind("<Button-1>", lambda e: self._show_about())
        info_btn.bind("<Enter>", lambda e: info_btn.configure(bg=BORDER, fg=TEXT))
        info_btn.bind("<Leave>", lambda e: info_btn.configure(bg=CARD, fg=TEXT_MUTED))

        # Scan Button Pill with Live Scan Feedback
        self._scan_btn = tk.Label(actions_frame, text="Scan", font=("Segoe UI", 9, "bold"),
                                  fg=ACCENT, bg=CARD, cursor="hand2", padx=12, pady=4)
        self._scan_btn.pack(side="right")
        self._scan_btn.bind("<Button-1>", lambda e: self.scan_all())
        self._scan_btn.bind("<Enter>", lambda e: self._scan_btn.configure(bg=BORDER, fg=TEXT))
        self._scan_btn.bind("<Leave>", lambda e: self._scan_btn.configure(bg=CARD, fg=ACCENT))

    def _build_pill_tabs(self) -> None:
        """Coucou-style navigation tab bar with smooth 60fps sliding pill animation."""
        tabs_container = tk.Frame(self._root, bg=BG, padx=14, pady=2)
        tabs_container.pack(fill="x")

        tabs = [
            ("mouse",    "Mouse"),
            ("keyboard", "Keyboard"),
            ("headset",  "Headset"),
        ]

        self._smooth_tabs = SmoothTabBar(
            tabs_container,
            tabs=tabs,
            on_tab_change=self._on_tab_clicked,
            height=38,
            bg=BG,
            bar_bg=CARD,
            active_bg=ACCENT,
            text_color=TEXT,
            muted_color=TEXT_MUTED,
        )
        self._smooth_tabs.pack(fill="x", expand=True)

    def _on_tab_clicked(self, tab_id: str) -> None:
        """Called when a tab is clicked in SmoothTabBar."""
        self._current_tab = tab_id
        for tid, page in self._tab_pages.items():
            if tid == tab_id:
                page.pack(fill="both", expand=True, padx=14, pady=10)
            else:
                page.pack_forget()

    def select_tab(self, tab_id: str) -> None:
        """Switch active tab page smoothly and trigger sliding pill animation."""
        self._current_tab = tab_id
        if hasattr(self, "_smooth_tabs") and self._smooth_tabs:
            self._smooth_tabs.select_tab_id(tab_id)
        self._on_tab_clicked(tab_id)

    # ------------------------------------------------------------------
    # Pages Container
    # ------------------------------------------------------------------

    def _build_pages_container(self) -> None:
        self._content_area = tk.Frame(self._root, bg=BG)
        self._content_area.pack(fill="both", expand=True)

        self._build_mouse_page()
        self._build_keyboard_page()
        self._build_headset_page()

    # ------------------------------------------------------------------
    # Page 1: Noir M1 Nex (Dedicated Mouse Customizer)
    # ------------------------------------------------------------------

    def _build_mouse_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["mouse"] = page

        # 1. Device Status Card (Coucou-style with Official Noir M1 Nex Asset)
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=12)
        card_stat.pack(fill="x", pady=(0, 8))

        stat_body = tk.Frame(card_stat, bg=CARD)
        stat_body.pack(fill="x")

        # Left Column: Official 3D Render of Noir M1 Nex Mouse
        self._mouse_img_lbl = tk.Label(stat_body, bg=CARD)
        if self._noir_img_offline:
            self._mouse_img_lbl.configure(image=self._noir_img_offline)
        self._mouse_img_lbl.pack(side="left", padx=(0, 16))

        # Right Column: Telemetry & Info
        info_col = tk.Frame(stat_body, bg=CARD)
        info_col.pack(side="left", fill="both", expand=True)

        row1 = tk.Frame(info_col, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="Noir M1 Nex", font=("Segoe UI", 12, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._mouse_status_lbl = tk.Label(row1, text="● Disconnected",
                                          font=("Segoe UI", 9, "bold"),
                                          fg=RED, bg=CARD)
        self._mouse_status_lbl.pack(side="right")

        # Hardware Specifications Sub-badge
        specs_row = tk.Frame(info_col, bg=CARD)
        specs_row.pack(fill="x", pady=(3, 6))
        tk.Label(specs_row, text="PixArt PAW3311 • Beken BK2535 • 70g Esports Ultralight",
                 font=("Segoe UI", 8), fg=DIM, bg=CARD).pack(side="left")

        # Battery Row
        bat_row = tk.Frame(info_col, bg=CARD)
        bat_row.pack(fill="x", pady=(4, 2))
        tk.Label(bat_row, text="Battery", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=8, anchor="w").pack(side="left")
        self._mouse_bat_bar = _BatteryBar(bat_row, width=170)
        self._mouse_bat_bar.pack(side="left", padx=6)
        self._mouse_bat_lbl = tk.Label(bat_row, text="N/A",
                                       font=("Segoe UI", 8, "bold"),
                                       fg=TEXT, bg=CARD)
        self._mouse_bat_lbl.pack(side="left")
        self._mouse_volt_lbl = tk.Label(bat_row, text="", font=("Segoe UI", 8),
                                        fg=DIM, bg=CARD)
        self._mouse_volt_lbl.pack(side="left", padx=6)

        # 2. DPI Stage Selector Card
        card_dpi = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_dpi.pack(fill="x", pady=4)

        dpi_head = tk.Frame(card_dpi, bg=CARD)
        dpi_head.pack(fill="x")
        tk.Label(dpi_head, text="DPI Sensitivity", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")
        self._mouse_dpi_val_lbl = tk.Label(dpi_head, text="1200 DPI",
                                           font=("Segoe UI", 9, "bold"),
                                           fg=TEXT, bg=CARD)
        self._mouse_dpi_val_lbl.pack(side="right")

        pills_row = tk.Frame(card_dpi, bg=CARD)
        pills_row.pack(fill="x", pady=(8, 4))
        for dpi in [400, 800, 1200, 2400, 3200, 5000, 10000]:
            btn = _DpiPill(pills_row, dpi, self._on_dpi_click)
            btn.pack(side="left", expand=True, fill="x", padx=2)
            self._dpi_buttons[dpi] = btn

        # 3. Dedicated Noir Button Remapping & Macro Section
        card_btns = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_btns.pack(fill="x", pady=4)

        tk.Label(card_btns, text="Button Mapping & Macro (Tombol Samping)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        self._mouse_btn_status_lbl = tk.Label(card_btns,
                                              text="● Button Remap & Macro Engine Active",
                                              font=("Segoe UI", 8), fg=GREEN, bg=CARD)
        self._mouse_btn_status_lbl.pack(anchor="w", pady=(2, 4))

        btn_grid = tk.Frame(card_btns, bg=CARD)
        btn_grid.pack(fill="x", pady=(2, 2))

        btn_all_opts = [
            "Next Track",
            "Previous Track",
            "Play/Pause",
            "Volume Up",
            "Volume Down",
            "Mute",
            "Browser Forward",
            "Browser Backward",
            "Double Click",
            "Quick Fire (Macro)",
            "Crouch Jump (Macro)",
            "Screenshot",
            "Sniper 400 DPI",
        ]

        # Button 4 (Forward)
        b4_row = tk.Frame(btn_grid, bg=CARD)
        b4_row.pack(fill="x", pady=2)
        tk.Label(b4_row, text="Button 4 (Forward)", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=18, anchor="w").pack(side="left")
        b4_menu = ttk.Combobox(b4_row, textvariable=self._mouse_btn4_var,
                               values=btn_all_opts, width=22, state="readonly")
        b4_menu.pack(side="left", padx=4)
        b4_menu.bind("<<ComboboxSelected>>", lambda e: self._on_btn_mapping_change(4, self._mouse_btn4_var.get()))

        # Button 5 (Backward)
        b5_row = tk.Frame(btn_grid, bg=CARD)
        b5_row.pack(fill="x", pady=2)
        tk.Label(b5_row, text="Button 5 (Backward)", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=18, anchor="w").pack(side="left")
        b5_menu = ttk.Combobox(b5_row, textvariable=self._mouse_btn5_var,
                               values=btn_all_opts, width=22, state="readonly")
        b5_menu.pack(side="left", padx=4)
        b5_menu.bind("<<ComboboxSelected>>", lambda e: self._on_btn_mapping_change(5, self._mouse_btn5_var.get()))

        # Interactive Live Test Badge for Side Buttons
        self._mouse_btn_test_lbl = tk.Label(
            card_btns,
            text="⚡ Tes Tombol: Tekan Tombol 4 / 5 di samping mouse untuk tes langsung",
            font=("Segoe UI", 8, "bold"),
            fg=TEXT_MUTED, bg=BORDER,
            padx=10, pady=5, relief="flat"
        )
        self._mouse_btn_test_lbl.pack(fill="x", pady=(6, 2))

        # 4. Mouse DPI LED / Effect Card (With Official Noir 14 Preset Colors)
        card_rgb = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_rgb.pack(fill="x", pady=4)

        rgb_head = tk.Frame(card_rgb, bg=CARD)
        rgb_head.pack(fill="x")
        tk.Label(rgb_head, text="Mouse DPI LED / Effect", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")

        self._mouse_active_color_lbl = tk.Label(rgb_head, text="● #FF2A2A", font=("Segoe UI", 8, "bold"),
                                                fg="#ff2a2a", bg=CARD)
        self._mouse_active_color_lbl.pack(side="left", padx=8)

        m_rgb_modes = ["Breathing", "Neon Cycle", "Static", "LED Off"]
        m_rgb_menu = ttk.Combobox(rgb_head, textvariable=self._mouse_rgb_mode_var,
                                  values=m_rgb_modes, width=14, state="readonly")
        m_rgb_menu.pack(side="right")
        m_rgb_menu.bind("<<ComboboxSelected>>", lambda e: self._on_mouse_rgb_mode_change(self._mouse_rgb_mode_var.get()))

        # Informational Banner: Noir M1 Nex Hardware Architecture
        info_banner = tk.Frame(card_rgb, bg=BORDER, padx=10, pady=6)
        info_banner.pack(fill="x", pady=(8, 8))
        tk.Label(
            info_banner,
            text="ℹ Indikator LED DPI Noir M1 Nex terletak pada roda scroll & sensor internal (esports ultralight).\n"
                 "Warna yang dipilih akan diprogram langsung ke chip flash hardware mouse secara instan.",
            font=("Segoe UI", 8),
            fg=TEXT_MUTED, bg=BORDER, justify="left"
        ).pack(anchor="w")

        # Official Noir 14 Color Palette extracted from driver
        dots_row1 = tk.Frame(card_rgb, bg=CARD)
        dots_row1.pack(fill="x", pady=(2, 2))
        tk.Label(dots_row1, text="Noir Preset:", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")

        noir_colors_1 = ["#ff0000", "#00ffff", "#00ff00", "#ff00ff", "#ffff00", "#ff5000", "#0000ff"]
        noir_colors_2 = ["#e3007f", "#2ea6df", "#601985", "#ffffff", "#8bb224", "#ff9b33", "#d071ad"]

        for hex_code in noir_colors_1:
            dot = tk.Label(dots_row1, text="●", font=("Segoe UI", 13, "bold"),
                           fg=hex_code, bg=CARD, cursor="hand2", padx=3)
            dot.pack(side="left")
            dot.bind("<Button-1>", lambda e, c=hex_code: self._on_mouse_color(c))

        dots_row2 = tk.Frame(card_rgb, bg=CARD)
        dots_row2.pack(fill="x", pady=(0, 4))
        tk.Label(dots_row2, text="", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12).pack(side="left")
        for hex_code in noir_colors_2:
            dot = tk.Label(dots_row2, text="●", font=("Segoe UI", 13, "bold"),
                           fg=hex_code, bg=CARD, cursor="hand2", padx=3)
            dot.pack(side="left")
            dot.bind("<Button-1>", lambda e, c=hex_code: self._on_mouse_color(c))

    def _on_dpi_click(self, dpi: int) -> None:
        """Called when user clicks a DPI button: changes DPI sensitivity independently."""
        if self._mouse:
            threading.Thread(target=self._mouse.set_dpi, args=(dpi,),
                             daemon=True, name="dpi-set").start()
        for d, btn in self._dpi_buttons.items():
            btn.set_active(d == dpi)
        self._mouse_dpi_val_lbl.configure(text=f"{dpi} DPI")

    def _on_mouse_color(self, hex_code: str) -> None:
        """Called when user clicks a preset color dot: updates LED color independently without changing DPI."""
        if self._mouse:
            threading.Thread(target=self._mouse.set_dpi_color, args=(hex_code,),
                             daemon=True, name="mouse-color-set").start()
        if hasattr(self, "_mouse_active_color_lbl"):
            self._mouse_active_color_lbl.configure(text=f"● {hex_code.upper()}", fg=hex_code)
        logger.info("Mouse custom LED color selected: %s", hex_code)

    def _on_mouse_rgb_mode_change(self, mode_name: str) -> None:
        if self._mouse:
            color = self._mouse.get_status().get("current_color", "#ff2a2a")
            threading.Thread(target=self._mouse.set_rgb_effect, args=(mode_name, color),
                             daemon=True, name="mouse-rgb-mode").start()
        logger.info("Mouse RGB mode changed: %s", mode_name)

    def _on_btn_mapping_change(self, btn_idx: int, action: str) -> None:
        if self._mouse:
            self._mouse.set_button_mapping(btn_idx, action)
        if hasattr(self, "_mouse_btn_status_lbl"):
            self._mouse_btn_status_lbl.configure(
                text=f"✓ Tombol {btn_idx} diatur ke '{action}'",
                fg=ACCENT
            )
            self._root.after(3000, lambda: self._mouse_btn_status_lbl.configure(
                text="● Button Remap & Macro Engine Active", fg=GREEN
            ))
        logger.info("Button %d remap action selected: %s", btn_idx, action)

    def _on_mouse_button_press(self, btn_idx: int, action: str) -> None:
        """Invoked live when user clicks physical button 4 or 5 on mouse."""
        if not self._root:
            return
        def _ui_update():
            if hasattr(self, "_mouse_btn_status_lbl"):
                self._mouse_btn_status_lbl.configure(
                    text=f"⚡ Tombol {btn_idx} Ditekan -> Menjalankan: '{action}'",
                    fg=ACCENT
                )
            if hasattr(self, "_mouse_btn_test_lbl"):
                self._mouse_btn_test_lbl.configure(
                    text=f"🎯 TOMBOL {btn_idx} AKTIF! Aksi: {action}",
                    bg=ACCENT, fg=TEXT
                )
                self._root.after(1400, lambda: self._mouse_btn_test_lbl.configure(
                    text="⚡ Tes Tombol: Tekan Tombol 4 / 5 di samping mouse untuk tes langsung",
                    bg=BORDER, fg=TEXT_MUTED
                ))
        self._root.after(0, _ui_update)

    def _on_mouse_rgb_mode_change(self, mode_name: str) -> None:
        if self._mouse:
            color = self._mouse.get_status().get("current_color", "#ff2a2a")
            self._mouse.set_rgb_effect(mode_name, color)
        logger.info("Mouse RGB mode changed: %s", mode_name)

    # ------------------------------------------------------------------
    # Page 2: AULA S75 Pro (Mechanical Keyboard)
    # ------------------------------------------------------------------

    def _build_keyboard_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["keyboard"] = page

        # 1. Device Status Card
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_stat.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(card_stat, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="AULA S75 Pro", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._kb_status_lbl = tk.Label(row1, text="● Disconnected",
                                       font=("Segoe UI", 9, "bold"),
                                       fg=RED, bg=CARD)
        self._kb_status_lbl.pack(side="right")

        # 2. Lighting Mode Selector
        card_lm = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_lm.pack(fill="x", pady=4)

        from devices.keyboard import LIGHT_MODE_NAMES
        lm_row = tk.Frame(card_lm, bg=CARD)
        lm_row.pack(fill="x")
        tk.Label(lm_row, text="Lighting Mode (20 Efek)", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(side="left")

        self._kb_light_menu = ttk.Combobox(lm_row, textvariable=self._kb_light_var,
                                           values=LIGHT_MODE_NAMES, width=18,
                                           state="readonly")
        self._kb_light_menu.pack(side="right")
        self._kb_light_menu.bind("<<ComboboxSelected>>", self._on_kb_light_mode_change)

        # 3. Custom Color Palette Card
        card_col = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_col.pack(fill="x", pady=4)

        tk.Label(card_col, text="Custom RGB Palette", font=("Segoe UI", 10, "bold"),
                 fg=ACCENT, bg=CARD).pack(anchor="w")

        from devices.keyboard import COLOR_PRESETS
        pal_row = tk.Frame(card_col, bg=CARD)
        pal_row.pack(fill="x", pady=(8, 2))

        for name, hex_code, (r, g, b) in COLOR_PRESETS:
            is_rain = (name == "Rainbow")
            cbtn = tk.Label(pal_row,
                            text="Rainbow" if is_rain else "●",
                            font=("Segoe UI", 8 if is_rain else 12, "bold"),
                            fg=ACCENT if is_rain else hex_code,
                            bg=CARD, cursor="hand2", padx=4)
            cbtn.pack(side="left")
            cbtn.bind("<Button-1>", lambda e, red=r, green=g, blue=b, rain=is_rain: self._on_kb_color_click(red, green, blue, rain))

        # 4. Brightness & Speed Sliders Card (Hardware Control)
        card_tune = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_tune.pack(fill="x", pady=4)

        tk.Label(card_tune, text="Hardware Sliders (Sonix ACK Handshake)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        # Brightness row
        br_row = tk.Frame(card_tune, bg=CARD)
        br_row.pack(fill="x", pady=(8, 4))
        tk.Label(br_row, text="Brightness", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._kb_br_slider = tk.Scale(br_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_br_var,
                                      command=self._on_kb_brightness_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=200, showvalue=False)
        self._kb_br_slider.pack(side="left")
        self._kb_br_lbl = tk.Label(br_row, text="Level 5", font=("Segoe UI", 8, "bold"),
                                   fg=TEXT, bg=CARD)
        self._kb_br_lbl.pack(side="left", padx=8)

        # Speed row
        sp_row = tk.Frame(card_tune, bg=CARD)
        sp_row.pack(fill="x", pady=(4, 2))
        tk.Label(sp_row, text="Speed", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._kb_sp_slider = tk.Scale(sp_row, from_=1, to=5, orient="horizontal",
                                      variable=self._kb_sp_var,
                                      command=self._on_kb_speed_change,
                                      bg=CARD, fg=TEXT, troughcolor=BORDER,
                                      highlightthickness=0, length=200, showvalue=False)
        self._kb_sp_slider.pack(side="left")
        self._kb_sp_lbl = tk.Label(sp_row, text="Speed 3", font=("Segoe UI", 8, "bold"),
                                   fg=TEXT, bg=CARD)
        self._kb_sp_lbl.pack(side="left", padx=8)

    def _on_kb_light_mode_change(self, event=None) -> None:
        if self._keyboard is None:
            return
        name = self._kb_light_var.get()
        threading.Thread(target=self._keyboard.set_light_mode_by_name, args=(name,),
                         daemon=True, name="kb-light").start()

    def _on_kb_color_click(self, r: int, g: int, b: int, is_rainbow: bool) -> None:
        if self._keyboard is None:
            return
        threading.Thread(target=self._keyboard.set_color, args=(r, g, b, is_rainbow),
                         daemon=True, name="kb-color").start()
        if is_rainbow:
            self._kb_light_var.set("Colourful")
        else:
            self._kb_light_var.set("Static")

    def _on_kb_brightness_change(self, val) -> None:
        if self._keyboard is None:
            return
        lvl = int(float(val))
        self._kb_br_lbl.configure(text=f"Level {lvl}")
        threading.Thread(target=self._keyboard.set_brightness, args=(lvl,),
                         daemon=True, name="kb-br").start()

    def _on_kb_speed_change(self, val) -> None:
        if self._keyboard is None:
            return
        lvl = int(float(val))
        self._kb_sp_lbl.configure(text=f"Speed {lvl}")
        threading.Thread(target=self._keyboard.set_speed, args=(lvl,),
                         daemon=True, name="kb-sp").start()

    # ------------------------------------------------------------------
    # Page 3: dbE Kumo GS1X Pro (Wireless Headset)
    # ------------------------------------------------------------------

    def _build_headset_page(self) -> None:
        page = tk.Frame(self._content_area, bg=BG)
        self._tab_pages["headset"] = page

        # 1. Device Status Card
        card_stat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_stat.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(card_stat, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text="dbE Kumo GS1X Pro", font=("Segoe UI", 11, "bold"),
                 fg=TEXT, bg=CARD).pack(side="left")
        self._hs_status_lbl = tk.Label(row1, text="● Dongle Not Detected",
                                       font=("Segoe UI", 9, "bold"),
                                       fg=RED, bg=CARD)
        self._hs_status_lbl.pack(side="right")

        # Smart Battery Tracker Card
        card_bat = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_bat.pack(fill="x", pady=4)

        tk.Label(card_bat, text="Smart Battery Tracker (16h Active Life)",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        bat_row = tk.Frame(card_bat, bg=CARD)
        bat_row.pack(fill="x", pady=(8, 4))
        tk.Label(bat_row, text="Est. Battery", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._hs_bat_bar = _BatteryBar(bat_row, width=170)
        self._hs_bat_bar.pack(side="left", padx=6)
        self._hs_bat_lbl = tk.Label(bat_row, text="N/A", font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._hs_bat_lbl.pack(side="left")

        btn_row = tk.Frame(card_bat, bg=CARD)
        btn_row.pack(fill="x", pady=(6, 2))
        self._hs_usage_lbl = tk.Label(btn_row, text="Usage: 0h 00m", font=("Segoe UI", 8),
                                      fg=TEXT_MUTED, bg=CARD)
        self._hs_usage_lbl.pack(side="left")

        charged_btn = tk.Label(btn_row, text="Mark Charged", font=("Segoe UI", 8, "bold"),
                               fg=TEXT, bg=BORDER, cursor="hand2", padx=10, pady=3)
        charged_btn.pack(side="right")
        charged_btn.bind("<Button-1>", lambda e: self._on_mark_charged())
        charged_btn.bind("<Enter>", lambda e: charged_btn.configure(bg=CARD_HOVER, fg=ACCENT))
        charged_btn.bind("<Leave>", lambda e: charged_btn.configure(bg=BORDER, fg=TEXT))

        # Windows Master Volume Card
        card_vol = tk.Frame(page, bg=CARD, padx=14, pady=10)
        card_vol.pack(fill="x", pady=4)

        tk.Label(card_vol, text="Windows Master Audio Volume",
                 font=("Segoe UI", 10, "bold"), fg=ACCENT, bg=CARD).pack(anchor="w")

        vol_row = tk.Frame(card_vol, bg=CARD)
        vol_row.pack(fill="x", pady=(8, 2))
        tk.Label(vol_row, text="Master Vol", font=("Segoe UI", 8),
                 fg=TEXT_MUTED, bg=CARD, width=12, anchor="w").pack(side="left")
        self._hs_vol_slider = tk.Scale(vol_row, from_=0, to=100, orient="horizontal",
                                       variable=self._hs_vol_var,
                                       command=self._on_volume_change,
                                       bg=CARD, fg=TEXT, troughcolor=BORDER,
                                       highlightthickness=0, length=200, showvalue=False)
        self._hs_vol_slider.pack(side="left")
        self._hs_vol_lbl = tk.Label(vol_row, text="50%", font=("Segoe UI", 8, "bold"),
                                    fg=TEXT, bg=CARD)
        self._hs_vol_lbl.pack(side="left", padx=8)

    def _on_volume_change(self, val) -> None:
        vol = int(float(val))
        self._hs_vol_lbl.configure(text=f"{vol}%")
        if self._headset:
            threading.Thread(target=self._headset.set_volume, args=(vol,),
                             daemon=True, name="hs-vol").start()

    def _on_mark_charged(self) -> None:
        if self._headset:
            self._headset.mark_charged()
            self._refresh_headset()

    # ------------------------------------------------------------------
    # Bottom Status Bar
    # ------------------------------------------------------------------

    def _build_bottom_status_bar(self) -> None:
        sbar = tk.Frame(self._root, bg=CARD, padx=14, pady=6)
        sbar.pack(fill="x", side="bottom")

        self._sbar_devices_lbl = tk.Label(sbar, text="● Detecting devices...",
                                          font=("Segoe UI", 8),
                                          fg=TEXT_MUTED, bg=CARD)
        self._sbar_devices_lbl.pack(side="left")

        self._sbar_battery_lbl = tk.Label(sbar, text="",
                                          font=("Segoe UI", 8, "bold"),
                                          fg=GREEN, bg=CARD)
        self._sbar_battery_lbl.pack(side="right")

    # ------------------------------------------------------------------
    # Visibility & Refresh loop
    # ------------------------------------------------------------------

    def is_visible(self) -> bool:
        """Return True if dashboard window is currently open/visible."""
        return self._visible

    def show(self) -> None:
        if self._root is None:
            return
        self._visible = True
        self._root.deiconify()
        self._root.lift()
        self._root.focus_set()
        self.refresh()
        self._schedule_refresh()

    def hide(self) -> None:
        self._visible = False
        if self._refresh_job and self._root:
            self._root.after_cancel(self._refresh_job)
            self._refresh_job = None
        if self._root:
            self._root.withdraw()

    def toggle(self) -> None:
        if self._visible:
            self.hide()
        else:
            self.show()

    def destroy(self) -> None:
        """Cleanly destroy window and cancel pending callbacks."""
        self.hide()
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

    def _schedule_refresh(self) -> None:
        if not self._visible or self._root is None:
            return
        self._refresh_job = self._root.after(3000, self._on_timer_refresh)

    def _on_timer_refresh(self) -> None:
        if self._visible:
            self.refresh()
            self._schedule_refresh()

    def scan_all(self) -> None:
        """Actively re-scans all devices and displays live feedback."""
        if hasattr(self, "_scan_btn") and self._scan_btn:
            self._scan_btn.configure(text="Scanning...", fg=ACCENT_HOVER, bg=BORDER)
        if hasattr(self, "_sbar_devices_lbl") and self._sbar_devices_lbl:
            self._sbar_devices_lbl.configure(text="● Scanning USB & HID ports...", fg=ORANGE)

        def _do_scan():
            if self._on_scan:
                try:
                    self._on_scan()
                except Exception as exc:
                    logger.debug("Scan error: %s", exc)
            if self._root:
                def _restore():
                    if hasattr(self, "_scan_btn") and self._scan_btn:
                        self._scan_btn.configure(text="Scan", fg=ACCENT, bg=CARD)
                    self.refresh()
                self._root.after(400, _restore)

        threading.Thread(target=_do_scan, daemon=True, name="active-scan").start()

    def refresh(self) -> None:
        """Update live telemetry for all components and the status bar."""
        if not self._root:
            return
        try:
            self._refresh_mouse()
            self._refresh_keyboard()
            self._refresh_headset()
            self._refresh_status_bar()
        except Exception as exc:
            logger.debug("Dashboard refresh error: %s", exc)

    def _refresh_mouse(self) -> None:
        if self._mouse is None:
            return
        st = self._mouse.get_status()
        conn_type = st.get("connection_type", "Disconnected")
        online = bool(st.get("online", False) or (conn_type not in ("Disconnected", None)))

        if online:
            self._mouse_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
            if hasattr(self, "_mouse_img_lbl") and self._noir_img_online:
                self._mouse_img_lbl.configure(image=self._noir_img_online)
        else:
            self._mouse_status_lbl.configure(text="● Disconnected", fg=RED)
            if hasattr(self, "_mouse_img_lbl") and self._noir_img_offline:
                self._mouse_img_lbl.configure(image=self._noir_img_offline)

        pct = st.get("battery_level")
        self._mouse_bat_bar.set_value(pct)
        self._mouse_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))

        v = st.get("battery_voltage")
        if v:
            self._mouse_volt_lbl.configure(text=f"({v/1000:.2f}V)")
        else:
            self._mouse_volt_lbl.configure(text="")

        dpi = st.get("current_dpi", 1200)
        self._mouse_dpi_val_lbl.configure(text=f"{dpi} DPI")
        for d, btn in self._dpi_buttons.items():
            btn.set_active(d == dpi)

        color = st.get("current_color")
        if color and hasattr(self, "_mouse_active_color_lbl"):
            self._mouse_active_color_lbl.configure(text=f"● {color.upper()}", fg=color)

        maps = st.get("button_mappings", {})
        if maps.get(4) and self._mouse_btn4_var.get() != maps[4]:
            self._mouse_btn4_var.set(maps[4])
        if maps.get(5) and self._mouse_btn5_var.get() != maps[5]:
            self._mouse_btn5_var.set(maps[5])

    def _refresh_keyboard(self) -> None:
        if self._keyboard is None:
            return
        st = self._keyboard.get_status()
        connected = st.get("connected", False)
        conn_type = st.get("connection_type", "Disconnected")

        if connected:
            self._kb_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
        else:
            self._kb_status_lbl.configure(text="● Disconnected", fg=RED)

        lm_name = st.get("light_mode_name", "Colourful")
        if self._kb_light_var.get() != lm_name:
            self._kb_light_var.set(lm_name)

        br = st.get("brightness", 5)
        if self._kb_br_var.get() != br:
            self._kb_br_var.set(br)
            self._kb_br_lbl.configure(text=f"Level {br}")

        sp = st.get("speed", 3)
        if self._kb_sp_var.get() != sp:
            self._kb_sp_var.set(sp)
            self._kb_sp_lbl.configure(text=f"Speed {sp}")

    def _refresh_headset(self) -> None:
        if self._headset is None:
            return
        st = self._headset.get_status()
        dongle = st.get("dongle_connected", False)
        conn_type = st.get("connection_type", "Disconnected")

        if dongle:
            self._hs_status_lbl.configure(text=f"● Connected ({conn_type})", fg=GREEN)
        else:
            self._hs_status_lbl.configure(text="● Dongle Not Detected", fg=RED)

        pct = st.get("battery_estimate", 0)
        self._hs_bat_bar.set_value(pct)
        self._hs_bat_lbl.configure(text=_pct_text(pct), fg=_battery_color(pct))

        hrs = st.get("usage_hours", 0.0)
        h = int(hrs)
        m = int((hrs - h) * 60)
        self._hs_usage_lbl.configure(text=f"Usage: {h}h {m:02d}m")

        vol = st.get("volume", 50)
        if self._hs_vol_var.get() != vol:
            self._hs_vol_var.set(vol)
            self._hs_vol_lbl.configure(text=f"{vol}%")

    def _refresh_status_bar(self) -> None:
        connected_count = 0
        batteries = []

        if self._mouse and self._mouse.get_status().get("online"):
            connected_count += 1
            b = self._mouse.get_status().get("battery_level")
            if b is not None:
                batteries.append(("Mouse", b))

        if self._keyboard and self._keyboard.get_status().get("connected"):
            connected_count += 1

        if self._headset and self._headset.get_status().get("dongle_connected"):
            connected_count += 1
            b = self._headset.get_status().get("battery_estimate")
            if b is not None:
                batteries.append(("Headset", b))

        # Status indicator
        if connected_count > 0:
            self._brand_dot.configure(fg=GREEN)
            self._sbar_devices_lbl.configure(
                text=f"● {connected_count} Device{'s' if connected_count > 1 else ''} Online",
                fg=GREEN
            )
        else:
            self._brand_dot.configure(fg=RED)
            self._sbar_devices_lbl.configure(text="● No devices connected", fg=RED)

        if batteries:
            dev_name, min_bat = min(batteries, key=lambda x: x[1])
            col = _battery_color(min_bat)
            self._sbar_battery_lbl.configure(text=f"● Lowest: {dev_name} {min_bat}%", fg=col)
        else:
            self._sbar_battery_lbl.configure(text="")
