"""Bildschirm eines Agent-Terminals einordnen, bevor der Wächter etwas sendet.

Grundregel: Gesendet wird nur bei 'bereit' (leere Eingabezeile, kein Menü, keine Kaufoption)
bzw. bei 'stale' nur ein Enter. Alles Unklare heißt: nichts senden, Push an den Nutzer.
Geprüft wird der untere Bereich, weil Menüs und Eingabe dort stehen; der Verlauf darüber
kann beliebige Wörter enthalten (auch "credits") und darf nicht zu Fehlalarmen führen.
"""

import re

from .sprache import t

UNTEN_ZEILEN = 12

MENUE = [
    r"Stop and wait for limit to reset",
    r"Don.t continue automatically",
    r"auto-continue in",
    r"any key to stay",
    r"Press enter to confirm",
    r"enter to (select|confirm)",
    r"esc to (go back|cancel)",
    r"^\s*[❯›]\s*\d+\.\s+\S",            # ausgewählte Menüzeile (Zeiger + Nummer)
    r"\[y/n\]|\(y/n\)",
    r"Resume this conversation\?",
    r"Resume from summary",
    r"Do you want to",
    r"Yes, and don.t ask",
    r"trust (this|the) (folder|hooks?)",
    r"/hooks to review",
    r"↑↓ (to )?select",                  # Auswahllisten (Tasten wirken dort direkt)
    r"x stop workflow|\bp pause\b|esc back",   # /workflows-Ansicht: Buchstaben wären Tastenbefehle
]

EINGEBAUT_WARTET = [
    r"continu\w* automatically",
    r"auto-?continu",
    r"waiting for (the |your )?(usage )?limit",
    r"wait(ing)? (until|for) (the )?reset",
]

# Nur die englischen UI-Formulierungen von Claude Code / Codex (Menüs, Limit-Hinweise).
# Allgemeine Wörter wie "credits" oder "kaufen" kommen auch im Gesprächstext vor und lösten
# an echten Terminals Fehlalarme aus.
GELD = [
    r"usage credits?", r"switch to usage", r"add funds", r"upgrade your plan", r"upgrade to (pro|max|plus)",
    r"/upgrade\b", r"extra usage", r"/extra-usage", r"/usage-credits", r"purchase (more )?credits",
    r"buy (more )?credits", r"reset credits?", r"use (a |1 )?(rate limit )?reset", r"pay as you go",
]

STALE = [r"press enter to continue"]

BESCHAEFTIGT = [
    r"esc to interrupt", r"ctrl\+c to interrupt",
    r"^\s*[✻✶✢✳✽✺✹·*]\s*\S+…",           # Claude 2.1.283: "✻ Thundering… (36m 32s · ↓ 210k tokens)"
    r"^\s*[•◦·]\s*Working\b", r"\bWorking \(\d",   # Codex
]

# Bekannte, harmlose Limit-Sätze, die Kaufwörter enthalten (statischer Text, kein Menü)
STATISCH_ENTFERNEN = [
    r"You.ve hit your usage limit\..{0,400}?try again at [^.]{1,60}\.",   # Codex
]

CLAUDE_PROMPT = re.compile(r"^\s*❯\s?(.*)$")
CODEX_PROMPT = re.compile(r"^\s*›\s?(.*)$")


def _unten(zeilen, n=UNTEN_ZEILEN):
    nicht_leer = [z.rstrip() for z in zeilen if z and z.strip()]
    return nicht_leer[-n:]


def _treffer(muster, text, flags=re.I | re.M):
    for m in muster:
        if re.search(m, text, flags):
            return m
    return None


def klassifiziere(zeilen, anbieter):
    """-> (art, grund). art: bereit | stale | beschaeftigt | menue | eingebaut_wartet | geld |
    eingabe_belegt | unbekannt."""
    if not zeilen:
        return "unbekannt", t("bs_leer")
    unten = _unten(zeilen)
    text_unten = "\n".join(unten)
    fliess = re.sub(r"\s+", " ", " ".join(unten))
    for m in STATISCH_ENTFERNEN:
        fliess = re.sub(m, " [limitmeldung] ", fliess, flags=re.I | re.S)

    m = _treffer(MENUE, text_unten)
    if m:
        return "menue", t("bs_menue", m=m)
    m = _treffer(EINGEBAUT_WARTET, fliess)
    if m:
        return "eingebaut_wartet", t("bs_eingebaut", m=m)
    m = _treffer(GELD, fliess)
    if m:
        return "geld", t("bs_geld", m=m)
    m = _treffer(STALE, fliess)
    if m:
        return "stale", t("bs_stale")
    m = _treffer(BESCHAEFTIGT, text_unten)
    if m:
        return "beschaeftigt", t("bs_arbeitet")

    muster = CLAUDE_PROMPT if anbieter == "claude" else CODEX_PROMPT
    for zeile in reversed(unten):
        treffer = muster.match(zeile)
        if not treffer:
            continue
        inhalt = treffer.group(1).strip()
        if anbieter == "codex":
            # Codex zeigt in der leeren Eingabe einen wechselnden Platzhalter; am Bildschirm
            # nicht von Text zu unterscheiden. Nachts tippt dort niemand, deshalb 'bereit'.
            return "bereit", t("bs_codex_bereit")
        if not inhalt or inhalt.startswith("Try \""):
            return "bereit", t("bs_bereit")
        return "eingabe_belegt", t("bs_belegt")
    return "unbekannt", t("bs_keine")


def ausschnitt(zeilen, n=8, breite=100):
    """Kurzer unterer Ausschnitt fürs lokale Log (zur Nachjustierung beim ersten echten Limit)."""
    return " | ".join(z[:breite] for z in _unten(zeilen, n))
