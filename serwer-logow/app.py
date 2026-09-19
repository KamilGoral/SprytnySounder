#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Skrzynka na logi ze sklepow SprytnySounder (Hetzner, 127.0.0.1:3401).

Sklepy siedza za NAT-em w roznych LAN-ach — z zewnatrz nie da sie do nich wejsc,
a log.txt jest jedynym dowodem, co dzialo sie w nocy. Dlatego to sklep wysyla
tutaj ogon swojego logu i status.

Ruch idzie TYLKO w jedna strone: ten serwis przyjmuje POST i zapisuje do pliku.
Nic nie oddaje i niczego nie wykonuje, wiec skrzynka na logi nie moze stac sie
kanalem sterowania sklepem. Odczyt = ssh na ten serwer (nginx przepuszcza tu
wylacznie POST).

Wdrozenie: wdroz.sh obok.
"""
import hmac
import json
import os
import re
from datetime import datetime

from flask import Flask, jsonify, request

KATALOG = os.environ.get("SOUNDER_DIR", "/opt/sounder-logi/dane")
PORT = int(os.environ.get("SOUNDER_PORT", "3401"))

# Nazwa sklepu ladzie w nazwie pliku — bez tej bramki "../../etc/passwd" tez by
# byl poprawnym sklepem. Slug pochodzi z location.txt: male litery, cyfry, myslnik.
SKLEP_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
ID_RE = re.compile(r"^[0-9a-f]{32,64}$")   # to, co sklep losuje przez os.urandom
MAX_LINII = 5000        # log na serwerze to okno, nie archiwum — zero przyrostu
MAX_ZNAKOW = 800_000    # twardy sufit na jeden raport (nginx tnie juz na 1 MB)

app = Flask(__name__)


def _tozsamosc_ok(sklep, ident):
    """TOFU: pierwszy raport danego sklepu przypina jego identyfikator, kazdy
    nastepny musi sie z nim zgadzac. Dzieki temu w PUBLICZNYM repo sklepow nie
    ma zadnego sekretu do wykradzenia — jest tylko adres tej skrzynki.

    Okno na podszycie sie pod sklep trwa od wdrozenia do pierwszego raportu
    (max godzina). Kto sie przypial i z jakiego IP, widac w <sklep>.id oraz w
    <sklep>.json; ponowne przypiecie = skasowanie <sklep>.id na serwerze."""
    plik = os.path.join(KATALOG, sklep + ".id")
    try:
        with open(plik, encoding="utf-8") as f:
            return hmac.compare_digest(f.read().strip(), ident)
    except OSError:
        _zapisz(plik, ident)
        return True


def _zapisz(sciezka, tresc):
    """Zapis atomowy — nigdy nie chce zobaczyc w polowie nadpisanego logu."""
    tmp = sciezka + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(tresc)
    os.replace(tmp, sciezka)


@app.route("/raport", methods=["POST"])
def raport():
    dane = request.get_json(silent=True)
    if not isinstance(dane, dict):
        return jsonify({"error": "oczekiwano obiektu JSON"}), 400

    sklep = str(dane.get("sklep", "")).strip().lower()
    if not SKLEP_RE.match(sklep):
        return jsonify({"error": "zla nazwa sklepu"}), 400

    ident = request.headers.get("X-Sklep-Id", "").strip().lower()
    if not ID_RE.match(ident):
        return jsonify({"error": "brak identyfikatora sklepu"}), 400

    os.makedirs(KATALOG, exist_ok=True)
    if not _tozsamosc_ok(sklep, ident):
        return jsonify({"error": "identyfikator nie zgadza sie z przypietym"}), 403

    linie = str(dane.get("log", ""))[-MAX_ZNAKOW:].splitlines(keepends=True)[-MAX_LINII:]
    _zapisz(os.path.join(KATALOG, sklep + ".log"), "".join(linie))
    _zapisz(os.path.join(KATALOG, sklep + ".json"), json.dumps({
        "odebrano": datetime.now().isoformat(timespec="seconds"),
        "ip": request.headers.get("X-Real-IP", request.remote_addr),
        "status": dane.get("status"),
    }, ensure_ascii=False, indent=2))
    return jsonify({"status": "ok", "linii": len(linie)})


@app.route("/zdrowie", methods=["GET"])
def zdrowie():
    """Tylko do sprawdzenia z samego serwera — nginx nie wpuszcza tu GET-ow."""
    try:
        pliki = sorted(f for f in os.listdir(KATALOG) if f.endswith(".log"))
    except OSError:
        pliki = []
    return jsonify({"status": "ok", "sklepy": [f[:-4] for f in pliki]})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PORT)
