"""Gemeinsame Helfer: Pfade, Zeit, atomare JSON-Dateien, Sperren, Log."""

import contextlib
import fcntl
import json
import os
import tempfile
import time

from . import sprache

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_MAX_BYTES = 1_000_000


def basis():
    """Laufzeitordner (Zustand, Logs). Tests setzen LIMIT_WAECHTER_HOME."""
    return os.environ.get("LIMIT_WAECHTER_HOME") or os.path.expanduser("~/.limit-waechter")


def pfad(*teile):
    p = os.path.join(basis(), *teile)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def jetzt():
    """Aktuelle Zeit in Sekunden; LIMIT_WAECHTER_NOW überschreibt sie für Tests und Simulation."""
    wert = os.environ.get("LIMIT_WAECHTER_NOW")
    return float(wert) if wert else time.time()


def lies_json(datei, standard=None):
    try:
        with open(datei, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return standard


def schreib_json(datei, daten):
    """Atomar schreiben (tmp + rename), damit parallele Leser nie halbe Dateien sehen."""
    os.makedirs(os.path.dirname(datei), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(datei), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(daten, f, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, datei)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def sperre(datei, warten=True):
    """Exklusive Sperre über eine .lock-Datei. Mit warten=False: RuntimeError, wenn belegt."""
    os.makedirs(os.path.dirname(datei), exist_ok=True)
    fd = os.open(datei + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        flags = fcntl.LOCK_EX | (0 if warten else fcntl.LOCK_NB)
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError:
            raise RuntimeError("gesperrt")
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _anhaengen(datei, zeile):
    try:
        if os.path.getsize(datei) > LOG_MAX_BYTES:
            os.replace(datei, datei + ".1")
    except OSError:
        pass
    with open(datei, "a", encoding="utf-8") as f:
        f.write(zeile + "\n")


def log(text):
    stempel = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(jetzt()))
    _anhaengen(pfad("log", "waechter.log"), f"{stempel} {text}")


def ereignis(typ, **daten):
    """Maschinenlesbares Ereignis für den Morgenbericht (keine Secrets, keine Prompts)."""
    eintrag = {"ts": round(jetzt(), 3), "typ": typ}
    eintrag.update(daten)
    _anhaengen(pfad("log", "ereignisse.jsonl"), json.dumps(eintrag, ensure_ascii=False, sort_keys=True))


def lies_ereignisse(seit=0.0, bis=None):
    ergebnis = []
    for datei in (pfad("log", "ereignisse.jsonl") + ".1", pfad("log", "ereignisse.jsonl")):
        try:
            with open(datei, encoding="utf-8") as f:
                for zeile in f:
                    try:
                        e = json.loads(zeile)
                    except ValueError:
                        continue
                    if e.get("ts", 0) >= seit and (bis is None or e["ts"] < bis):
                        ergebnis.append(e)
        except OSError:
            continue
    return ergebnis


def uhrzeit(ts, bezug=None):
    """16:30, bei anderem Tag mit Wochentag: So 03:00 (en: Sun 03:00)."""
    if not ts:
        return "?"
    t = time.localtime(ts)
    b = time.localtime(bezug if bezug is not None else jetzt())
    if (t.tm_year, t.tm_yday) == (b.tm_year, b.tm_yday):
        return time.strftime("%H:%M", t)
    tag = sprache.WOCHENTAGE[sprache.AKTUELL][t.tm_wday]
    return f"{tag} {time.strftime('%H:%M', t)}"


def _zahl(x):
    text = f"{x:.1f}"
    return text.replace(".", ",") if sprache.AKTUELL == "de" else text


def dauer_text(sekunden):
    s = int(max(0, sekunden))
    if s < 90:
        return f"{s} s"
    if s < 5400:
        return f"{round(s / 60)} min"
    if s < 172800:
        return f"{_zahl(s / 3600)} h"
    return f"{_zahl(s / 86400)} {sprache.t('tage')}"


def parse_dauer(text):
    """'90m', '2h', '1d', '45' (Minuten) -> Sekunden."""
    text = text.strip().lower()
    faktor = {"s": 1, "m": 60, "h": 3600, "d": 86400, "t": 86400}
    if text and text[-1] in faktor:
        return float(text[:-1].replace(",", ".")) * faktor[text[-1]]
    return float(text.replace(",", ".")) * 60
