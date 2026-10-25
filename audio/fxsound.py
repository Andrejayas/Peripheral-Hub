r"""
audio/fxsound.py
FxSound - Read and write FxSound settings for software audio enhancement.
Settings file: C:\Users\Andre\AppData\Roaming\FxSound\FxSound.settings
FxSound uses an XML properties format.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

SETTINGS_PATH = Path(os.environ.get("APPDATA", r"C:\Users\Andre\AppData\Roaming")) / "FxSound" / "FxSound.settings"

BUILTIN_PRESETS = [
    "Bass Boost",
    "Vocal Enhancement",
    "Ambiance",
    "Loudness",
    "High Fidelity",
    "Podcast",
    "Gaming",
    "Movie",
    "Music",
]

FAC_DIR = Path(r"C:\Program Files\FxSound LLC\FxSound\Factsoft")


class FxSound:
    """
    Controls FxSound by reading and writing its XML settings file.
    FxSound monitors its settings file and applies changes in real-time.
    """

    def __init__(self, settings_path: Path = SETTINGS_PATH):
        self._settings_path = Path(settings_path)
        self._cached: Dict[str, str] = {}
        self._load()

    def _load(self) -> Dict[str, str]:
        """Load settings from XML file into cache."""
        try:
            if self._settings_path.exists():
                tree = ET.parse(self._settings_path)
                root = tree.getroot()
                self._cached = {}
                for val in root.findall("VALUE"):
                    name = val.attrib.get("name")
                    v = val.attrib.get("val")
                    if name is not None and v is not None:
                        self._cached[name] = v
            else:
                self._cached = self._defaults()
        except Exception as exc:
            logger.debug("FxSound load error: %s", exc)
            self._cached = self._defaults()
        return self._cached

    def _save(self) -> bool:
        """Write cached settings back to the XML settings file."""
        try:
            self._settings_path.parent.mkdir(parents=True, exist_ok=True)
            root = ET.Element("PROPERTIES")
            for name, val in self._cached.items():
                node = ET.SubElement(root, "VALUE")
                node.set("name", str(name))
                node.set("val", str(val))
            
            tree = ET.ElementTree(root)
            tmp = self._settings_path.with_suffix(".tmp")
            # Write with XML declaration and utf-8
            tree.write(tmp, encoding="utf-8", xml_declaration=True)
            shutil.move(str(tmp), str(self._settings_path))
            logger.debug("FxSound settings saved.")
            return True
        except Exception as exc:
            logger.warning("FxSound save error: %s", exc)
            return False

    @staticmethod
    def _defaults() -> Dict[str, str]:
        return {
            "power": "1",
            "preset": "Bass Boost",
            "output_device_id": "",
            "output_device_name": "",
            "master_gain": "0.0",
            "normalization": "0.0",
            "balance": "0.0",
        }

    @property
    def settings_path(self) -> Path:
        return self._settings_path

    def is_installed(self) -> bool:
        """Return True if FxSound settings file exists."""
        return self._settings_path.exists()

    def refresh(self) -> None:
        """Reload settings from disk."""
        self._load()

    def get_power(self) -> bool:
        """Return True if FxSound processing is enabled."""
        val = self._cached.get("power", "0")
        return str(val) in ("1", "true", "True")

    def set_power(self, enabled: bool) -> bool:
        """Enable or disable FxSound processing."""
        self._cached["power"] = "1" if enabled else "0"
        return self._save()

    def get_preset(self) -> str:
        """Return the currently active preset name."""
        return str(self._cached.get("preset", "Bass Boost"))

    def set_preset(self, preset_name: str) -> bool:
        """Switch to the named preset. Returns True on success."""
        self._cached["preset"] = preset_name
        return self._save()

    def get_master_gain(self) -> float:
        """Return master gain float."""
        try:
            return float(self._cached.get("master_gain", "0.0"))
        except (ValueError, TypeError):
            return 0.0

    def set_master_gain(self, gain: float) -> bool:
        """Set master gain float."""
        self._cached["master_gain"] = str(round(gain, 1))
        return self._save()

    def get_output_device_name(self) -> str:
        return str(self._cached.get("output_device_name", ""))

    def set_output_device(self, name: str, device_id: str = "") -> bool:
        self._cached["output_device_name"] = name
        if device_id:
            self._cached["output_device_id"] = device_id
        return self._save()

    def list_presets(self) -> List[str]:
        """Return list of available presets."""
        presets = list(BUILTIN_PRESETS)
        try:
            if FAC_DIR.exists():
                for fac in sorted(FAC_DIR.glob("*.fac")):
                    name = fac.stem
                    if name not in presets:
                        presets.append(name)
        except Exception as exc:
            logger.debug("FAC dir scan error: %s", exc)
        return presets

    def get_all_settings(self) -> Dict[str, str]:
        self._load()
        return dict(self._cached)
