r"""
audio/equalizer_apo.py
EqualizerAPO - Read and write Equalizer APO config.txt for EQ profile switching.
Config file: E:\Master APP\Equalizer APO\config\config.txt
APO applies changes in real-time when config.txt is saved.
"""

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(r"E:\Master APP\Equalizer APO\config\config.txt")

# ---------------------------------------------------------------------------
# EQ Profile Definitions
# Each profile is a list of filter lines for Equalizer APO's config format.
# Filter syntax: Filter N: ON PK Fc HZ Gain dB Q 1.0
# ---------------------------------------------------------------------------

_PROFILES: Dict[str, List[str]] = {
    "fps_step_booster": [
        "# Profile: FPS Step Booster",
        "# Boost footstep frequencies for competitive FPS",
        "Preamp: -3 dB",
        "Filter 1: ON PK Fc 316 Hz Gain 4.5 dB Q 1.41",
        "Filter 2: ON PK Fc 1288 Hz Gain 7.5 dB Q 1.41",
        "Filter 3: ON PK Fc 2432 Hz Gain 7.5 dB Q 1.41",
        "Filter 4: ON PK Fc 4140 Hz Gain 5.5 dB Q 1.41",
        "Filter 5: ON PK Fc 6800 Hz Gain 6.0 dB Q 1.41",
    ],
    "bass_boost": [
        "# Profile: Bass Boost",
        "# Heavy low-end impact for EDM and explosion immersion",
        "Preamp: -4 dB",
        "Filter 1: ON PK Fc 60 Hz Gain 9.0 dB Q 1.0",
        "Filter 2: ON PK Fc 100 Hz Gain 7.5 dB Q 1.2",
        "Filter 3: ON PK Fc 150 Hz Gain 5.0 dB Q 1.2",
        "Filter 4: ON PK Fc 2500 Hz Gain 2.0 dB Q 1.0",
        "Filter 5: ON PK Fc 8000 Hz Gain 3.0 dB Q 1.0",
    ],
    "music_movie": [
        "# Profile: Music / Movie",
        "# Warm bass + bright treble for immersive listening",
        "Preamp: -2 dB",
        "Filter 1: ON PK Fc 60 Hz Gain 4.0 dB Q 0.71",
        "Filter 2: ON PK Fc 120 Hz Gain 2.5 dB Q 1.00",
        "Filter 3: ON PK Fc 500 Hz Gain -1.5 dB Q 1.41",
        "Filter 4: ON PK Fc 2000 Hz Gain 1.0 dB Q 1.00",
        "Filter 5: ON PK Fc 8000 Hz Gain 3.5 dB Q 1.41",
        "Filter 6: ON PK Fc 16000 Hz Gain 2.0 dB Q 0.71",
    ],
    "flat": [
        "# Profile: Flat / Normal",
        "# No EQ adjustments - true flat response",
        "Preamp: 0 dB",
    ],
    "gaming_surround": [
        "# Profile: Gaming Surround",
        "# Mid-range and high-frequency boost for positional audio",
        "Preamp: -3 dB",
        "Filter 1: ON PK Fc 300 Hz Gain 2.5 dB Q 1.00",
        "Filter 2: ON PK Fc 900 Hz Gain 3.5 dB Q 1.00",
        "Filter 3: ON PK Fc 2500 Hz Gain 5.0 dB Q 1.41",
        "Filter 4: ON PK Fc 5000 Hz Gain 4.5 dB Q 1.41",
        "Filter 5: ON PK Fc 10000 Hz Gain 3.5 dB Q 1.00",
    ],
}

_PROFILE_DISPLAY_NAMES: Dict[str, str] = {
    "fps_step_booster": "FPS Step Booster",
    "bass_boost": "Bass Boost",
    "music_movie": "Music / Vocal",
    "flat": "Flat / Neutral",
    "gaming_surround": "Gaming Surround",
}

# Lines to always include at the top of config.txt (device include chain)
_CONFIG_HEADER = [
    "# Equalizer APO Configuration",
    "# Managed by Peripheral Hub - do not edit manually",
    "# https://sourceforge.net/projects/equalizerapo/",
    "",
    "Device: all",
    "Channel: all",
    "",
]


class EqualizerAPO:
    """
    Manages Equalizer APO's config.txt to switch between EQ profiles.
    Writes atomically: new content -> temp file -> rename, so APO
    always reads a complete file.
    """

    def __init__(self, config_path: Path = CONFIG_PATH):
        self._config_path = Path(config_path)
        self._current_profile: str = "flat"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write_atomic(self, lines: List[str]) -> bool:
        """Write lines to a temp file then atomically replace config.txt."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._config_path.with_suffix(".tmp")
            content = "\n".join(lines) + "\n"
            tmp_path.write_text(content, encoding="utf-8")
            # Atomic replace (Windows: rename over existing)
            shutil.move(str(tmp_path), str(self._config_path))
            logger.info("Equalizer APO config written: %d lines", len(lines))
            return True
        except Exception as exc:
            logger.warning("EqualizerAPO write error: %s", exc)
            return False

    def _build_config(self, profile_key: str) -> List[str]:
        """Assemble full config.txt content for a given profile."""
        lines = list(_CONFIG_HEADER)
        profile_lines = _PROFILES.get(profile_key, _PROFILES["flat"])
        lines.extend(profile_lines)
        return lines

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def current_profile(self) -> str:
        return self._current_profile

    @property
    def available_profiles(self) -> List[str]:
        return list(_PROFILES.keys())

    def get_display_name(self, profile_key: str) -> str:
        """Return the human-readable name for a profile key."""
        return _PROFILE_DISPLAY_NAMES.get(profile_key, profile_key)

    _KEY_MAP = {
        "FPS Step Booster": "fps_step_booster",
        "fps_step_booster": "fps_step_booster",
        "Bass Boost": "bass_boost",
        "bass_boost": "bass_boost",
        "Music / Vocal": "music_movie",
        "music_movie": "music_movie",
        "Gaming Surround": "gaming_surround",
        "gaming_surround": "gaming_surround",
        "Flat / Neutral": "flat",
        "flat": "flat",
    }

    def apply_profile(self, profile_key: str) -> bool:
        """
        Apply the named EQ profile by writing Equalizer APO's config.txt.
        Supports both display names and internal keys.
        Returns True on success.
        """
        norm_key = self._KEY_MAP.get(profile_key, profile_key.lower().replace(" ", "_"))
        if norm_key not in _PROFILES:
            logger.warning("Unknown EQ profile: %s", profile_key)
            return False

        if not self._config_path.parent.exists():
            logger.warning("Equalizer APO config directory not found: %s",
                           self._config_path.parent)
            return False

        lines = self._build_config(norm_key)
        ok = self._write_atomic(lines)
        if ok:
            self._current_profile = norm_key
            logger.info("EQ profile applied: %s (%s)", profile_key, norm_key)
        return ok

    def apply_custom_sliders(self, bass_pct: int, clarity_pct: int, surround_pct: int) -> bool:
        """
        Dynamically shape frequency response in real time based on UI sliders:
        - bass_pct: 0 to 100 -> 0 to +12 dB at 80 Hz
        - clarity_pct: 0 to 100 -> 0 to +12 dB at 2500 Hz
        - surround_pct: 0 to 100 -> 0 to +8 dB at 8000 Hz
        """
        bass_gain = (max(0, min(100, bass_pct)) / 100.0) * 12.0
        clarity_gain = (max(0, min(100, clarity_pct)) / 100.0) * 12.0
        spatial_gain = (max(0, min(100, surround_pct)) / 100.0) * 8.0

        lines = list(_CONFIG_HEADER)
        lines.append(f"# Dynamic Frequency Shaping: Bass={bass_pct}%, Clarity={clarity_pct}%, 3D={surround_pct}%")
        lines.append("Preamp: -4 dB")
        if bass_gain > 0.1:
            lines.append(f"Filter 1: ON PK Fc 80 Hz Gain {bass_gain:.1f} dB Q 1.1")
        if clarity_gain > 0.1:
            lines.append(f"Filter 2: ON PK Fc 2500 Hz Gain {clarity_gain:.1f} dB Q 1.4")
        if spatial_gain > 0.1:
            lines.append(f"Filter 3: ON PK Fc 8000 Hz Gain {spatial_gain:.1f} dB Q 1.2")

        ok = self._write_atomic(lines)
        if ok:
            logger.info("Custom EQ sliders applied: Bass=%.1fdB, Clarity=%.1fdB, 3D=%.1fdB",
                        bass_gain, clarity_gain, spatial_gain)
        return ok

    def read_current_config(self) -> Optional[str]:
        """Read and return the current config.txt content."""
        try:
            if self._config_path.exists():
                return self._config_path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.debug("Read config error: %s", exc)
        return None

    def detect_current_profile(self) -> str:
        """
        Try to detect which profile is currently active by reading the config
        comment header. Falls back to 'flat' if not detectable.
        """
        content = self.read_current_config()
        if content is None:
            return "flat"
        for key in _PROFILES:
            display = _PROFILE_DISPLAY_NAMES.get(key, "")
            if display and f"# Profile: {display}" in content:
                return key
            # Also check key in comment
            if f"# Profile: {key}" in content:
                return key
        return "flat"

    def is_apo_installed(self) -> bool:
        """Return True if the Equalizer APO config directory exists."""
        return self._config_path.parent.exists()

    def is_installed(self) -> bool:
        """Alias for is_apo_installed()."""
        return self.is_apo_installed()

    def get_current_profile(self) -> str:
        """Return the currently detected or active EQ profile."""
        detected = self.detect_current_profile()
        self._current_profile = detected
        return detected
