# -*- coding: utf-8 -*-
"""Sprawdzian kalendarza handlowego (poland_holidays.py — ten sam, ktory jedzie na sklepy).
Uruchom: python test_handel.py   (nie wymaga Windows ani pycaw)"""

import datetime

from poland_holidays import get_trade_sundays, is_trade_day


def d(rok, miesiac, dzien):
    return datetime.date(rok, miesiac, dzien)


def demo():
    # --- Niedziele handlowe 2026 (gov.pl) ---
    n2026 = get_trade_sundays(2026)
    assert d(2026, 1, 25) in n2026, "ostatnia niedziela stycznia"
    assert d(2026, 3, 29) in n2026, "niedziela palmowa (Wielkanoc 5.04.2026)"
    assert d(2026, 4, 26) in n2026
    assert d(2026, 6, 28) in n2026
    assert d(2026, 8, 30) in n2026
    assert d(2026, 12, 13) in n2026, "dwie niedziele przed Boza Narodzeniem"
    assert d(2026, 12, 20) in n2026, "20.12 to niedziela handlowa - tu byl blad (wychodzilo 6.12)"
    assert d(2026, 12, 6) not in n2026
    assert len(n2026) == 7

    # 2025: Boze Narodzenie w czwartek - inny uklad, ta sama pulapka
    n2025 = get_trade_sundays(2025)
    assert d(2025, 12, 21) in n2025 and d(2025, 12, 14) in n2025
    assert d(2025, 12, 7) not in n2025

    # 2027: 25.12 wypada w sobote
    n2027 = get_trade_sundays(2027)
    assert d(2027, 12, 19) in n2027 and d(2027, 12, 12) in n2027

    # --- Czy wolno grac ---
    assert not is_trade_day(d(2026, 7, 26)), "zwykla niedziela = cisza (zgloszenie z Bielskiej)"
    assert is_trade_day(d(2026, 7, 26), sunday_inverted=True), "Krotka 2a handluje w niehandlowe"
    assert is_trade_day(d(2026, 7, 25)), "sobota"
    assert is_trade_day(d(2026, 12, 20)), "niedziela handlowa - ma grac"
    assert not is_trade_day(d(2026, 8, 15)), "swieto ma zamykac takze sklepy z odwroconymi..."
    assert not is_trade_day(d(2026, 8, 15), sunday_inverted=True), "...niedzielami"

    print("OK - kalendarz handlowy: niedziele handlowe 2025-2027 i swieta licza sie poprawnie")


if __name__ == "__main__":
    demo()
