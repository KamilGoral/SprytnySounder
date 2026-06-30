# locations/ — ustawienia per placówka

Każdy sklep ma tu **jeden plik** `<nazwa>.json`. To jest źródło prawdy o placówce —
trzymane w repo, więc wszystkie sklepy wiedzą o wszystkich ustawieniach, a auto-update
nigdy ich nie kasuje.

## Jak dodać nowy sklep

1. Skopiuj `_przyklad.json` na `<krotka-nazwa>.json` (małe litery, bez spacji),
   np. `bielska.json`, `sulkowice.json`, `krotka2a.json`.
2. Ustaw pola:
   - `store_name` — nazwa wyświetlana w panelu (może mieć polskie znaki i spacje).
   - `sunday_inverted` — `true` tylko dla sklepów z odwróconymi niedzielami (np. Krótka 2a).
   - (opcjonalnie) `host` — stały adres IP, jeśli nie chcesz auto-wykrywania.
3. Wypchnij do repo (`git push`).
4. Na maszynie sklepu w pliku `location.txt` wpisz tę krótką nazwę (np. `bielska`).

`location.txt` jest lokalny (gitignored) i nigdy nie jest nadpisywany przez aktualizacje —
to jedyna rzecz unikalna per maszyna. Reszta (kod, dźwięki, wspólne ustawienia) jest wspólna.

## Warstwy konfiguracji (każda nadpisuje poprzednią)

1. `config.defaults.json` — wspólne dla wszystkich (port, foldery, update_url...).
2. `locations/<location.txt>.json` — tożsamość tej placówki.
3. `config.json` — lokalne maszynowe (auto-wykryty `host`, nadpisania z panelu).
