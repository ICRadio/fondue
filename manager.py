# manager.py
import json
import os

class SourceManager:
    def __init__(self, filepath="sources.json"):
        self.filepath = filepath
        self.sources = {}
        self.active = None
        self._load_sources()

    def _load_sources(self):
        if os.path.exists(self.filepath):
            with open(self.filepath, "r") as f:
                self.sources = json.load(f)
        else:
            self.sources = {}

    def _save_sources(self):
        with open(self.filepath, "w") as f:
            json.dump(self.sources, f, indent=2)

    def add_source(self, name, path):
        self.sources[name] = path
        self._save_sources()

    def remove_source(self, name):
        if name in self.sources:
            del self.sources[name]
            self._save_sources()

    def get_sources(self):
        return self.sources

    def get_active(self):
        return self.active

    def switch_to(self, name):
        if name not in self.sources:
            raise ValueError(f"Source '{name}' not found.")
        old = self.active
        self.active = name
        return old, name
