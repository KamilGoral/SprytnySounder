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
# Master urządzenia (nie sesji) — starsze pycaw na sklepach może tego nie mieć,
# wtedy diagnostyka po prostu poda mniej, zamiast wywalić aplikację.
try:
    from pycaw.pycaw import IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
except Exception:
    IAudioEndpointVolume = None
    CLSCTX_ALL = None
from flask_cors import CORS
import pygame
import pythoncom
import requests

# === W³asne modu³y ===
from poland_holidays import is_trade_day, get_trade_info
from czas import hm_to_minutes, in_quiet_hours, clock_info, clock_summary

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

def _resolve_location(local_cfg):
    # Nazwa lokalizacji: najpierw location.txt (per maszyna), a gdy go brak -
    # dopasowanie po IP maszyny z locations/machines.json (w repo, więc placówkę
    # można "podpiąć" zdalnie samym pushem, bez tworzenia plików na maszynie).
    location = _read_location_name()
    if location:
        return location
    machines = _read_json(os.path.join(LOCATIONS_DIR, "machines.json"))
    location = machines.get(str(local_cfg.get("host", "")).strip(), "")
    if location:
        # utrwal, żeby maszyna zachowała tożsamość nawet po zmianie machines.json
        try:
            with open(LOCATION_FILE, "w", encoding="utf-8") as f:
                f.write(location + "\n")
        except Exception:
            pass
    return location

def load_config():
    # 3. warstwa czytana najpierw, bo jej "host" służy do dopasowania lokalizacji
    local_cfg = _read_json(CONFIG_FILE)
    cfg = {}
    # 1. Wspólne domyślne z repo
    cfg.update(_read_json(DEFAULTS_FILE))
    # 2. Ustawienia per lokalizacja z repo
    location = _resolve_location(local_cfg)
    if location:
        cfg.update(_read_json(os.path.join(LOCATIONS_DIR, location + ".json")))
    # 3. Lokalne ustawienia maszyny (najwyższy priorytet). Stare sklepy mają tu pełny
    #    config.json, więc działają dokładnie jak dawniej (wsteczna zgodność).
    cfg.update(local_cfg)
    return cfg

config = load_config()

HOST = config.get("host", "0.0.0.0")
PORT = config.get("port", 8989)
SOUND_DIRECTORY = config.get("sound_folder", "static/sounds")
LOG_FILE = config.get("log_file", "log.txt")
STATS_FILE = config.get("stats_file", "statystyka.txt")
VERSION = config.get("version", "1.1.0")
SUNDAY_INVERTED = config.get("sunday_inverted", False)
# Most audio (tylko placówki z tym kluczem w locations/<nazwa>.json — np. Bielska).
# Wymusza ustawienie Windows "Nasłuchuj tego urządzenia" CABLE Output -> Głośniki,
# które po restarcie/zmianie urządzenia potrafi się zgubić i wtedy jest cisza na sali.
# Pusty klucz = funkcja bezczynna (wszystkie pozostałe sklepy jej nie odpalają).
AUDIO_BRIDGE = config.get("audio_bridge") or {}
UPDATE_ENABLED = config.get("update_enabled", True)
UPDATE_URL = config.get("update_url", "")
UPDATE_INTERVAL = config.get("update_check_interval_hours", 24)
STORE_NAME = config.get("store_name", "SprytnySounder")

# Bony kaucyjne — podgląd niezrealizowanych bonów ze zwrotomatu (serwis na Hetznerze).
# bony_url siedzi w config.defaults.json; bony_token to sekret per sklep, TYLKO w
# lokalnym config.json. Bez tokenu funkcja jest niewidoczna (przycisk się nie renderuje).
BONY_URL = str(config.get("bony_url", "")).rstrip("/")
BONY_TOKEN = config.get("bony_token", "")

# Głośność (sterowane z panelu /admin, zapisywane do lokalnego config.json)
ANNOUNCEMENT_VOLUME = int(config.get("announcement_volume", 100))  # głośność komunikatu (%)
DUCK_VOLUME = int(config.get("duck_volume", 5))                    # tło PODCZAS komunikatu (%)
RESTORE_VOLUME = int(config.get("restore_volume", 33))            # tło PO komunikacie (%)

# Cisza nocna — sklep milknie o QUIET_FROM i wraca o QUIET_TO (czas lokalny maszyny).
# Reguły dni handlowych obowiązują nadal: w niedzielę niehandlową cisza trwa całą dobę.
QUIET_FROM = str(config.get("quiet_from", "22:00"))
QUIET_TO = str(config.get("quiet_to", "05:30"))

# Katalog przycisków — JEDNO źródło prawdy (panel /admin + widok /). Kolejność = układ.
# Widoczność per placówka: HIDDEN_BUTTONS (lista plików) w lokalnym config.json,
# przełączana z /admin — sklep bez 3 kas / bez samoobsługi chowa u siebie zbędne.
BUTTONS = [
    {"file": "kasa-2.mp3",              "label": "Otwórz kasę 2",         "icon": "fa-cash-register"},
    {"file": "kasa-3.mp3",              "label": "Otwórz kasę 3",         "icon": "fa-cash-register"},
    {"file": "kasa-biuro.mp3",          "label": "Sprzedawca do biura",   "icon": "fa-door-open"},
    {"file": "help-sco.mp3",            "label": "Samoobsługowe - Pomoc", "icon": "fa-shopping-cart"},
    {"file": "korzystaniesco.mp3",      "label": "Samoobsługowe - Promocja", "icon": "fa-hand-pointer"},
    {"file": "help-gas.mp3",            "label": "Butla gazowa",          "icon": "fa-fire"},
    {"file": "new-delivery.mp3",        "label": "Dostawa",               "icon": "fa-box"},
    {"file": "donuts.mp3",              "label": "Cukiernica",            "icon": "fa-birthday-cake"},
    {"file": "call-office.mp3",         "label": "Kierownik zmiany",      "icon": "fa-user-tie"},
    {"file": "Dobregodnia.mp3",         "label": "Dobrego dnia",          "icon": "fa-smile"},
    {"file": "zabierz-koszyk.mp3",      "label": "Zabierz koszyk / wózek","icon": "fa-shopping-basket"},
    {"file": "thief.mp3",               "label": "Złodziej",              "icon": "fa-user-secret"},
    {"file": "meat-office.mp3",         "label": "Kierownik mięsny",      "icon": "fa-drumstick-bite"},
    {"file": "recyklomat-oproznij.mp3", "label": "Recyklomat — opróżnij", "icon": "fa-recycle"},
    {"file": "recyklomat-pomoc.mp3",    "label": "Recyklomat — pomoc",    "icon": "fa-circle-question"},
]
HIDDEN_BUTTONS = list(config.get("hidden_buttons", []))  # pliki ukryte na TEJ placówce

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
_play_lock = threading.Lock()  # jeden komunikat naraz (mixer nie jest thread-safe)


def log_line(text):
    """Dopisuje liniê do log.txt (start, blokady, b³êdy) — bez tego jedynym œladem
    by³ ekran konsoli, którego na sklepie nikt nie widzi."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"{timestamp} - {text}\n")
    except Exception:
        pass


def log_event(filename):
    """Zapisuje zdarzenie do loga."""
    log_line(f"Odtworzono plik: {filename}")


QUIET_FROM_MIN = hm_to_minutes(QUIET_FROM, 22 * 60)
QUIET_TO_MIN = hm_to_minutes(QUIET_TO, 5 * 60 + 30)


def audio_snapshot(with_device_name=True):
    """Stan WYJŒCIA audio Windows: domyœlne urz¹dzenie, master, wyciszenie, liczba sesji.

    Aplikacja steruje tylko g³oœnoœci¹ sesji — zjechany master urz¹dzenia albo
    podmiana domyœlnego wyjœcia (np. znika CABLE i wchodzi Realtek) daj¹ ciszê na
    sali, której z kodu nie widaæ. Bez tego wpisu nie da siê zdalnie odró¿niæ
    'aplikacja nie zagra³a' od 'zagra³a w z³e urz¹dzenie'.
    Diagnostyka nigdy nie mo¿e wywaliæ odtwarzania — st¹d wszystko w try."""
    info = {"device": None, "master": None, "muted": None, "sessions": None}
    try:
        pythoncom.CoInitialize()
        speakers = AudioUtilities.GetSpeakers()

        if with_device_name:
            try:
                device_id = speakers.GetId()
                for dev in AudioUtilities.GetAllDevices():
                    if getattr(dev, "id", None) == device_id:
                        info["device"] = dev.FriendlyName
                        break
            except Exception:
                pass

        if IAudioEndpointVolume is not None:
            endpoint = speakers.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            master = endpoint.QueryInterface(IAudioEndpointVolume)
            info["master"] = int(round(master.GetMasterVolumeLevelScalar() * 100))
            info["muted"] = bool(master.GetMute())

        # Nazwy i głośności sesji — bez nich nie da się zdalnie sprawdzić, czy radio
        # naprawdę zostało ściszone (aplikacja rusza sesje, nie master urządzenia).
        names = []
        for s in AudioUtilities.GetAllSessions():
            if not s.Process:
                continue
            try:
                names.append("{} {}%".format(
                    s.Process.name(),
                    int(round(s.SimpleAudioVolume.GetMasterVolume() * 100))))
            except Exception:
                continue
        info["sessions"] = len(names)
        info["session_list"] = names
    except Exception as e:
        info["error"] = str(e)
    return info


def audio_summary(info=None):
    """Jedno zdanie do log.txt — po nim widaæ, czy w nocy zmieni³o siê wyjœcie audio."""
    i = audio_snapshot() if info is None else info
    if i.get("error"):
        return f"audio: nie uda³o siê odczytaæ ({i['error']})"
    parts = []
    if i.get("device"):
        parts.append(f"wyjœcie: {i['device']}")
    if i.get("master") is not None:
        parts.append(f"master {i['master']}%")
        parts.append("URZ¥DZENIE WYCISZONE" if i["muted"] else "niewyciszone")
    if i.get("session_list"):
        parts.append("sesje: " + ", ".join(i["session_list"]))
    elif i.get("sessions") is not None:
        parts.append(f"sesji: {i['sessions']}")
    return ", ".join(parts) if parts else "audio: brak danych"


def count_log_starts(hours):
    """Ile razy aplikacja startowa³a w ostatnich N godzinach (z log.txt).
    Ka¿dy w³¹cz/wy³¹cz komputera przez obs³ugê = jeden START, wiêc to nasz licznik
    zg³oszeñ 'znowu nie gra³o'."""
    if not os.path.exists(LOG_FILE):
        return 0
    limit = datetime.now() - timedelta(hours=hours)
    count = 0
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f.readlines()[-5000:]:
                if " - START " not in line:
                    continue
                try:
                    stamp = datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if stamp >= limit:
                    count += 1
    except Exception:
        return 0
    return count


def heartbeat_loop():
    """Co godzinê wpis do log.txt. Dziêki temu widaæ, czy nad ranem aplikacja ¿y³a
    (wtedy cisza jest po stronie Windows/audio), czy ju¿ jej nie by³o (wtedy po
    stronie aplikacji). £apie te¿ uœpienie maszyny i zmianê czasu — d³ugoœæ drzemki
    inna ni¿ godzina oznacza, ¿e zegar albo komputer zrobi³ coœ w nocy."""
    step = 3600
    last = time.time()
    while True:
        time.sleep(step)
        now = time.time()
        drift_min = int(round((now - last - step) / 60.0))
        last = now
        if abs(drift_min) >= 5:
            log_line(f"Przeskok zegara albo uœpienie maszyny: {drift_min:+d} min "
                     f"({clock_summary()})")
        log_line(f"¯yje — {mute_reason() or 'gra'} — {audio_summary()}")


def background_mute_loop():
    """Cisza na sali to nie tylko brak komunikatów — gdy sklep jest zamknięty
    (niedziela niehandlowa, święto, cisza nocna, wyciszenie ręczne), radio też ma
    milczeć. Do 1.5.5 blokada dotyczyła WYŁĄCZNIE komunikatów, więc w niedzielę
    z głośników leciało tło ustawione ostatnim komunikatem w sobotę.

    Wyciszenie wymuszamy co tick (a nie raz, na zmianie stanu), bo komunikat
    zaczęty tuż przed 22:00 kończy się `set_all_sessions_volume(RESTORE_VOLUME)`
    już w ciszy nocnej i podniósłby radio na całą noc. Przywracamy raz — żeby
    obsługa mogła w ciągu dnia podgłośnić radio i nie walczyć z aplikacją."""
    own = {os.path.basename(sys.executable).lower()}
    was_muted = False  # przy starcie nie ruszamy głośności, dopóki nie wejdziemy w ciszę
    while True:
        muted = mute_reason() is not None
        try:
            if muted:
                set_all_sessions_volume(0, exclude_names=own)
            elif was_muted:
                set_all_sessions_volume(RESTORE_VOLUME, exclude_names=own)
            if muted != was_muted:
                log_line("Tło na sali: {} ({})".format(
                    "wyciszone" if muted else f"przywrócone {RESTORE_VOLUME}%",
                    mute_reason() or "sklep otwarty"))
            was_muted = muted
        except Exception as e:
            log_line(f"B£¥D wyciszania tła: {e}")  # bez zmiany was_muted = spróbuje znowu
        time.sleep(30)


def mute_reason(now=None):
    """JEDYNE miejsce decyduj¹ce, czy wolno graæ. Zwraca powód blokady albo None.
    Liczone na ¿¹danie — nie ma w¹tku ani flagi, która mog³aby zostaæ zawieszona
    po pó³nocy w z³ym stanie."""
    if _manual_muted:
        return "wyciszenie rêczne (panel /admin)"
    now = now or datetime.now()
    if in_quiet_hours(now.hour * 60 + now.minute, QUIET_FROM_MIN, QUIET_TO_MIN):
        return f"cisza nocna ({QUIET_FROM}-{QUIET_TO})"
    trade_info = check_trade_day()
    if not trade_info["is_trade_day"]:
        return trade_info["reason"]
    return None


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
        reason = mute_reason()
        if reason:
            print(f"⛔ Blokada: {reason} — dŸwiêk nie zostanie odtworzony")
            log_line(f"Zablokowano ({reason}): {os.path.basename(sound_path)}")
            return

    own_name = os.path.basename(sys.executable).lower()
    exclude = {own_name}

    # Jeden komunikat naraz — równoleg³e w¹tki potrafi³y sobie nawzajem
    # zamkn¹æ mixer (pygame.error) w trakcie grania
    with _play_lock:
        try:
            pythoncom.CoInitialize()

            # Wycisz resztê systemu na czas komunikatu
            set_all_sessions_volume(DUCK_VOLUME, exclude_names=exclude)

            # Rozgrzewka
            warmup_path = os.path.join(SOUND_DIRECTORY, "ping.mp3")
            if os.path.exists(warmup_path):
                play_single_sound(warmup_path)
                time.sleep(0.1)

            # W³aœciwy komunikat. Mierzymy czas: gdy urz¹dzenie jest martwe, pygame
            # koñczy "odtwarzanie" w u³amku sekundy — w logu widaæ to od razu.
            started = time.time()
            play_single_sound(sound_path)
            played = time.time() - started
            log_line(f"Zagrano {os.path.basename(sound_path)} w {played:.1f} s — "
                     f"{audio_summary(audio_snapshot(with_device_name=False))}")

        except Exception as e:
            print(f"❌ B³¹d odtwarzania: {e}")
            log_line(f"B£¥D odtwarzania {os.path.basename(sound_path)}: {e} — "
                     f"{audio_summary()}")
        finally:
            # Przywróæ g³oœnoœæ t³a ZAWSZE — inaczej b³¹d odtwarzania
            # zostawia³ radio œciszone do DUCK_VOLUME a¿ do restartu komputera
            try:
                set_all_sessions_volume(RESTORE_VOLUME, exclude_names=exclude)
            except Exception as e:
                print(f"❌ B³¹d przywracania g³oœnoœci: {e}")
            pygame.mixer.quit()


# === MOST AUDIO (Nasłuchuj tego urządzenia) ===

def ensure_audio_bridge():
    """Wymusza most CABLE Output -> Głośniki przez SoundVolumeView (NirSoft).
    Działa TYLKO gdy w configu placówki jest klucz `audio_bridge` (np. Bielska).
    Idempotentne — bezpieczne do wołania w kółko. Nigdy nie rzuca wyjątkiem."""
    if not AUDIO_BRIDGE or os.name != "nt":
        return
    listen = AUDIO_BRIDGE.get("listen_device")
    playback = AUDIO_BRIDGE.get("playback_device")
    if not listen:
        return
    exe = os.path.join(BASE_PATH, "SoundVolumeView.exe")
    if not os.path.exists(exe):
        print(f"⚠️ Most audio: brak {exe} — pomijam")
        return

    def _run(args):
        # 3.6-safe: bez capture_output=/text= (patrz historia zgodności 3.6 vs 3.7+)
        try:
            subprocess.run([exe] + args, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, universal_newlines=True, timeout=15)
        except Exception as e:
            print(f"⚠️ Most audio: {args[0]} nie powiódł się: {e}")

    if playback:
        _run(["/SetPlaybackThroughDevice", listen, playback])
    _run(["/SetListenToThisDevice", listen, "1"])


def audio_bridge_loop():
    """Wątek tła — przywraca most co interval (domyślnie 10 min)."""
    interval = int(AUDIO_BRIDGE.get("recheck_minutes", 10)) * 60
    while True:
        time.sleep(max(60, interval))
        ensure_audio_bridge()


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


UPDATE_HOURS = (8, 10, 20, 22)  # o tych godzinach sklepy sprawdzaj¹ nowe wersje


def _seconds_until_next_update_hour():
    """Ile sekund do najbli¿szej zaplanowanej godziny sprawdzenia (UPDATE_HOURS)."""
    now = datetime.now()
    candidates = []
    for day_offset in (0, 1):  # dziœ i jutro -> zawsze znajdzie kolejny slot
        base = now + timedelta(days=day_offset)
        for h in UPDATE_HOURS:
            t = base.replace(hour=h, minute=0, second=0, microsecond=0)
            if t > now:
                candidates.append(t)
    return (min(candidates) - now).total_seconds()


def auto_update_loop():
    """Pêtla t³a — o godzinach UPDATE_HOURS pobiera i wgrywa zmiany, potem restart."""
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

        time.sleep(_seconds_until_next_update_hour())


# === ENDPOINTY API ===

@app.route('/play-sound', methods=['POST'])
def play_sound_route():
    """Endpoint do uploadu i odtwarzania pliku dŸwiêkowego."""
    # SprawdŸ czy wolno graæ
    trade_info = check_trade_day()
    reason = mute_reason()
    if reason:
        return jsonify({
            "error": f"System wyciszony: {reason}",
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
    reason = mute_reason()
    if reason:
        return jsonify({
            "error": f"System wyciszony: {reason}",
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
        "mute_reason": mute_reason(),  # None = w tej chwili wolno graæ
        "quiet_from": QUIET_FROM,
        "quiet_to": QUIET_TO,
        "clock": clock_info(),          # z³a strefa = cisza o z³ej godzinie
        "audio": audio_snapshot(),      # domyœlne wyjœcie + master (aplikacja rusza tylko sesje)
        "restarts_24h": count_log_starts(24),
        "restarts_7d": count_log_starts(24 * 7),
        "sunday_inverted": SUNDAY_INVERTED,
        "announcement_volume": ANNOUNCEMENT_VOLUME,
        "duck_volume": DUCK_VOLUME,
        "restore_volume": RESTORE_VOLUME,
        "trade_info": trade_info,
        "update_enabled": UPDATE_ENABLED,
        "hidden_buttons": HIDDEN_BUTTONS,
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
    global ANNOUNCEMENT_VOLUME, DUCK_VOLUME, RESTORE_VOLUME, _manual_muted, HIDDEN_BUTTONS
    global BONY_TOKEN

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

        if "bony_token" in data:
            # Sekret per sklep — trafia do lokalnego config.json, działa bez restartu
            BONY_TOKEN = str(data["bony_token"]).strip()
            updates["bony_token"] = BONY_TOKEN

        if "hidden_buttons" in data:
            valid = {b["file"] for b in BUTTONS}
            HIDDEN_BUTTONS = [f for f in data["hidden_buttons"] if f in valid]
            updates["hidden_buttons"] = HIDDEN_BUTTONS

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


@app.route('/api/bony', methods=['GET'])
def bony_proxy():
    """Proxy do serwisu bonów — token zostaje na serwerze sklepu, nie w przeglądarce."""
    if not (BONY_URL and BONY_TOKEN):
        return jsonify({"error": "Bony nieskonfigurowane"}), 404
    try:
        r = requests.get(f"{BONY_URL}/api/bony",
                         headers={"X-Token": BONY_TOKEN}, timeout=5)
        return r.text, r.status_code, {"Content-Type": "application/json"}
    except requests.RequestException:
        return jsonify({"error": "Brak połączenia z serwisem bonów"}), 502


# === STRONY ===

@app.route('/')
def index():
    visible = [b for b in BUTTONS if b["file"] not in HIDDEN_BUTTONS]
    return render_template('index.html', buttons=visible,
                           bony_enabled=bool(BONY_URL and BONY_TOKEN))


@app.route('/tablet')
def index_tablet():
    return render_template('index-tablet.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html', buttons=BUTTONS, hidden=HIDDEN_BUTTONS)


# === START ===

if __name__ == '__main__':
    try:
        own_name = os.path.basename(sys.executable).lower()
        exclude = {own_name}
        set_all_sessions_volume(RESTORE_VOLUME, exclude_names=exclude)
    except Exception as e:
        print(f"❌ B³¹d przy ustawianiu g³oœnoœci przy starcie: {e}")

    # Most audio przy starcie (najczęstsza przyczyna ciszy = zgubione "Nasłuchuj"
    # po restarcie komputera). Bezczynne na sklepach bez klucza audio_bridge.
    ensure_audio_bridge()
    if AUDIO_BRIDGE:
        threading.Thread(target=audio_bridge_loop, daemon=True).start()
        print("🔊 Most audio aktywny (Nasłuchuj tego urządzenia pilnowany)")

    # SprawdŸ dzieñ handlowy
    check_trade_day()
    # Œlad w log.txt: po czym poznaæ, ¿e sklep restartowa³ maszynê i o której
    starts_24h = count_log_starts(24)  # liczone PRZED dopisaniem naszego STARTU
    log_line(f"START {STORE_NAME} v{VERSION} — cisza nocna {QUIET_FROM}-{QUIET_TO}, "
             f"{clock_summary()}, stan: {mute_reason() or 'gra'}, {audio_summary()}")
    if starts_24h >= 1:
        log_line(f"MONIT: to ju¿ {starts_24h + 1}. uruchomienie w ci¹gu doby — "
                 f"obs³uga znowu restartowa³a komputer, problem z cisz¹ trwa")
    threading.Thread(target=heartbeat_loop, daemon=True).start()
    threading.Thread(target=background_mute_loop, daemon=True).start()

    # Start auto-updater w tle
    if UPDATE_ENABLED and UPDATE_URL:
        updater = threading.Thread(target=auto_update_loop, daemon=True)
        updater.start()
        print(f"🔄 Auto-updater w³¹czony (o godzinach: {', '.join(f'{h}:00' for h in UPDATE_HOURS)})")

    print(f"📢 SprytnySounder v{VERSION} wystartowa³")
    print(f"   Host: {HOST}:{PORT}")
    print(f"   Odwrócone niedziele: {SUNDAY_INVERTED}")
    print(f"   Wyciszenie: {'TAK' if _system_muted else 'NIE'}")

    # debug=False: reloader Werkzeuga potrafi³ zrestartowaæ proces w œrodku
    # komunikatu (gdy auto-update podmieni pliki) = radio zostaje œciszone
    # threaded=True: odtwarzanie i tak serializuje _play_lock, a przy jednym
    # watku kazde nacisniecie przycisku (join do 15 s) wieszalo caly serwer
    app.run(host=HOST, port=PORT, debug=False, threaded=True)
