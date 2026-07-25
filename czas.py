# -*- coding: utf-8 -*-
"""Czas: cisza nocna i kontrola zegara maszyny.

Osobny moduł, bo app.py ciągnie pycaw/pygame (tylko Windows), a tę logikę
chcemy dać się sprawdzić wszędzie — patrz test_cisza.py.
"""

import time
from datetime import datetime


def hm_to_minutes(value, default_minutes):
    """'22:00' -> 1320. Byle jaka wartość z configu nie może wywalić sklepu."""
    try:
        hours, minutes = str(value).strip().split(":")
        return (int(hours) * 60 + int(minutes)) % (24 * 60)
    except Exception:
        return default_minutes


def in_quiet_hours(now_minutes, start_minutes, end_minutes):
    """Czy dana minuta doby wpada w ciszę nocną. Zakres przechodzi przez północ
    (22:00 -> 05:30), więc nie da się tego liczyć zwykłym 'start <= x < end'."""
    if start_minutes == end_minutes:
        return False  # równe godziny = cisza wyłączona (sklep całodobowy)
    if start_minutes < end_minutes:
        return start_minutes <= now_minutes < end_minutes
    return now_minutes >= start_minutes or now_minutes < end_minutes


def clock_info(now=None):
    """Strefa czasowa maszyny + czy trwa czas letni.

    Cisza nocna liczy się z zegara Windows, więc sklep z ustawioną złą strefą
    milknie o złej porze, a przy zmianie czasu letni/zimowy przesuwa się o
    godzinę. Polska: zimą UTC+1 (CET), latem UTC+2 (CEST).
    """
    is_dst = bool(time.localtime().tm_isdst)
    offset_h = -(time.altzone if is_dst else time.timezone) / 3600.0
    expected_h = 2.0 if is_dst else 1.0
    names = time.tzname
    return {
        "tz": names[1] if is_dst and len(names) > 1 else names[0],
        "dst": is_dst,
        "offset_h": offset_h,
        "expected_h": expected_h,
        "ok": abs(offset_h - expected_h) < 0.01,
        "local_time": (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
    }


def clock_summary(info=None):
    """Jedno zdanie do log.txt — po nim widać, czy zegar sklepu jest wiarygodny."""
    info = info or clock_info()
    czas = "letni" if info["dst"] else "zimowy"
    if info["ok"]:
        return "zegar {} UTC{:+.0f} (czas {})".format(info["tz"], info["offset_h"], czas)
    return ("UWAGA zla strefa czasowa: {} UTC{:+.0f}, a dla Polski powinno byc "
            "UTC{:+.0f} — cisza nocna zadziala o zlej godzinie").format(
                info["tz"], info["offset_h"], info["expected_h"])
