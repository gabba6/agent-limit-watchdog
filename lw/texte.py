"""Texte an die Agenten und kurze Push-Texte (sachlich formuliert, keine Befehlsform à la System).

Die Wörter selbst stehen zweisprachig in sprache.py; hier werden sie zusammengesetzt.
"""

from . import sprache, util
from .sprache import t

NAME = {"claude": "Claude", "codex": "Codex"}

# Präfixe, an denen der Hook eigene Fortsetzungen erkennt (beide Sprachen, unabhängig von der Einstellung)
PRAEFIXE = ("Limit-Wächter:", "Limit Watchdog:")

# Anfang des festen Prompts von Claudes eingebauter Fortsetzung (Binary 2.1.282)
EINGEBAUT_PRAEFIX = "Your claude.ai usage limit has reset"


def fortsetzungsprompt():
    return t("prompt_fortsetzen")


def art_text(art):
    return t("art_woche") if art == "woche" else t("art_fuenf")


def stand(p, bezug=None):
    return t("stand", art=art_text(p.get("art")), pct=sprache.prozent(p.get("pct", 0)),
             reset=util.uhrzeit(p.get("reset"), bezug))


def _danach(p):
    return t("ohne_fortsetzung", wer=sprache.wer()) if p.get("reserve_erreicht") else t("nach_reset")


def _herkunft():
    return t("hook_herkunft_name", name=sprache.NUTZER) if sprache.NUTZER else t("hook_herkunft")


def sicherungsauftrag(p, bezug=None):
    return (t("sicherung_kopf", app=t("app"), herkunft=_herkunft(), stand=stand(p, bezug))
            + t("sicherung_kern") + _danach(p))


def stopp_kontext(p, bezug=None):
    return t("stopp_kontext", app=t("app"), stand=stand(p, bezug))


def deny_grund(p, bezug=None):
    return t("deny_grund", app=t("app"), stand=stand(p, bezug))


def prompt_hinweis(p, bezug=None):
    return t("prompt_hinweis", app=t("app"), stand=stand(p, bezug))


def reserve_block(p, bezug=None):
    return t("reserve_block", app=t("app"), pctw=sprache.prozent(p.get("pctw", 0)), wer=sprache.wer())


def codex_stopp(p, bezug=None):
    return t("codex_kopf", app=t("app"), stand=stand(p, bezug)) + t("codex_kern") + _danach(p)


# ---------------------------------------------------------------- Push-Texte (kurz, ohne Projektinhalte)

def push_phase(anbieter, p, anzahl_wartend=0, remote_hinweis=""):
    werte = {"n": NAME[anbieter], "art": art_text(p["art"]), "pct": sprache.prozent(p["pct"]),
             "reset": util.uhrzeit(p["reset"]), "hinweis": remote_hinweis}
    if p["phase"] == "warnung":
        return t("push_warnung", **werte)
    if p["phase"] == "stopp":
        return t("push_stopp", **werte)
    if p["phase"] == "limit":
        warten = t("push_limit_warten", anzahl=anzahl_wartend) if anzahl_wartend else ""
        return t("push_limit", warten=warten, **werte)
    return f"{NAME[anbieter]}: {p['phase']}"
