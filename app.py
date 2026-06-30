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
# Warstwy (każda nadpisuje poprzednią):
#   1. config.defaults.json  – wspólne ustawienia z repo (te same na każdym sklepie)
#   2. locations/<location>.json – tożsamość placówki z repo (store_name, sunday_inverted...)
#      gdzie <location> to zawartość pliku location.txt (jedno słowo, per maszyna)
#   3. config.json – lokalne ustawienia maszyny (host auto-wykryty, nadpisania z panelu)
# Dzięki temu auto-update (repo) nigdy nie kasuje ustawień sklepu, a dodanie nowej
# placówki = dodanie locations/<nazwa>.json do repo + location.txt na maszynie.
CONFIG_FILE = "config.json"
DEFAULTS_FILE = "config.defaults.json"
LOCATION_FILE = "location.txt"
LOCATIONS_DIR = "locations"

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _read_location_name():
    try:
        with open(LOCATION_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def load_config():
    cfg = {}
    # 1. Wspólne domyślne z repo
    cfg.update(_read_json(DEFAULTS_FILE))
    # 2. Ustawienia per lokalizacja z repo
    location = _read_location_name()
    if location:
        cfg.update(_read_json(os.path.join(LOCATIONS_DIR, location + ".json")))
    # 3. Lokalne ustawienia maszyny (najwyższy priorytet). Stare sklepy mają tu pełny
    #    config.json, więc działają dokładnie jak dawniej (wsteczna zgodność).
    cfg.update(_read_json(CONFIG_FILE))
    return cfg

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

# Głośność (sterowane z panelu /admin, zapisywane do lokalnego config.json)
ANNOUNCEMENT_VOLUME = int(config.get("announcement_volume", 100))  # głośność komunikatu (%)
DUCK_VOLUME = int(config.get("duck_volume", 5))                    # tło PODCZAS komunikatu (%)
RESTORE_VOLUME = int(config.get("restore_volume", 33))            # tło PO komunikacie (%)

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
_system_muted = False  # Czy system jest wyciszony automatycznie (dzieñ wolny od handlu)
_manual_muted = bool(config.get("manual_mute", False))  # Rêczne wyciszenie z panelu /admin
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


def play_single_sound(path, volume=None):
    """Odtwarza pojedynczy plik dŸwiêkowy przez pygame.
    volume: 0-100 (%) — domyœlnie ANNOUNCEMENT_VOLUME z konfiguracji."""
    if not os.path.exists(path):
        print(f"⚠️ Plik nie istnieje: {path}")
        return
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    vol_pct = ANNOUNCEMENT_VOLUME if volume is None else volume
    vol = max(0.0, min(1.0, vol_pct / 100.0))
    pygame.mixer.music.load(path)
    pygame.mixer.music.set_volume(vol)
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


def play_sound_with_isolation(sound_path, force=False):
    """
    Odtwarza dŸwiêk z izolacj¹ g³oœnoœci.
    Sprawdza czy wolno graæ (dzieñ handlowy + rêczne wyciszenie),
    chyba ¿e force=True (test z panelu /admin gra zawsze).
    """
    if not force:
        if _manual_muted:
            print("⛔ Blokada: rêczne wyciszenie — dŸwiêk nie zostanie odtworzony")
            return
        trade_info = check_trade_day()
        if not trade_info["is_trade_day"]:
            print(f"⛔ Blokada: {trade_info['reason']} — dŸwiêk nie zostanie odtworzony")
            return

    try:
        pythoncom.CoInitialize()
        own_name = os.path.basename(sys.executable).lower()
        exclude = {own_name}

        # Wycisz resztê systemu na czas komunikatu
        set_all_sessions_volume(DUCK_VOLUME, exclude_names=exclude)

        # Rozgrzewka
        warmup_path = os.path.join(SOUND_DIRECTORY, "ping.mp3")
        if os.path.exists(warmup_path):
            play_single_sound(warmup_path)
            time.sleep(0.1)

        # W³aœciwy komunikat
        play_single_sound(sound_path)

        # Przywróæ g³oœnoœæ t³a
        set_all_sessions_volume(RESTORE_VOLUME, exclude_names=exclude)

    except Exception as e:
        print(f"❌ B³¹d odtwarzania: {e}")
    finally:
        pygame.mixer.quit()


# === AUTO-UPDATER ===

def _read_version_file():
    """Czyta zainstalowan¹ wersjê z version.txt (autorytatywne)."""
    try:
        with open(os.path.join(BASE_PATH, "version.txt"), "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return VERSION


def run_update_now():
    """
    Uruchamia update.py (--no-restart), który robi git pull albo pobiera ZIP —
    dzia³a tak samo na sklepach git i ZIP. Zwraca (changed, before, after).
    Pobieranie jest scentralizowane w update.py (jedno Ÿród³o prawdy).
    """
    before = _read_version_file()
    updater = os.path.join(BASE_PATH, "update.py")
    if not os.path.exists(updater):
        return (False, before, before)
    try:
        # Wymuœ UTF-8 w podprocesie, ¿eby emoji w update.py nie wywali³y siê na cp1250
        env = dict(os.environ)
        env["PYTHONUTF8"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        result = subprocess.run(
            [sys.executable, updater, "--no-restart"],
            cwd=BASE_PATH, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,  # 'capture_output'/'text' są dopiero w 3.7
            encoding="utf-8", errors="replace", timeout=180, env=env
        )
        if result.stdout:
            print("[Update] " + result.stdout.strip().replace("\n", "\n[Update] "))
    except Exception as e:
        print(f"[Update] B³¹d uruchomienia update.py: {e}")
        return (False, before, before)
    after = _read_version_file()
    return (after != before, before, after)


def auto_update_loop():
    """Pêtla t³a — co UPDATE_INTERVAL godzin pobiera i wgrywa zmiany, potem restart."""
    time.sleep(15)  # Poczekaj a¿ Flask wystartuje
    while True:
        try:
            changed, before, after = run_update_now()
            if changed:
                # Restart TYLKO po realnej zmianie wersji -> brak pêtli restartów
                print(f"[Auto-Update] Zaktualizowano {before} -> {after}, restartujê...")
                os.execl(sys.executable, sys.executable, *sys.argv)
            else:
                print(f"[Auto-Update] Aktualne ({after})")
        except Exception as e:
            print(f"[Auto-Update] B³¹d: {e}")

        time.sleep(UPDATE_INTERVAL * 3600)


# === ENDPOINTY API ===

@app.route('/play-sound', methods=['POST'])
def play_sound_route():
    """Endpoint do uploadu i odtwarzania pliku dŸwiêkowego."""
    # SprawdŸ czy wolno graæ
    trade_info = check_trade_day()
    if _manual_muted:
        return jsonify({
            "error": "System wyciszony rêcznie (panel /admin)",
            "trade_info": trade_info
        }), 423
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
    if _manual_muted:
        return jsonify({
            "error": "System wyciszony rêcznie (panel /admin)",
            "trade_info": trade_info
        }), 423
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
        "manual_mute": _manual_muted,
        "sunday_inverted": SUNDAY_INVERTED,
        "announcement_volume": ANNOUNCEMENT_VOLUME,
        "duck_volume": DUCK_VOLUME,
        "restore_volume": RESTORE_VOLUME,
        "trade_info": trade_info,
        "update_enabled": UPDATE_ENABLED,
        "stats": stats,
        "sounds_available": sorted(os.listdir(SOUND_DIRECTORY)) if os.path.exists(SOUND_DIRECTORY) else []
    })


def _clamp_pct(value, fallback):
    """Przycina wartoœæ do zakresu 0-100 (%)."""
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return fallback


@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """Odczytuje lub aktualizuje konfiguracjê (panel /admin).
    Zapisuje TYLKO zmienione pola do lokalnego config.json — nie zaœmieca go
    pe³nym mergem, wiêc locations/ pozostaje Ÿród³em prawdy dla reszty."""
    global SUNDAY_INVERTED, STORE_NAME, config, _last_trade_check
    global ANNOUNCEMENT_VOLUME, DUCK_VOLUME, RESTORE_VOLUME, _manual_muted

    if request.method == 'POST':
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400

        updates = {}

        if "sunday_inverted" in data:
            SUNDAY_INVERTED = bool(data["sunday_inverted"])
            updates["sunday_inverted"] = SUNDAY_INVERTED
            _last_trade_check = None  # zresetuj cache dnia

        if "store_name" in data:
            STORE_NAME = str(data["store_name"])
            updates["store_name"] = STORE_NAME

        if "update_enabled" in data:
            updates["update_enabled"] = bool(data["update_enabled"])

        if "update_url" in data:
            updates["update_url"] = str(data["update_url"])

        if "announcement_volume" in data:
            ANNOUNCEMENT_VOLUME = _clamp_pct(data["announcement_volume"], ANNOUNCEMENT_VOLUME)
            updates["announcement_volume"] = ANNOUNCEMENT_VOLUME

        if "duck_volume" in data:
            DUCK_VOLUME = _clamp_pct(data["duck_volume"], DUCK_VOLUME)
            updates["duck_volume"] = DUCK_VOLUME

        if "restore_volume" in data:
            RESTORE_VOLUME = _clamp_pct(data["restore_volume"], RESTORE_VOLUME)
            updates["restore_volume"] = RESTORE_VOLUME
            # Zastosuj OD RAZU — radio/tło (np. Lewiatan) skacze na nowy poziom natychmiast
            try:
                own = os.path.basename(sys.executable).lower()
                set_all_sessions_volume(RESTORE_VOLUME, exclude_names={own})
            except Exception as e:
                print(f"⚠️ Nie udało się zastosować głośności tła na żywo: {e}")

        if "manual_mute" in data:
            _manual_muted = bool(data["manual_mute"])
            updates["manual_mute"] = _manual_muted

        # Zapisz tylko zmienione pola do LOKALNEGO config.json
        try:
            local = _read_json(CONFIG_FILE)
            local.update(updates)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(local, f, indent=2, ensure_ascii=False)
            config = load_config()  # odœwie¿ scalon¹ konfiguracjê
        except Exception as e:
            return jsonify({"error": f"Nie mo¿na zapisaæ configu: {e}"}), 500

        return jsonify({"status": "ok", "saved": updates})

    # GET
    return jsonify({"config": config})


@app.route('/api/check-update', methods=['POST'])
def api_check_update():
    """Rêczne sprawdzenie + pobranie aktualizacji (z panelu /admin)."""
    if not UPDATE_ENABLED or not UPDATE_URL:
        return jsonify({"status": "disabled", "message": "Auto-update wy³¹czony lub brak URL"})

    changed, before, after = run_update_now()
    if changed:
        # Restart po krótkiej chwili, ¿eby zd¹¿yæ odes³aæ odpowiedŸ do panelu
        def _restart():
            time.sleep(2)
            os.execl(sys.executable, sys.executable, *sys.argv)
        threading.Thread(target=_restart, daemon=True).start()
        return jsonify({"status": "updated", "message": f"Zaktualizowano {before} → {after}. Restartujê…"})

    return jsonify({"status": "ok", "message": f"Ju¿ aktualne ({after})"})


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


@app.route('/api/test-sound', methods=['POST'])
def api_test_sound():
    """Test odtworzenia z panelu /admin — gra ZAWSZE (pomija wyciszenie i dzieñ
    wolny), z aktualnymi ustawieniami g³oœnoœci. Do sprawdzania suwaków."""
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")
    sound_dir = os.path.join(BASE_PATH, SOUND_DIRECTORY)

    if not filename:
        candidates = []
        if os.path.exists(sound_dir):
            candidates = [f for f in sorted(os.listdir(sound_dir))
                          if f.lower().endswith(('.mp3', '.wav')) and f.lower() != 'ping.mp3']
        if not candidates:
            return jsonify({"error": "Brak dŸwiêków do testu"}), 404
        filename = candidates[0]

    file_path = os.path.join(SOUND_DIRECTORY, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "Plik nie istnieje"}), 404

    def play_in_thread():
        try:
            play_sound_with_isolation(file_path, force=True)
        except Exception as e:
            print(f"Error during test playback: {e}")

    threading.Thread(target=play_in_thread).start()
    return jsonify({"status": "ok", "played_file": filename})


# === STRONY ===

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/tablet')
def index_tablet():
    return render_template('index-tablet.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


# === START ===

if __name__ == '__main__':
    try:
        own_name = os.path.basename(sys.executable).lower()
        exclude = {own_name}
        set_all_sessions_volume(RESTORE_VOLUME, exclude_names=exclude)
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
