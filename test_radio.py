# -*- coding: utf-8 -*-
"""Sprawdzian wykrywania radia (funkcje z app.py — ten sam plik jedzie na sklepy).
Uruchom: python test_radio.py   (nie wymaga Windows ani pycaw)

Powód (1.7.4): na Kilińskiego 21.09 log pokazał w jednej linii „sesje: chrome.exe 25%"
i „chrome.exe: NIE DZIAŁA" — tasklist nie widział procesu, który trzymał strumień audio.
Sesja audio jest mocniejszym dowodem i wygrywa, a rozjazd ma zostać w logu z cytatem
z tasklist, żeby dało się ustalić winnego bez wizyty w sklepie.
"""

import re
import subprocess
import sys
import types

SRC = open("app.py", encoding="utf-8").read()


def wytnij(nazwa):
    """Wytnij jedną funkcję z app.py — import całego pliku wymaga Windows (pycaw)."""
    m = re.search(r"^def " + nazwa + r"\(.*?(?=^def |\Z)", SRC, re.S | re.M)
    if not m:
        raise SystemExit("nie znalazłem funkcji {} w app.py".format(nazwa))
    return m.group(0)


class Wynik:
    def __init__(self, out="", err=""):
        self.stdout, self.stderr = out, err


NS = {"os": types.SimpleNamespace(name="nt"), "subprocess": subprocess,
      "RADIO_PROCESS": "chrome.exe"}
exec(compile("\n\n".join(wytnij(f) for f in ("sesja_radia", "proces_radia", "radio_running",
                                             "audio_summary")),
             "app.py", "exec"), NS)

sesja_radia = NS["sesja_radia"]
proces_radia = NS["proces_radia"]
radio_running = NS["radio_running"]
audio_summary = NS["audio_summary"]

class Podstawiony:
    """Udaje moduł subprocess: przechwytuje tylko `run`, resztę (PIPE, DEVNULL…)
    przepuszcza do prawdziwego modułu — inaczej atrapa kłamie przy pierwszej zmianie."""

    def __init__(self):
        self.out, self.err, self.blad = "", "", None
        self.wolania = []

    def __getattr__(self, nazwa):
        return getattr(subprocess, nazwa)

    def run(self, *a, **k):
        self.wolania.append(a[0] if a else k)
        if self.blad:
            raise self.blad
        return Wynik(self.out, self.err)


TASKLIST = Podstawiony()
NS["subprocess"] = TASKLIST


def podstaw_tasklist(out="", err="", wyjatek=None):
    """Podstawia odpowiedź tasklist; zeruje licznik wywołań."""
    TASKLIST.out, TASKLIST.err, TASKLIST.blad = out, err, wyjatek
    del TASKLIST.wolania[:]


CSV_JEST = '"chrome.exe","1234","Console","1","123 456 K"\r\n'
CSV_NIE_MA = "INFO: No tasks are running which match the specified criteria.\r\n"

BLEDY = []


def sprawdz(co, opis, oczekiwane=True):
    ok = (co == oczekiwane) if not callable(oczekiwane) else oczekiwane(co)
    print("{} {}".format("OK  " if ok else "BŁĄD", opis))
    if not ok:
        BLEDY.append("{} → {!r}".format(opis, co))


def main():
    # 1. Sesja audio: dokładna nazwa procesu, bez względu na wielkość liter.
    sprawdz(sesja_radia(["python.exe 66%", "chrome.exe 25%"]), "sesja chrome.exe wykryta")
    sprawdz(sesja_radia(["Chrome.EXE 25%"]), "wielkość liter nie ma znaczenia")
    sprawdz(sesja_radia(["python.exe 66%"]), "brak sesji chrome", False)
    sprawdz(sesja_radia(None), "pusta lista sesji", False)
    sprawdz(sesja_radia(["chrome.exe.bak 25%"]), "podobna nazwa to nie radio", False)

    # 2. tasklist: dopasowanie i surowa odpowiedź (ta jedzie do logu).
    podstaw_tasklist(CSV_JEST)
    zyje, surowe = proces_radia()
    sprawdz(zyje, "tasklist widzi chrome.exe")
    sprawdz("chrome.exe" in surowe, "surowa odpowiedź zachowana")
    podstaw_tasklist(CSV_NIE_MA)
    zyje, surowe = proces_radia()
    sprawdz(zyje, "tasklist nie widzi procesu", False)
    sprawdz("No tasks" in surowe, "cytat z tasklist przy braku procesu")
    podstaw_tasklist(wyjatek=OSError("tasklist nie startuje"))
    zyje, surowe = proces_radia()
    sprawdz(zyje, "błąd tasklist = nie wiem", None)
    sprawdz("tasklist" in surowe, "błąd tasklist trafia do logu")

    # 3. Sesja wygrywa z tasklist i nie woła tasklist bez potrzeby.
    podstaw_tasklist(CSV_NIE_MA)
    sprawdz(radio_running(["chrome.exe 25%"]), "sesja = radio działa, mimo tasklist", True)
    sprawdz(TASKLIST.wolania, "przy sesji tasklist nie był wołany", [])

    # 4. Bez sesji rozstrzyga tasklist (dwa różne lekarstwa).
    podstaw_tasklist(CSV_JEST)
    sprawdz(radio_running(["python.exe 66%"]), "proces jest, karta stoi", True)
    podstaw_tasklist(CSV_NIE_MA)
    sprawdz(radio_running(["python.exe 66%"]), "procesu nie ma", False)

    # 5. Linia do logu: stan trójwartościowy + jawna sprzeczność z cytatem.
    INFO = {"device": "Głośniki", "master": 100, "muted": False,
            "session_list": ["python.exe 66%", "chrome.exe 25%"], "sessions": 2}
    podstaw_tasklist(CSV_NIE_MA)
    linia = audio_summary(INFO)
    sprawdz("działa (sesja audio)" in linia, "linia mówi: działa (sesja audio)")
    sprawdz("SPRZECZNOŚĆ z tasklist" in linia, "sprzeczność oznaczona")
    sprawdz("No tasks" in linia, "cytat tasklist w linii logu")
    podstaw_tasklist(CSV_JEST)
    linia = audio_summary(INFO)
    sprawdz("SPRZECZNOŚĆ" in linia, "zgoda obu sygnałów = brak sprzeczności", False)
    bez_sesji = {"device": "Głośniki", "master": 100, "muted": False,
                 "session_list": ["python.exe 66%"], "sessions": 1}
    linia = audio_summary(bez_sesji)
    sprawdz("proces jest, brak sesji audio" in linia, "proces żyje, karta stoi")
    podstaw_tasklist(CSV_NIE_MA)
    linia = audio_summary(bez_sesji)
    sprawdz("NIE DZIAŁA" in linia, "brak procesu = NIE DZIAŁA")

    # 6. Poza Windows nic nie zgadujemy.
    NS["os"] = types.SimpleNamespace(name="posix")
    sprawdz(radio_running(["chrome.exe 25%"]), "poza Windows nie wiem", None)
    sprawdz(proces_radia(), "poza Windows bez tasklist", (None, ""))

    print()
    if BLEDY:
        print("PORAŻKA ({}):".format(len(BLEDY)))
        for b in BLEDY:
            print("  -", b)
        return 1
    print("Wszystko przeszło — wykrywanie radia działa jak opisane.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
