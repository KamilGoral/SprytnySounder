#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dopisuje location /sounder/ do bloku sprytnypcmarket.pl i sprawdza konfiguracje.

Osobny skrypt, bo sed w cudzym pliku nginxa to proszenie sie o 502 na calej
domenie. Tu: kopia zapasowa -> wstawka -> nginx -t -> reload; blad testu cofa
plik do kopii. Idempotentny — drugi przebieg nic nie robi.
"""
import shutil
import subprocess
import sys
import time

PLIK = "/etc/nginx/sites-enabled/sprytnypcmarket.pl"
MARKER = "location /sounder/"
KOTWICA = "    client_max_body_size 50m;\n"
WPIS = """
    # SprytnySounder — skrzynka na logi ze sklepow (serwis na 127.0.0.1:3401).
    # TYLKO POST: sklepy maja tu dopisywac swoj log.txt, nikt z zewnatrz nie ma
    # go czytac. Odczyt logow odbywa sie przez ssh na tym serwerze.
    location /sounder/ {
        auth_basic off;
        limit_except POST { deny all; }
        client_max_body_size 1m;
        proxy_pass http://127.0.0.1:3401/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
"""

tresc = open(PLIK, encoding="utf-8").read()
if MARKER in tresc:
    print("nginx: wpis /sounder/ juz jest, nic nie zmieniam")
    sys.exit(0)
if tresc.count(KOTWICA) != 1:
    sys.exit(f"nginx: nie znalazlem jednoznacznej kotwicy {KOTWICA!r} — przerywam")

kopia = f"{PLIK}.bak-{int(time.time())}"
shutil.copy2(PLIK, kopia)
open(PLIK, "w", encoding="utf-8").write(tresc.replace(KOTWICA, KOTWICA + WPIS))

test = subprocess.run(["nginx", "-t"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                      universal_newlines=True)
if test.returncode != 0:
    shutil.copy2(kopia, PLIK)
    sys.exit(f"nginx -t nie przeszedl, plik cofniety do {kopia}:\n{test.stdout}")

subprocess.run(["systemctl", "reload", "nginx"], check=True)
print(f"nginx: /sounder/ dodane i przeladowane (kopia: {kopia})")
