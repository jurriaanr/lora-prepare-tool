# config.py
import os
import json

CONFIG_FILE = "config.json"
HISTORY_FILE = "suggest_history.txt"   # semicolon-separated: tag;count
GLOBAL_WORDS_FILE = "global_words.txt"

# Note: keep output_dir/processed_dir as RELATIVE defaults.
# They will be resolved against the CURRENT IMAGE'S FOLDER when used.
DEFAULTS = {
    "geometry": None,
    "frame_size": 768,
    "output_dir": "output",        # relative to image folder
    "processed_dir": "processed",  # relative to image folder
    "last_open_dir": None,
}

class AppConfig:
    def __init__(self, app_dir: str):
        self.app_dir = app_dir
        self.path = os.path.join(app_dir, CONFIG_FILE)
        self.data = dict(DEFAULTS)
        self.load()

        # Ensure we have *some* string values (stay relative by default)
        if not isinstance(self.data.get("output_dir"), str) or not self.data["output_dir"].strip():
            self.data["output_dir"] = DEFAULTS["output_dir"]
        if not isinstance(self.data.get("processed_dir"), str) or not self.data["processed_dir"].strip():
            self.data["processed_dir"] = DEFAULTS["processed_dir"]

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.data.update(loaded)  # <-- merge all keys, not just those in DEFAULTS
        except Exception:
            pass

    def save(self):
        # Persist exactly what the user entered (relative paths stay relative)
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception:
            pass

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    # ---- Directory resolution ----
    def _expand(self, path_str: str) -> str:
        """Expand ~ and environment vars, but do NOT absolutize."""
        return os.path.expandvars(os.path.expanduser(path_str))

    def _resolve_for_image(self, stored_path: str, src_path: str) -> str:
        """
        Resolve a stored path string for a given image:
        - If stored_path is absolute -> return it after expanding ~ and env vars.
        - If stored_path is relative or empty -> join with the image's directory.
        """
        stored_path = (stored_path or "").strip()
        img_dir = os.path.dirname(os.path.abspath(src_path))
        if not stored_path:
            stored_path = "output"  # fallback, shouldn't normally happen due to defaults
        expanded = self._expand(stored_path)
        if os.path.isabs(expanded):
            return expanded
        return os.path.abspath(os.path.join(img_dir, expanded))

    def effective_output_dir_for(self, src_path: str) -> str:
        return self._resolve_for_image(self.get("output_dir", DEFAULTS["output_dir"]), src_path)

    def effective_processed_dir_for(self, src_path: str) -> str:
        return self._resolve_for_image(self.get("processed_dir", DEFAULTS["processed_dir"]), src_path)
