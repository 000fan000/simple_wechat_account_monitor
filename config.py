import os
import yaml
from pathlib import Path

class Config:
    def __init__(self, config_file: str = "config.yaml"):
        self._config = {}
        self._config_file = config_file
        self.reload()

    def reload(self):
        if os.path.exists(self._config_file):
            with open(self._config_file, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}

    def get(self, key: str, default=None):
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value):
        keys = key.split(".")
        d = self._config
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value

    def save_config(self):
        with open(self._config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._config, f, allow_unicode=True)

cfg = Config()


def getWxToken():
    token_file = cfg.get("wx.token_file", "data/wx_token.json")
    if os.path.exists(token_file):
        with open(token_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def saveWxToken(token_data: dict):
    os.makedirs(os.path.dirname(cfg.get("wx.token_file", "data/wx_token.json")), exist_ok=True)
    token_file = cfg.get("wx.token_file", "data/wx_token.json")
    with open(token_file, "w", encoding="utf-8") as f:
        json.dump(token_data, f, ensure_ascii=False, indent=2)


import json