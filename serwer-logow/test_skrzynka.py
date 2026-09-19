#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bramki skrzynki: przypiety identyfikator, nazwa sklepu (traversal), limit linii."""
import os
import sys
import tempfile

KATALOG = tempfile.mkdtemp(prefix="sounder-test-")
os.environ["SOUNDER_DIR"] = KATALOG
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as skrzynka  # noqa: E402

c = skrzynka.app.test_client()
ID_SKLEPU = "a1" * 16
DOBRY = {"X-Sklep-Id": ID_SKLEPU}

# Identyfikator obowiazkowy i w ustalonym formacie
assert c.post("/raport", json={"sklep": "bielska"}).status_code == 400, "brak id przeszedl"
assert c.post("/raport", json={"sklep": "bielska"},
              headers={"X-Sklep-Id": "krotkie"}).status_code == 400, "zle id przeszlo"

# TOFU: pierwszy raport przypina, podszywacz dostaje 403, a wlasciciel dalej wchodzi
assert c.post("/raport", json={"sklep": "bielska", "log": "x"}, headers=DOBRY).status_code == 200
assert c.post("/raport", json={"sklep": "bielska", "log": "x"},
              headers={"X-Sklep-Id": "b2" * 16}).status_code == 403, "podszycie sie przeszlo"
assert c.post("/raport", json={"sklep": "bielska", "log": "x"}, headers=DOBRY).status_code == 200

for zly in ("../../etc/passwd", "a/b", "", "Bielska!", "."):
    r = c.post("/raport", json={"sklep": zly, "log": "x"}, headers=DOBRY)
    assert r.status_code == 400, f"nazwa {zly!r} przeszla"

duzy = "".join(f"linia {i}\n" for i in range(9000))
r = c.post("/raport", json={"sklep": "kilinskiego", "log": duzy, "status": {"version": "1.7.0"}},
           headers=DOBRY)
assert r.status_code == 200, r.data
assert r.get_json()["linii"] == skrzynka.MAX_LINII

zapisany = open(os.path.join(KATALOG, "kilinskiego.log"), encoding="utf-8").read()
assert zapisany.endswith("linia 8999\n")
assert zapisany.startswith("linia 4000\n"), "ogon przyciety nie od tej strony"
assert sorted(os.listdir(KATALOG)) == ["bielska.id", "bielska.json", "bielska.log",
                                      "kilinskiego.id", "kilinskiego.json",
                                      "kilinskiego.log"], os.listdir(KATALOG)

print("OK - skrzynka: przypiete id, nazwa sklepu i limit linii trzymaja")
