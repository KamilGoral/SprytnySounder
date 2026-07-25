# -*- coding: utf-8 -*-
"""Sprawdzian ciszy nocnej i kontroli zegara (moduł czas.py — ten sam, który jedzie na sklepy).
Uruchom: python test_cisza.py   (nie wymaga Windows ani pycaw)"""

import os
import time

from czas import hm_to_minutes, in_quiet_hours, clock_info, clock_summary


def cisza(h, m=0, start="22:00", koniec="05:30"):
    return in_quiet_hours(h * 60 + m,
                          hm_to_minutes(start, 22 * 60),
                          hm_to_minutes(koniec, 5 * 60 + 30))


def _z_strefa(tz):
    """Udaje zegar maszyny w danej strefie — tak sprawdzamy czas letni/zimowy."""
    stara = os.environ.get("TZ")
    os.environ["TZ"] = tz
    time.tzset()
    try:
        return clock_info()
    finally:
        if stara is None:
            del os.environ["TZ"]
        else:
            os.environ["TZ"] = stara
        time.tzset()


def demo():
    # --- Cisza nocna 22:00 - 05:30 ---
    assert cisza(22), "22:00 wchodzi cisza"
    assert cisza(23, 30)
    assert cisza(0), "polnoc to nadal cisza (tu lamie sie naiwne start<=x<end)"
    assert cisza(5, 29), "5:29 jeszcze cisza"
    assert not cisza(5, 30), "5:30 dziewczyny przychodza do pracy - ma grac"
    assert not cisza(6)
    assert not cisza(12)
    assert not cisza(21, 59), "21:59 jeszcze gra"

    # Bledna wartosc w configu nie moze wywalic sklepu - wchodzi domyslna
    assert hm_to_minutes("nie-godzina", 22 * 60) == 22 * 60
    assert hm_to_minutes("5:30", 0) == 5 * 60 + 30, "godzina bez zera wiodacego tez ma dzialac"

    # Sklep calodobowy: rowne godziny = cisza wylaczona
    assert not in_quiet_hours(3 * 60, 0, 0)

    # --- Zegar: czas letni i zimowy ---
    if hasattr(time, "tzset"):
        lato = _z_strefa("Europe/Warsaw")  # test pisany w lipcu -> czas letni
        assert lato["ok"], "polska strefa ma byc uznana za poprawna: " + clock_summary(lato)
        assert lato["dst"] is True and lato["offset_h"] == 2.0, "lato = CEST UTC+2"

        zima = _z_strefa("Etc/GMT-1")  # staly UTC+1 bez DST = polska zima
        assert zima["dst"] is False and zima["offset_h"] == 1.0
        assert zima["ok"], "zima = CET UTC+1, tez poprawne: " + clock_summary(zima)

        zla = _z_strefa("UTC")  # maszyna z fabrycznym zegarem = cisza o zlej porze
        assert not zla["ok"], "UTC musi byc zgloszone jako zla strefa"
        assert "UWAGA" in clock_summary(zla)

    print("OK - cisza nocna 22:00-05:30 (takze po polnocy) i kontrola zegara dzialaja")


if __name__ == "__main__":
    demo()
