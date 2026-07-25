# -*- coding: utf-8 -*-
"""Sprawdzian rozpoznawania tokena aktualizacji.
Regresja po bledzie, ktory po cichu wylaczal autoryzacje: 'github_pat_...' zaczyna
sie od 'gi', nie od 'gh', wiec skrot startswith('gh') odrzucal prawidlowy token.
Na publicznym repo nie widac roznicy, na prywatnym to koniec aktualizacji na sklepach.

Uruchom: python test_token.py
"""

from update import looks_like_token


def demo():
    # Fine-grained (te wystawia sie dzis) - MUSZA byc uznane
    assert looks_like_token("github_pat_11ABCDEFG_przykladowy")

    # Klasyczne warianty tez
    assert looks_like_token("ghp_przykladowy")
    assert looks_like_token("gho_przykladowy")

    # Smieci odrzucone - inaczej doklejalibysmy bezsensowny naglowek
    assert not looks_like_token("")
    assert not looks_like_token("# wklej tutaj token")
    assert not looks_like_token("gh")

    print("OK - token rozpoznawany (takze fine-grained github_pat_)")


if __name__ == "__main__":
    demo()
