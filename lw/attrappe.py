"""Orca-Attrappe für Tests und `simulate`: gleiche Schnittstelle wie lw.orca.Orca, sendet nie wirklich."""

from .orca import OrcaFehler


class OrcaAttrappe:
    def __init__(self, terminals=None, agenten=None, bildschirme=None, konten=None, erreichbar_=True,
                 senden_ok=True):
        self._terminals = terminals or []
        self._agenten = agenten or {}
        self.bildschirme = bildschirme or {}     # handle -> Zeilenliste
        self._konten = konten or {}
        self._erreichbar = erreichbar_
        self.senden_ok = senden_ok
        self.gesendet = []
        self.dry_run = True

    def _pruefen(self):
        if not self._erreichbar:
            raise OrcaFehler("Orca-Attrappe: nicht erreichbar")

    def erreichbar(self):
        return self._erreichbar

    def konten(self):
        self._pruefen()
        return self._konten

    def terminals(self):
        self._pruefen()
        return list(self._terminals)

    def agenten(self):
        self._pruefen()
        return dict(self._agenten)

    def bildschirm(self, handle):
        self._pruefen()
        return {"zeilen": list(self.bildschirme.get(handle, [])), "quelle": "screen", "status": "running"}

    def senden(self, handle, text=None, enter=True, warten=60):
        self._pruefen()
        self.gesendet.append({"handle": handle, "text": text, "enter": enter})
        return {"angenommen": self.senden_ok, "gestartet": self.senden_ok, "stufen": ["input_accepted"]}

    def erstellen(self, worktree, befehl, titel):
        self._pruefen()
        self.gesendet.append({"erstellen": worktree, "befehl": befehl, "titel": titel})
        return {"handle": "term_neu"}
