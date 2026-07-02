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
4. Na maszynie sklepu w pliku `location.txt` wpisz tę krótką nazwę (np. `bielska`) —
   **albo** dodaj wpis w `machines.json` (patrz niżej) i nic nie rób na maszynie.

`location.txt` jest lokalny (gitignored) i nigdy nie jest nadpisywany przez aktualizacje —
to jedyna rzecz unikalna per maszyna. Reszta (kod, dźwięki, wspólne ustawienia) jest wspólna.

## machines.json — podpięcie maszyny zdalnie, bez location.txt

Gdy maszyna NIE ma `location.txt`, app przy starcie szuka swojego IP (pole `host`
z lokalnego `config.json`) w `locations/machines.json`:

```json
{
    "192.168.133.101": "bielska"
}
```

Po dopasowaniu app sam zapisuje `location.txt` na maszynie (tożsamość zostaje na stałe).
Dzięki temu nową placówkę podpina się samym pushem do repo — maszyna zaciągnie to
przy najbliższej aktualizacji/restarcie.

UWAGA: IP jest unikalne tylko w obrębie sklepu (każdy sklep to osobna sieć LAN) —
jeśli dwie placówki mają ten sam adres, wpis dopasuje każdą maszynę bez `location.txt`
o tym IP. Stare sklepy z pełnym `config.json` są bezpieczne: ich lokalny config i tak
nadpisuje wszystko.

## Warstwy konfiguracji (każda nadpisuje poprzednią)

1. `config.defaults.json` — wspólne dla wszystkich (port, foldery, update_url...).
2. `locations/<location.txt>.json` — tożsamość tej placówki.
3. `config.json` — lokalne maszynowe (auto-wykryty `host`, nadpisania z panelu).
