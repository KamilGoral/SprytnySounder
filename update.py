#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SprytnySounder — Auto-Update Script
Sprawdza aktualizacje z repozytorium GitHub i aktualizuje pliki.

Sposoby u¿ycia:
  python update.py          - sprawdŸ i zaktualizuj
  python update.py --force  - wymuœ aktualizacjê (nawet ta sama wersja)
  python update.py --status - tylko sprawdŸ wersjê

Dzia³anie:
  1. Sprawdza lokaln¹ wersjê z config.json
  2. Pobiera zdaln¹ wersjê z GitHub (raw)
  3. Jeśli nowsza -> git pull lub pobiera ZIP i zastêpuje pliki
  4. Restartuje aplikacjê Flask
"""

import os
import sys
import json
import subprocess
import tempfile
import shutil
import zipfile
import io
import time
import requests  # pip install requests

# Konsola na sklepach bywa cp1250 (Python 3.6) — emoji w printach (✓ 📦 ⚠️ …)
# nie mogą wywalać skryptu UnicodeEncodeError. Działa na 3.6 i 3.7+.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Python 3.7+
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except AttributeError:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
except Exception:
    pass

CONFIG_FILE = "config.json"
DEFAULTS_FILE = "config.defaults.json"
LOCATION_FILE = "location.txt"
LOCATIONS_DIR = "locations"
VERSION_FILE = "version.txt"

if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.abspath(".")


def _read_json(rel_path):
    path = os.path.join(BASE_PATH, rel_path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config():
    # Warstwy jak w app.py: defaults (repo) -> locations/<location.txt> (repo) -> config.json (lokalne)
    cfg = {}
    cfg.update(_read_json(DEFAULTS_FILE))
    try:
        loc_path = os.path.join(BASE_PATH, LOCATION_FILE)
        if os.path.exists(loc_path):
            with open(loc_path, "r", encoding="utf-8") as f:
                loc = f.read().strip()
            if loc:
                cfg.update(_read_json(os.path.join(LOCATIONS_DIR, loc + ".json")))
    except Exception:
        pass
    cfg.update(_read_json(CONFIG_FILE))
    return cfg


def get_local_version(config):
    # version.txt jest autorytatywne (aktualizacja je nadpisuje); config jako fallback
    try:
        with open(os.path.join(BASE_PATH, VERSION_FILE), "r", encoding="utf-8") as f:
            v = f.read().strip()
            if v:
                return v
    except Exception:
        pass
    return config.get("version", "0.0.0")


def check_update(config):
    """Sprawdza czy dostêpna jest aktualizacja."""
    update_url = config.get("update_url", "")
    if not update_url:
        return {"status": "no_url", "current": get_local_version(config), "available": None}

    # Próbuj ró¿ne lokacje pliku wersji
    version_urls = [
        update_url.rstrip("/") + "/raw/main/version.txt",
        update_url.rstrip("/") + "/raw/master/version.txt",
    ]

    for url in version_urls:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                remote_version = resp.text.strip()
                return {
                    "status": "found",
                    "current": get_local_version(config),
                    "available": remote_version,
                    "url": url
                }
        except Exception:
            continue

    return {"status": "not_found", "current": get_local_version(config), "available": None}


def download_and_update(config, force=False):
    """Pobiera i aktualizuje pliki z repozytorium."""
    update_url = config.get("update_url", "")
    if not update_url:
        print("❌ Brak URL aktualizacji w config.json")
        return False

    local_version = get_local_version(config)
    check = check_update(config)
    remote_version = check.get("available", "")

    if not force and remote_version and remote_version == local_version:
        print(f"✓ Ju¿ aktualne: {local_version}")
        return True

    if remote_version:
        print(f"📦 Aktualizacja: {local_version} → {remote_version}")
    else:
        print("📦 Pobieranie najnowszej wersji...")

    # Próbuj przez git pull
    git_dir = os.path.join(BASE_PATH, ".git")
    if os.path.exists(git_dir):
        try:
            print("🔄 Próbujê git pull...")
            result = subprocess.run(
                ["git", "pull"],
                cwd=BASE_PATH,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,  # 'text=True' istnieje dopiero w 3.7
                timeout=30
            )
            if result.returncode == 0:
                print(f"✅ Git pull: {result.stdout.strip()}")
                # Wersja jest w version.txt (zaktualizowana przez pull) - nic nie zapisujemy
                return True
            else:
                print(f"⚠️ Git pull failed: {result.stderr}")
        except Exception as e:
            print(f"⚠️ Git error: {e}")

    # Fallback: pobierz ZIP z GitHub
    print("📥 Pobieram ZIP z repozytorium...")
    zip_url = update_url.rstrip("/") + "/archive/refs/heads/main.zip"
    
    # Spróbuj te¿ master
    try:
        resp = requests.get(zip_url, stream=True, timeout=30)
        if resp.status_code != 200:
            zip_url = update_url.rstrip("/") + "/archive/refs/heads/master.zip"
            resp = requests.get(zip_url, stream=True, timeout=30)
        if resp.status_code != 200:
            print("❌ Nie mo¿na pobraæ ZIP z repozytorium")
            return False
    except Exception as e:
        print(f"❌ B³¹d pobierania ZIP: {e}")
        return False

    # Wypakuj do tymczasowego katalogu
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            z.extractall(tmpdir)
            
            # ZnajdŸ g³ówny katalog w ZIP (ma nazwê repo-nazwa)
            extracted_dirs = [d for d in os.listdir(tmpdir) if os.path.isdir(os.path.join(tmpdir, d))]
            if not extracted_dirs:
                print("❌ ZIP nie zawiera oczekiwanych plików")
                return False
            
            source_dir = os.path.join(tmpdir, extracted_dirs[0])
            
            # Kopiuj pliki, ALE nigdy nie nadpisuj lokalnych ustawień sklepu
            # (config.json, location.txt) ani lokalnych danych (logi, statystyki, backup).
            skip_dirs = {
                "venv", "venv_tts", "build", "dist", ".git", "__pycache__", ".idea",
                ".secrets", "backup",
                "config.json", "location.txt",
                "log.txt", "statystyka.txt", "temp_sound_file.mp3",
            }
            for item in os.listdir(source_dir):
                if item in skip_dirs:
                    continue
                src = os.path.join(source_dir, item)
                dst = os.path.join(BASE_PATH, item)
                
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                else:
                    shutil.copy2(src, dst)
            
            print("✅ Pliki zaktualizowane pomyœlnie")
            # Wersja jest w version.txt (skopiowanym z repo) - nic nie zapisujemy
            return True

    except Exception as e:
        print(f"❌ B³¹d podczas wypakowywania: {e}")
        return False


def restart_app():
    """Restartuje aplikacjê Flask."""
    print("🔄 Restartujê aplikacjê...")
    time.sleep(1)
    python = sys.executable
    script = os.path.join(BASE_PATH, "app.py")
    os.execl(python, python, script)


def main():
    config = load_config()
    if not config:
        sys.exit(1)

    args = sys.argv[1:]

    if "--status" in args:
        check = check_update(config)
        print(f"Lokalna wersja: {check['current']}")
        print(f"Dostêpna wersja: {check['available'] or 'nieznana'}")
        print(f"Status: {check['status']}")
        return

    if "--force" in args:
        success = download_and_update(config, force=True)
    else:
        success = download_and_update(config)

    if success and "--no-restart" not in args:
        restart_app()


if __name__ == "__main__":
    main()
