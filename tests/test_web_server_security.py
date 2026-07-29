import os
import json
from pathlib import Path
from scripts.web_server import _save_settings, SETTINGS_PATH, _md_to_html

def test_settings_chmod(tmp_path, monkeypatch):
    test_settings_file = tmp_path / "_settings.json"
    monkeypatch.setattr("scripts.web_server.SETTINGS_PATH", str(test_settings_file))
    _save_settings({"api_key": "secret123"})
    assert test_settings_file.exists()
    assert test_settings_file.read_text(encoding="utf-8") != ""

def test_md_to_html_escaping():
    malicious = "Normal <img src=x onerror=alert(1)> text"
    rendered = _md_to_html(malicious)
    assert "<img src=x onerror=alert(1)>" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
