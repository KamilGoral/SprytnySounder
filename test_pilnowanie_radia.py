# -*- coding: utf-8 -*-
"""Sprawdzian pilnowania Chrome z radiem (1.7.5). Uruchom: python test_pilnowanie_radia.py

Powód: na Kilińskiego chrome.exe znika co wieczór między 22:00 a 22:55 przy
działającym komputerze, a rano radio wraca dopiero po ręcznym restarcie.
Aplikacja ma zapisać, kiedy i jak zniknął, i od 04:00 podnieść go sama."""

import re
import sys
from datetime import datetime, timedelta

SRC = open("app.py", encoding="utf-8").read()
m = re.search(r"^def radio_watch_tick\(.*?(?=^def |\Z)", SRC, re.S | re.M)
LOG, URUCHOMIENIA = [], []
IRON = '"C:\\Pact24\\Iron\\chrome.exe" --app=http://player.pact24'
POLECENIE = [IRON]
NS = {"datetime": datetime, "timedelta": timedelta,
      "log_line": LOG.append, "idle_seconds": lambda: 30,
      "tytuly_okien_radia": lambda: ["Radio Lewiatan - Google Chrome"],
      "uruchom_radio": lambda p="": URUCHOMIENIA.append(p),
      "polecenie_radia": lambda: POLECENIE[0],
      "hm_to_minutes": lambda hm, d: int(hm[:2]) * 60 + int(hm[3:]),
      "QUIET_FROM_MIN": 22 * 60, "RADIO_PROCESS": "chrome.exe", "RADIO_AUTOSTART": True,
      "RADIO_AUTOSTART_FROM": "04:00", "RADIO_URL": "",
      "RADIO_PROB_DZIENNIE": 4, "RADIO_ODSTEP_S": 900}
exec(compile(m.group(0), "app.py", "exec"), NS)
tick = NS["radio_watch_tick"]
BLEDY = []


def sprawdz(co, opis, oczekiwane=True):
    ok = co == oczekiwane
    print("{} {}".format("OK  " if ok else "BŁĄD", opis))
    if not ok:
        BLEDY.append("{} → {!r}".format(opis, co))


def t(hm, dzien=25):
    return datetime(2026, 9, dzien, int(hm[:2]), int(hm[3:]))


st = {}
tick(st, t("21:55"), True)
tick(st, t("22:07"), False)
sprawdz(any("ZNIKNĄŁ między 21:55:00 a 22:07:00" in x for x in LOG), "zniknięcie z oknem czasu")
sprawdz(any("ktoś był przy komputerze" in x for x in LOG), "bezczynność 30 s = człowiek")
sprawdz(URUCHOMIENIA, "po 22:00 nie uruchamiamy", [])

tick(st, t("03:59", 26), False)
sprawdz(URUCHOMIENIA, "przed 04:00 nie uruchamiamy", [])
tick(st, t("04:00", 26), False)
sprawdz(len(URUCHOMIENIA), "04:00 bez Chrome = uruchom", 1)
tick(st, t("04:05", 26), False)
sprawdz(len(URUCHOMIENIA), "odstęp 15 min między próbami", 1)
tick(st, t("04:16", 26), True)
sprawdz(any("wrócił, okna: Radio Lewiatan" in x for x in LOG), "powrót z tytułem okna")
tick(st, t("10:00", 26), True)
sprawdz(len(URUCHOMIENIA), "działa = nie ruszamy", 1)

st, URUCHOMIENIA[:] = {}, []
for i in range(10):
    tick(st, t("05:00", 27) + timedelta(minutes=16 * i), False)
sprawdz(len(URUCHOMIENIA), "max 4 próby dziennie", 4)
sprawdz(sum("nie uruchamiam więcej" in x for x in LOG), "poddanie się zalogowane raz", 1)
tick(st, t("04:00", 28), False)
sprawdz(len(URUCHOMIENIA), "nowy dzień = nowe próby", 5)

st, URUCHOMIENIA[:] = {"nie_przed": t("06:05")}, []
tick(st, t("06:01"), False)
sprawdz(URUCHOMIENIA, "5 min po starcie aplikacji czekamy", [])
tick(st, t("06:05"), None)
sprawdz(URUCHOMIENIA, "nie wiem = nic nie robię", [])

# 1.7.6: podnosimy dokładnie ten program, który grał (Iron + Pact24), nie „chrome”
st, URUCHOMIENIA[:], LOG[:] = {}, [], []
tick(st, t("21:00", 29), True)
sprawdz(st.get("polecenie"), "zapamiętane polecenie działającego radia", IRON)
sprawdz(sum("zapamiętałem program" in x and "Iron" in x for x in LOG), "program w logu raz", 1)
tick(st, t("21:30", 29), True)
sprawdz(sum("zapamiętałem" in x for x in LOG), "bez ponownego odczytu co minutę", 1)
tick(st, t("22:05", 29), False)
tick(st, t("04:00", 30), False)
sprawdz(URUCHOMIENIA, "04:00 uruchamia zapamiętany program", [IRON])
sprawdz(any("zapamiętany program" in x for x in LOG), "log mówi, co uruchamia")

POLECENIE[0] = ""
st, URUCHOMIENIA[:] = {}, []
tick(st, t("10:00", 29), True)
tick(st, t("22:05", 29), False)
tick(st, t("04:00", 30), False)
sprawdz(URUCHOMIENIA, "nieznane polecenie = stara ścieżka (Chrome)", [""])

M2 = re.search(r"^def glowny_proces\(.*?(?=^def |\Z)", SRC, re.S | re.M)
exec(compile(M2.group(0), "app.py", "exec"), NS)
sprawdz(NS["glowny_proces"](['"x\\chrome.exe" --type=renderer', '"x\\chrome.exe" --app=a', ""]),
        "proces główny = bez --type=", '"x\\chrome.exe" --app=a')

print()
if BLEDY:
    print("PORAŻKA:", *BLEDY, sep="\n  - ")
    sys.exit(1)
print("Wszystko przeszło — pilnowanie radia działa jak opisane.")
