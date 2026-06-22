"""
Modu³ dni wolnych od handlu w Polsce.
Okreœla czy w danym dniu handel jest dozwolony.

Zasady:
- Niedziele: generalnie niehandlowe, z wyj¹tkiem ~7 niedziel handlowych w roku
- Œwiêta pañstwowe: 1 Stycznia, 6 Stycznia, Wielkanoc, Poniedzia³ek Wielkanocny,
  1 Maja, 3 Maja, Bo¿e Cia³o, 15 Sierpnia, 1 Listopada, 11 Listopada,
  25 Grudnia, 26 Grudnia

Konfiguracja per-sklep:
- sunday_inverted: True = sklep handluje w niedziele niehandlowe,
  a w handlowe jest zamkniêty (przypadek Krótka 2a)

Uwaga: przepisy o niedzielach handlowych mog¹ siê zmieniaæ.
SprawdŸ aktualne przepisy przed sezonem.
"""

import datetime


def _easter_date(year):
    """
    Algorytm Gaussa obliczania daty Wielkanocy.
    Dzia³a dla lat 1900-2099.
    """
    a = year % 19
    b = year % 4
    c = year % 7
    d = (19 * a + 24) % 30
    e = (2 * b + 4 * c + 6 * d + 5) % 7
    days = 22 + d + e
    if days <= 31:
        return datetime.date(year, 3, days)
    return datetime.date(year, 4, days - 31)


def _get_fixed_holidays(year):
    """Zwraca set dat œwi¹t o sta³ej dacie."""
    return {
        datetime.date(year, 1, 1),    # Nowy Rok
        datetime.date(year, 1, 6),    # Œwiêto Trzech Króli
        datetime.date(year, 5, 1),    # Œwiêto Pracy
        datetime.date(year, 5, 3),    # Œwiêto Konstytucji 3 Maja
        datetime.date(year, 8, 15),   # Wniebowziêcie NMP
        datetime.date(year, 11, 1),   # Wszystkich Œwiêtych
        datetime.date(year, 11, 11),  # Œwiêto Niepodleg³oœci
        datetime.date(year, 12, 25),  # Bo¿e Narodzenie (pierwszy dzieñ)
        datetime.date(year, 12, 26),  # Bo¿e Narodzenie (drugi dzieñ)
    }


def _get_movable_holidays(year):
    """Zwraca set dat œwi¹t ruchomych."""
    easter_date = _easter_date(year)
    corpus_christi = easter_date + datetime.timedelta(days=60)  # Bo¿e Cia³o
    return {
        easter_date,                                   # Wielkanoc (niedziela)
        easter_date + datetime.timedelta(days=1),      # Poniedzia³ek Wielkanocny
        corpus_christi,                                # Bo¿e Cia³o
    }


def get_trade_sundays(year):
    """
    Zwraca listê niedziel handlowych w danym roku.
    W Polsce od 2018: generalny zakaz handlu w niedziele,
    z wyj¹tkiem ostatnich niedziel stycznia, kwietnia, czerwca i sierpnia
    oraz 2 niedziel przed Wielkanoc¹ i 2 przed Bo¿ym Narodzeniem.

    Uwaga: konkretne dni mog¹ siê zmieniaæ.
    Dla pewnoœci zawsze sprawdŸ aktualne przepisy (gov.pl).
    """
    trade_sundays = []

    # Ostatnia niedziela stycznia, kwietnia, czerwca, sierpnia
    for month in [1, 4, 6, 8]:
        if month == 12:
            last_day = datetime.date(year, 12, 31)
        else:
            last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
        # Cofaj do ostatniej niedzieli (weekday() == 6)
        while last_day.weekday() != 6:
            last_day -= datetime.timedelta(days=1)
        trade_sundays.append(last_day)

    # Niedziela przed Wielkanoc¹ (Palmowa)
    easter_date = _easter_date(year)
    palm_sunday = easter_date - datetime.timedelta(days=7)
    trade_sundays.append(palm_sunday)

    # 2 niedziele przed Bo¿ym Narodzeniem
    christmas = datetime.date(year, 12, 25)
    for i in range(2):
        advent_sunday = christmas - datetime.timedelta(days=7 * (i + 1))
        while advent_sunday.weekday() != 6:
            advent_sunday -= datetime.timedelta(days=1)
        trade_sundays.append(advent_sunday)

    return sorted(set(trade_sundays))


def is_public_holiday(date_obj):
    """Sprawdza czy data jest œwiêtem pañstwowym (wolnym od handlu)."""
    all_holidays = _get_fixed_holidays(date_obj.year)
    all_holidays.update(_get_movable_holidays(date_obj.year))
    return date_obj in all_holidays


def _get_holiday_name(date_obj):
    """Zwraca nazwê œwiêta dla danej daty, lub None."""
    year = date_obj.year
    fixed = {
        datetime.date(year, 1, 1): "Nowy Rok",
        datetime.date(year, 1, 6): "Œwiêto Trzech Króli",
        datetime.date(year, 5, 1): "Œwiêto Pracy",
        datetime.date(year, 5, 3): "Œwiêto Konstytucji 3 Maja",
        datetime.date(year, 8, 15): "Wniebowziêcie NMP",
        datetime.date(year, 11, 1): "Wszystkich Œwiêtych",
        datetime.date(year, 11, 11): "Œwiêto Niepodleg³oœci",
        datetime.date(year, 12, 25): "Bo¿e Narodzenie (dzieñ 1)",
        datetime.date(year, 12, 26): "Bo¿e Narodzenie (dzieñ 2)",
    }
    if date_obj in fixed:
        return fixed[date_obj]

    easter_date = _easter_date(year)
    movable = {
        easter_date: "Wielkanoc",
        easter_date + datetime.timedelta(days=1): "Poniedzia³ek Wielkanocny",
        easter_date + datetime.timedelta(days=60): "Bo¿e Cia³o",
    }
    return movable.get(date_obj)


def is_trade_day(date_obj=None, sunday_inverted=False):
    """
    G³ówna funkcja: czy w danym dniu handel jest dozwolony?

    Args:
        date_obj: Data do sprawdzenia (domyœlnie dzisiaj)
        sunday_inverted: Jeśli True, sklep ma odwrócone niedziele
                        (handluje w niehandlowe, zamkniêty w handlowe)

    Returns:
        bool: True jeśli mo¿na handlowaæ, False jeśli wolne od handlu
    """
    if date_obj is None:
        date_obj = datetime.date.today()

    # Œwiêta pañstwowe — zawsze wolne od handlu (niezale¿nie od flagi)
    if is_public_holiday(date_obj):
        return False

    # SprawdŸ czy to niedziela
    is_sunday = date_obj.weekday() == 6

    if is_sunday:
        trade_sundays = get_trade_sundays(date_obj.year)
        is_trade_sunday = date_obj in trade_sundays

        if sunday_inverted:
            # Odwrócone: handlujemy w niehandlowe niedziele
            return not is_trade_sunday
        else:
            # Normalne: handlujemy tylko w handlowe niedziele
            return is_trade_sunday

    # Dni powszednie i soboty — normalny handel
    return True


def get_trade_info(date_obj=None, sunday_inverted=False):
    """
    Zwraca pe³n¹ informacjê o dniu handlowym.

    Returns:
        dict: {
            'date': 'YYYY-MM-DD',
            'day_name': 'poniedzia³ek',
            'is_trade_day': True/False,
            'is_holiday': True/False,
            'is_sunday': True/False,
            'is_trade_sunday': True/False,
            'sunday_inverted': True/False,
            'reason': '...'
        }
    """
    if date_obj is None:
        date_obj = datetime.date.today()

    day_names = ['poniedzia³ek', 'wtorek', 'œroda', 'czwartek', 'pi¹tek', 'sobota', 'niedziela']
    is_sunday = date_obj.weekday() == 6
    holiday = is_public_holiday(date_obj)

    holiday_name = _get_holiday_name(date_obj) if holiday else None
    trade_sundays = get_trade_sundays(date_obj.year)
    is_trade_sunday = date_obj in trade_sundays if is_sunday else False

    trade_day = is_trade_day(date_obj, sunday_inverted)

    # Ustal powód
    if holiday:
        reason = f"Œwiêto: {holiday_name}"
    elif is_sunday and sunday_inverted and not is_trade_sunday:
        reason = "Niedziela niehandlowa (odwrócone — OTWARTE)"
    elif is_sunday and sunday_inverted and is_trade_sunday:
        reason = "Niedziela handlowa (odwrócone — zamkniête)"
    elif is_sunday and is_trade_sunday:
        reason = "Niedziela handlowa"
    elif is_sunday and not is_trade_sunday:
        reason = "Niedziela niehandlowa"
    else:
        reason = "Dzieñ handlowy"

    return {
        'date': date_obj.isoformat(),
        'day_name': day_names[date_obj.weekday()],
        'is_trade_day': trade_day,
        'is_holiday': holiday,
        'is_sunday': is_sunday,
        'is_trade_sunday': is_trade_sunday,
        'sunday_inverted': sunday_inverted,
        'reason': reason,
    }
