# -*- coding: utf-8 -*-
"""
SprytnySounder — System komunikat³w g³osowych na salê sprzeda¿y.
Automat: Kamil @ SprytnyKupiec
Wersja: 1.1.0

Ulepszenia:
- Dni wolne od handlu — system wyciszony w œwiêta i niedziele niehandlowe
- Konfiguracja odwróconych niedziel (sklep Krótka 2a)
- Panel z przyciskami Recyklomat
- Auto-updater przez git
"""

from flask import Flask, request, jsonify, render_template
import os
import time
import threading
import subprocess
import sys
import json
from datetime import datetime, timedelta
from pycaw.pycaw import AudioUtilities
from flask_cors import CORS
import pygame
import pythoncom
import requests

# === W³asne modu³y ===
from poland_holidays import is_trade_day, get_trade_info

# === Konfiguracja ===
CONFIG_FILE = "config.json"

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

HOST = config.get("host", "0.0.0.0")
PORT = config.get("port", 8989)
SOUND_DIRECTORY = config.get("sound_folder", "static/sounds")
LOG_FILE = config.get("log_file", "log.txt")
STATS_FILE = config.get("stats_file", "statystyka.txt")
VERSION = config.get("version", "1.1.0")
SUNDAY_INVERTED = config.get("sunday_inverted", False)
UPDATE_ENABLED = config.get("update_enabled", True)
UPDATE_URL = config.get("update_url", "")
UPDATE_INTERVAL = config.get("update_check_interval_hours", 24)
STORE_NAME = config.get("store_name", "SprytnySounder")

if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.abspath(".")

# Flask
app = Flask(__name__,
            static_folder=os.path.join(BASE_PATH, "static"),
            template_folder=os.path.join(BASE_PATH, "templates"))
CORS(app)

# Pygame audio
pygame.init()
pygame.mixer.init()
pythoncom.CoInitialize()

# === Flagi systemowe ===
_system_muted = False  # Czy system jest wyciszony (dzieñ wolny od handlu)
_last_trade_check = None
_last_trade_result = None


def log_event(filename):
    """Zapisuje zdarzenie do loga."""
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.write(f"{timestamp} - Odtworzono plik: {filename}\n")


def update_stats(filename):
    """Aktualizuje statystykê odtworzeñ."""
    stats = {}
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as stats_file:
            for line in stats_file:
                line = line.strip()
                if ": " in line:
                    name, count = line.split(": ", 1)
                    stats[name] = int(count)
    stats[filename] = stats.get(filename, 0) + 1
    with open(STATS_FILE, "w", encoding="utf-8") as stats_file:
        for name, count in stats.items():
            stats_file.write(f"{name}: {count}\n")


def set_all_sessions_volume(target_volume, exclude_names=None):
    """Ustawia g³oœnoœæ wszystkich sesji audio na podany poziom."""
    pythoncom.CoInitialize()
    exclude_names = exclude_names or set()
    for session in AudioUtilities.GetAllSessions():
        if session.Process:
            try:
                name = session.Process.name().lower()
                if name not in exclude_names:
                    session.SimpleAudioVolume.SetMasterVolume(target_volume / 100.0, None)
            except Exception:
                continue


def play_single_sound(path):
    """Odtwarza pojedynczy plik dŸwiêkowy przez pygame."""
    if not os.path.exists(path):
        print(f"⚠️ Plik nie istnieje: {path}")
        return
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(path)
    pygame.mixer.music.set_volume(1.0)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(100)


def check_trade_day():
    """
    Sprawdza czy dzisiaj jest dzieñ handlowy.
    Uwzglêdnia konfiguracjê sunday_inverted.
    """
    global _last_trade_check, _last_trade_result, _system_muted

    now = datetime.now()
    today = now.date()

    # Cache na dziœ
    if _last_trade_check == today:
        return _last_trade_result

    info = get_trade_info(today, sunday_inverted=SUNDAY_INVERTED)
    _last_trade_check = today
    _last_trade_result = info
    _system_muted = not info["is_trade_day"]

    if _system_muted:
        print(f"🔇 SYSTEM WYCISZONY: {info['reason']}")
    else:
        print(f"🔊 SYSTEM AKTYWNY: {info['reason']}")

    return info


def play_sound_with_isolation(sound_path):
    """
    Odtwarza dŸwiêk z izolacj¹ g³oœnoœci.
    Najpierw sprawdza czy dziœ jest dzieñ handlowy.
    """
    # SprawdŸ czy wolno graæ
    trade_info = check_trade_day()
    if not trade_info["is_trade_day"]:
        print(f"⛔ Blokada: {trade_info['reason']} — dŸwiêk nie zostanie odtworzony")
        return

    try:
        pythoncom.CoInitialize()
        own_name = os.path.basename(sys.executable).lower()
        exclude = {own_name}

        # Wycisz resztê systemu do 5%
        set_all_sessions_volume(5, exclude_names=exclude)

        # Rozgrzewka
        warmup_path = os.path.join(SOUND_DIRECTORY, "ping.mp3")
        if os.path.exists(warmup_path):
            play_single_sound(warmup_path)
            time.sleep(0.1)

        # W³aœciwy komunikat
        play_single_sound(sound_path)

        # Przywróæ do 33%
        set_all_sessions_volume(33, exclude_names=exclude)

    except Exception as e:
        print(f"❌ B³¹d odtwarzania: {e}")
    finally:
        pygame.mixer.quit()


# === AUTO-UPDATER ===

def check_for_updates():
    """
    Sprawdza czy dostêpna jest nowsza wersja.
    Dzia³a na dwa sposoby:
    1. Jeśli git dostêpny — wykonuje git pull
    2. Jeśli nie — sprawdza wersjê przez HTTP
    """
    if not UPDATE_ENABLED or not UPDATE_URL:
        return {"status": "disabled", "message": "Auto-update wy³¹czony lub brak URL"}

    try:
        # Próbuj przez git
        if os.path.exists(os.path.join(BASE_PATH, ".git")):
            result = subprocess.run(
                ["git", "pull"],
                cwd=BASE_PATH,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                if "Already up to date" in result.stdout:
                    return {"status": "ok", "message": "Ju¿ aktualne"}
                else:
                    return {"status": "updated", "message": "Zaktualizowano!", "detail": result.stdout}
            else:
                return {"status": "error", "message": f"Git error: {result.stderr}"}

        # Fallback: HTTP version check z GitHub releases
        try:
            # Próba pobrania pliku wersji z repozytorium
            version_url = UPDATE_URL.rstrip("/") + "/raw/main/version.txt"
            resp = requests.get(version_url, timeout=5)
            if resp.status_code == 200:
                remote_version = resp.text.strip()
                if remote_version != VERSION:
                    return {"status": "available", "message": f"Dostêpna wersja {remote_version}"}
                return {"status": "ok", "message": "Ju¿ aktualne"}
        except Exception:
            pass

        return {"status": "unknown", "message": "Nie mo¿na sprawdziæ"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


def auto_update_loop():
    """Pêtla t³a — sprawdza aktualizacje co UPDATE_INTERVAL godzin."""
    time.sleep(10)  # Poczekaj a¿ Flask wystartuje
    while True:
        try:
            result = check_for_updates()
            print(f"[Auto-Update] {result['status']}: {result['message']}")
            if result["status"] == "updated":
                # Restart aplikacji po aktualizacji
                print("[Auto-Update] Restartujê aplikacjê...")
                os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception as e:
            print(f"[Auto-Update] B³¹d: {e}")

        time.sleep(UPDATE_INTERVAL * 3600)


# === ENDPOINTY API ===

@app.route('/play-sound', methods=['POST'])
def play_sound_route():
    """Endpoint do uploadu i odtwarzania pliku dŸwiêkowego."""
    # SprawdŸ czy wolno graæ
    trade_info = check_trade_day()
    if not trade_info["is_trade_day"]:
        return jsonify({
            "error": f"System wyciszony: {trade_info['reason']}",
            "trade_info": trade_info
        }), 423  # 423 Locked

    try:
        file = request.files.get('path')
        if file is None:
            return jsonify({"error": "No file provided"}), 400

        temp_path = "temp_sound_file.mp3"
        file.save(temp_path)

        def play_in_thread():
            try:
                play_sound_with_isolation(temp_path)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        t = threading.Thread(target=play_in_thread)
        t.start()
        t.join(timeout=15)

        log_event(temp_path)
        update_stats(temp_path)

        return jsonify({"status": "Success", "trade_info": trade_info}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/play-defined-sound', methods=['POST'])
def play_defined_sound():
    """Endpoint do odtwarzania zdefiniowanego dŸwiêku po nazwie pliku."""
    # SprawdŸ czy wolno graæ
    trade_info = check_trade_day()
    if not trade_info["is_trade_day"]:
        return jsonify({
            "error": f"System wyciszony: {trade_info['reason']}",
            "trade_info": trade_info
        }), 423

    try:
        data = request.get_json()
        filename = data.get("filename")
        if not filename:
            return jsonify({"error": "Brak nazwy pliku"}), 400

        file_path = os.path.join(SOUND_DIRECTORY, filename)
        if not os.path.exists(file_path):
            return jsonify({"error": "Plik nie istnieje"}), 404

        def play_in_thread():
            try:
                play_sound_with_isolation(file_path)
            except Exception as e:
                print(f"Error during playback: {e}")

        t = threading.Thread(target=play_in_thread)
        t.start()
        t.join(timeout=15)

        log_event(filename)
        update_stats(filename)

        return jsonify({
            "status": "Success",
            "played_file": filename,
            "trade_info": trade_info
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    """Zwraca pe³ny status systemu."""
    trade_info = check_trade_day()

    # Statystyki
    stats = {}
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ": " in line:
                    name, count = line.split(": ", 1)
                    stats[name] = int(count)

    return jsonify({
        "status": "running",
        "version": VERSION,
        "store_name": STORE_NAME,
        "muted": _system_muted,
        "sunday_inverted": SUNDAY_INVERTED,
        "trade_info": trade_info,
        "update_enabled": UPDATE_ENABLED,
        "stats": stats,
        "sounds_available": sorted(os.listdir(SOUND_DIRECTORY)) if os.path.exists(SOUND_DIRECTORY) else []
    })


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Odczytuje lub aktualizuje konfiguracjê."""
    global SUNDAY_INVERTED, config

    if request.method == 'POST':
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        # Aktualizuj dozwolone pola
        if "sunday_inverted" in data:
            SUNDAY_INVERTED = bool(data["sunday_inverted"])
            config["sunday_inverted"] = SUNDAY_INVERTED
            # Zresetuj cache dnia
            global _last_trade_check
            _last_trade_check = None

        if "store_name" in data:
            config["store_name"] = str(data["store_name"])

        if "update_enabled" in data:
            config["update_enabled"] = bool(data["update_enabled"])

        if "update_url" in data:
            config["update_url"] = str(data["update_url"])

        # Zapisz config
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            return jsonify({"error": f"Nie mo¿na zapisaæ configu: {e}"}), 500

        return jsonify({"status": "ok", "config": config})

    # GET
    return jsonify({"config": config})


@app.route('/api/check-update', methods=['POST'])
def api_check_update():
    """Rêczne wywo³anie sprawdzenia aktualizacji."""
    result = check_for_updates()
    return jsonify(result)


@app.route('/api/sounds', methods=['GET'])
def api_list_sounds():
    """Zwraca listê dostêpnych dŸwiêków."""
    sounds = []
    sound_dir = os.path.join(BASE_PATH, SOUND_DIRECTORY)
    if os.path.exists(sound_dir):
        for f in sorted(os.listdir(sound_dir)):
            if f.endswith('.mp3') or f.endswith('.wav'):
                path = os.path.join(sound_dir, f)
                sounds.append({
                    "filename": f,
                    "size": os.path.getsize(path),
                    "path": f"/static/sounds/{f}"
                })
    return jsonify({"sounds": sounds})


# === STRONY ===

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/tablet')
def index_tablet():
    return render_template('index-tablet.html')


# === START ===

if __name__ == '__main__':
    try:
        own_name = os.path.basename(sys.executable).lower()
        exclude = {own_name}
        set_all_sessions_volume(33, exclude_names=exclude)
    except Exception as e:
        print(f"❌ B³¹d przy ustawianiu g³oœnoœci przy starcie: {e}")

    # SprawdŸ dzieñ handlowy
    check_trade_day()

    # Start auto-updater w tle
    if UPDATE_ENABLED and UPDATE_URL:
        updater = threading.Thread(target=auto_update_loop, daemon=True)
        updater.start()
        print(f"🔄 Auto-updater w³¹czony (co {UPDATE_INTERVAL}h)")

    print(f"📢 SprytnySounder v{VERSION} wystartowa³")
    print(f"   Host: {HOST}:{PORT}")
    print(f"   Odwrócone niedziele: {SUNDAY_INVERTED}")
    print(f"   Wyciszenie: {'TAK' if _system_muted else 'NIE'}")

    app.run(host=HOST, port=PORT, debug=True, threaded=False)
