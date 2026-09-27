"""Phasen je Anbieter: ok -> warnung -> stopp -> limit (Reset = Fenster abgelaufen)."""

STUFEN = ["ok", "warnung", "stopp", "limit"]
ART_TEXT = {"fuenf": "5h", "woche": "Woche"}


def fenster_id(anbieter, art, reset):
    """Stabile Kennung eines Limitfensters (Reset auf 10 min gerundet, weil Quellen um Sekunden abweichen)."""
    return f"{anbieter}-{art}-{int(round((reset or 0) / 600.0))}"


def claude_sanft(stopp_art, p):
    """v1.4 N2: sanfter Stopp für Claude? Nur am 5h-Stopp ohne Wochenreserve und mit claude_stopp_art "sanft";
    Wochen-Stopp und Wochenreserve bleiben immer ein geordneter Stopp mit Sicherungsauftrag."""
    return (stopp_art or "sanft") != "geordnet" and (p or {}).get("art") != "woche" \
        and not (p or {}).get("reserve_erreicht")


def waehle_quelle(*kandidaten, now=None, max_alter_s=None):
    """Von mehreren Nutzungsständen den frischesten nehmen.

    v1.4: mit now hat eine junge offizielle Quelle (quelle == "offiziell", höchstens max_alter_s alt) Vorrang;
    sonst gewinnt der frischeste Stand, Kandidaten ohne Stand verlieren gegen jeden mit Stand
    (Gleichstand: der zuerst genannte)."""
    gueltig = [k for k in kandidaten if k and (k.get("fuenf") or k.get("woche"))]
    if not gueltig:
        return None
    if now is None:
        return max(gueltig, key=lambda k: k.get("stand") or 0)
    for k in gueltig:
        if k.get("quelle") == "offiziell" and k.get("stand") \
                and (max_alter_s is None or now - k["stand"] <= max_alter_s):
            return k
    mit_stand = [k for k in gueltig if k.get("stand")]
    return max(mit_stand or gueltig, key=lambda k: k.get("stand") or 0)


def berechne(anbieter, daten, hinweise, k, now):
    """daten: {'fuenf': {pct, reset}, 'woche': {...}, 'stand', 'quelle'}; hinweise: [{'art','reset'}] aus Limit-Ereignissen."""
    s = k["schwellen"]
    daten = daten or {}

    def aktiv(f):
        return bool(f and f.get("reset") and f["reset"] > now)

    f5, fw = daten.get("fuenf"), daten.get("woche")
    p5 = f5["pct"] if aktiv(f5) else 0.0
    pw = fw["pct"] if aktiv(fw) else 0.0
    r5 = f5["reset"] if aktiv(f5) else None
    rw = fw["reset"] if aktiv(fw) else None

    kandidaten = []
    for art, p, r, warn, stopp in (("fuenf", p5, r5, s["warnung"], s["stopp"]),
                                   ("woche", pw, rw, s["woche_warnung"], s["woche_stopp"])):
        if r is None:
            continue
        stufe = 3 if p >= 100 else 2 if p >= stopp else 1 if p >= warn else 0
        kandidaten.append((stufe, r, art, p))
    for h in hinweise or []:
        if h.get("reset") and h["reset"] > now:
            art = h.get("art") or "fuenf"
            p = (pw if art == "woche" else p5) or 100.0
            kandidaten.append((3, h["reset"], art, max(p, 100.0)))

    if kandidaten:
        stufe, reset, art, pct = max(kandidaten)
    else:
        stufe, reset, art, pct = 0, None, "fuenf", 0.0
    if stufe == 0:
        art, reset, pct = "fuenf", r5, p5

    stand = daten.get("stand")
    return {
        "anbieter": anbieter,
        "phase": STUFEN[stufe],
        "art": art,
        "pct": round(pct, 1),
        "reset": reset,
        "fenster_id": fenster_id(anbieter, art, reset) if reset else None,
        "pct5": round(p5, 1), "reset5": r5,
        "pctw": round(pw, 1), "resetw": rw,
        "reserve_erreicht": bool(rw) and pw >= 100 - s["wochen_reserve"],
        "stand": stand,
        "alter": (now - stand) if stand else None,
        "veraltet": (not stand) or (now - stand) > k["daten"]["max_alter_minuten"] * 60,
        "quelle": daten.get("quelle"),
        "hat_daten": bool(f5 or fw),
    }
