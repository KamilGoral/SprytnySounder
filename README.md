# SprytnySounder 🎵

System komunikatów głosowych na salę sprzedaży dla sklepów spożywczych.

## Jak uruchomić

1. Zainstaluj Pythona 3.8+ i wymagane biblioteki:
   ```
   pip install -r requirements.txt
   ```
2. Uruchom:
   ```
   python app.py
   ```
   Lub przez `uruchom.bat`

3. Otwórz przeglądarkę na `http://<IP_SERWERA>:8989`

## Panel pracowniczy

- **index.html** — pełny panel z 12 przyciskami (dla komputerów/tabletów poziomych)
- **/tablet** — uproszczony panel (dla tabletów pionowych)

## Konfiguracja (`config.json`)

| Pole | Opis |
|------|------|
| `host` | IP serwera (np. 192.168.133.101) |
| `port` | Port HTTP (domyślnie 8989) |
| `sunday_inverted` | `true` jeśli sklep handluje w niedziele niehandlowe (Krótka 2a) |
| `update_enabled` | `true` = sprawdzaj aktualizacje automatycznie |
| `update_url` | URL repozytorium GitHub (np. https://github.com/user/repo) |
| `store_name` | Nazwa sklepu (wyświetlana w API status) |

## Dni wolne od handlu

System automatycznie wycisza się w:
- Święta państwowe (Wielkanoc, Boże Narodzenie, Nowy Rok, etc.)
- Niedziele niehandlowe (z możliwością odwrócenia flagą `sunday_inverted`)

## Dodawanie nowych komunikatów

1. Nagraj plik MP3 przez ElevenLabs (lub inne TTS)
2. Umieść w `static/sounds/`
3. Dodaj przycisk w `templates/index.html` i/lub `templates/index-tablet.html`

## Auto-updater

System raz dziennie sprawdza aktualizacje z repozytorium GitHub.
Można też wywołać ręcznie:
```
python update.py --status    # sprawdź wersję
python update.py             # sprawdź i aktualizuj
python update.py --force     # wymuś aktualizację
```

Aby aktywować auto-updater, ustaw `update_url` w config.json na URL Twojego repozytorium.

## Wersja

1.1.0
