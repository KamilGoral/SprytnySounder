#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Czy app.py buduje trasy i renderuje strony — bez Windows (pycaw/pygame zaslepione).
Lapie rozjazd trasa <-> szablon, np. zmienna usunieta z render_template, ale
zostawiona w Jinji. Uruchom: python test_strony.py (potrzebny tylko flask)."""
import os
import sys
import types

for name in ("pygame", "pythoncom", "pycaw", "pycaw.pycaw", "comtypes"):
    module = types.ModuleType(name)
    module.__getattr__ = lambda attr: (lambda *a, **k: None)
    sys.modules[name] = module
sys.modules["pycaw.pycaw"].AudioUtilities = types.SimpleNamespace(
    GetAllSessions=lambda: [], GetSpeakers=lambda: None, GetAllDevices=lambda: [])
sys.modules["pycaw.pycaw"].IAudioEndpointVolume = None
sys.modules["comtypes"].CLSCTX_ALL = None
sys.modules["pythoncom"].CoInitialize = lambda: None
sys.modules["pygame"].mixer = types.SimpleNamespace(
    get_init=lambda: False, init=lambda: None, quit=lambda: None, music=None)
sys.modules["pygame"].time = types.SimpleNamespace(wait=lambda ms: None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import app  # noqa: E402

client = app.app.test_client()

for path in ("/", "/tablet", "/admin", "/api/status", "/api/log?lines=5"):
    assert client.get(path).status_code == 200, f"{path} nie odpowiada 200"

assert "Pokaż log" in client.get("/admin").get_data(as_text=True)

# Bony wycofane (1.6.9) — ani sladu w trasach i na ekranach
for path in ("/bony", "/api/bony"):
    assert client.get(path).status_code == 404, f"{path} wciaz istnieje"
for path in ("/", "/admin", "/tablet"):
    assert "bony" not in client.get(path).get_data(as_text=True).lower(), path

print("OK - strony renderuja sie, /api/log dziala, bonow nie ma")
