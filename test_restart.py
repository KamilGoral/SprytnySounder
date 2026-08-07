# -*- coding: utf-8 -*-
"""Sprawdzian restartu po aktualizacji (regresja Kilinskiego, 1.6.6 -> 1.6.7).
os.exec* na Windows skleja argumenty spacjami BEZ cudzyslowow, wiec sciezka
"C:\\komunikaty glosowe\\app.py" rozpadala sie na "C:\\komunikaty" + reszte
i restart po auto-aktualizacji zabijal serwer. Fix: na nt subprocess.Popen
(cytuje przez list2cmdline) + os._exit.

Uruchom: python test_restart.py
"""
import re
import subprocess


def demo():
    # Mechanizm fixa: Popen/list2cmdline cytuje sciezke ze spacja, exec nie
    path = r"C:\komunikaty glosowe\app.py"
    assert subprocess.list2cmdline([path]) == '"%s"' % path
    assert " ".join([path]).split(" ")[0] == r"C:\komunikaty"  # tak psul exec

    # Zadnego golego os.execl poza galezia posix w restart_self/restart_app
    for fname in ("app.py", "update.py"):
        src = open(fname, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"os\.execl", src):
            before = src[:m.start()].rsplit("def ", 1)[-1]
            assert 'os.name == "nt"' in before, (
                "%s: os.execl bez galezi Windows (Popen)" % fname)
    assert "restart_self()" in open("app.py", encoding="utf-8").read()
    print("OK - restart cytuje sciezki ze spacjami")


if __name__ == "__main__":
    demo()
