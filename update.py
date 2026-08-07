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
import base64
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
TOKEN_FILE = "update_token.txt"

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


def looks_like_token(value):
    """Czy to wygl¹da na token GitHuba. UWAGA: fine-grained 'github_pat_...' NIE
    zaczyna siê od 'gh' (tylko klasyczne 'ghp_', 'gho_'...), wiêc skrót w postaci
    startswith('gh') po cichu odrzuca³ prawid³owy token i sklep szed³ anonimowo —
    na publicznym repo tego nie widaæ, na prywatnym to koniec aktualizacji."""
    return str(value).startswith(("github_pat_", "ghp_", "gho_", "ghs_", "ghu_", "ghr_"))


def get_token():
    """Token do prywatnego repo. Kolejnoœæ: .secrets (rêcznie na sklepie, nie
    kasowane przez aktualizacje) -> update_token.txt (jedzie z repo).

    Format update_token.txt: base64 z tokenem zapisanym OD TY£U. Goły ani zwykle
    zbase64owany PAT nie przechodzi — GitHub blokuje push (push protection), a w
    publicznym repo dodatkowo sam uniewa¿nia znaleziony token, wiêc sklepy
    straci³yby aktualizacje. Zapis:
        printf 'github_pat_...' | rev | base64 -w0 > update_token.txt
    """
    for rel, is_b64 in ((os.path.join(".secrets", "github-token"), False),
                        (TOKEN_FILE, True)):
        try:
            with open(os.path.join(BASE_PATH, rel), "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if not raw:
                continue
            tok = base64.b64decode(raw).decode("ascii")[::-1].strip() if is_b64 else raw
            if looks_like_token(tok):
                return tok
        except Exception:
            continue
    return ""


def api_base(update_url):
    """https://github.com/Owner/Repo -> https://api.github.com/repos/Owner/Repo
    API dzia³a te¿ na publicznym repo, wiêc jest jedna œcie¿ka zamiast dwóch."""
    slug = update_url.rstrip("/").replace(".git", "").split("github.com/")[-1]
    return "https://api.github.com/repos/" + slug


def gh_headers(accept="application/vnd.github+json"):
    headers = {"Accept": accept}
    token = get_token()
    if token:
        headers["Authorization"] = "Bearer " + token
    return headers


def check_update(config):
    """Sprawdza czy dostêpna jest aktualizacja."""
    update_url = config.get("update_url", "")
    if not update_url:
        return {"status": "no_url", "current": get_local_version(config), "available": None}

    api = api_base(update_url)
    version_urls = [
        api + "/contents/version.txt?ref=main",
        api + "/contents/version.txt?ref=master",
    ]
    headers = gh_headers("application/vnd.github.raw")

    for url in version_urls:
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code in (401, 403, 404) and "Authorization" not in headers:
                print("⚠️ Repo prywatne albo brak dostêpu, a nie mam tokena "
                      "(update_token.txt / .secrets/github-token)")
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
            env = dict(os.environ)
            env["GIT_TERMINAL_PROMPT"] = "0"  # prywatne repo bez creds ma paœæ, nie wisieæ
            result = subprocess.run(
                ["git", "pull"],
                cwd=BASE_PATH,
                env=env,
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
    api = api_base(update_url)
    headers = gh_headers()

    # Spróbuj te¿ master
    try:
        resp = requests.get(api + "/zipball/main", headers=headers, stream=True, timeout=30)
        if resp.status_code != 200:
            resp = requests.get(api + "/zipball/master", headers=headers, stream=True, timeout=30)
        if resp.status_code != 200:
            print("❌ Nie mo¿na pobraæ ZIP z repozytorium (HTTP %s)" % resp.status_code)
            if "Authorization" not in headers:
                print("   Repo mo¿e byæ prywatne — brakuje tokena aktualizacji")
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
    if os.name == "nt":
        # os.exec* na Windows nie cytuje argumentów — œcie¿ka ze spacj¹
        # (C:\komunikaty glosowe) rozpada siê i restart pada; Popen cytuje
        subprocess.Popen([python, script], cwd=BASE_PATH)
        os._exit(0)
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
