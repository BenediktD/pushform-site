#!/usr/bin/env python3
"""Traegt den App-Store-Durchschnitt (Deutschland) in index.html ein.

Laeuft woechentlich als GitHub-Job (.github/workflows/bewertung.yml), kann aber
auch von Hand gestartet werden:  python3 .github/scripts/bewertung.py [--trocken]

- Quelle: Apples oeffentliche Abfrage itunes.apple.com/lookup, je Land (LAENDER).
  Der angezeigte Schnitt ist ueber alle Laender nach Anzahl gewichtet und wird
  auf eine Nachkommastelle ABGERUNDET (4,95 -> 4,9), damit er nie uebertreibt.
  Die Besucher der Website schicken dabei nichts an Apple.
- Geschrieben wird nur, wenn sich der gerundete Durchschnitt geaendert hat oder
  der "Stand" aelter als 30 Tage ist (damit das Datum nicht veraltet und der
  geplante Job bei GitHub nicht mangels Aktivitaet abgeschaltet wird).
- Die Anzahl der Bewertungen wird bewusst NICHT angezeigt.
- Sicher im Fehlerfall: Antwort unbrauchbar, zu wenige Bewertungen oder eine
  Textstelle nicht genau so oft gefunden wie erwartet -> nichts schreiben.
"""
import datetime
import json
import math
import os
import re
import sys
import urllib.request

APP_ID = "6785243655"
LAENDER = ["de", "at", "ch", "us", "gb", "ca", "au", "nz", "ie", "nl", "be", "lu", "fr", "it", "es",
           "pt", "se", "no", "dk", "fi", "pl", "cz", "hu", "ro", "gr", "tr", "in", "jp", "kr", "sg",
           "br", "mx", "ae", "za"]
DATEI = "index.html"
MIN_BEWERTUNGEN = 5        # darunter ist der Schnitt zu wackelig – dann lieber nichts aendern
MAX_ALTER_TAGE = 30
MONATE_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ausgabe(schluessel, wert):
    pfad = os.environ.get("GITHUB_OUTPUT")
    if pfad:
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(f"{schluessel}={wert}\n")


def land_holen(land):
    url = f"https://itunes.apple.com/lookup?id={APP_ID}&country={land}"
    req = urllib.request.Request(url, headers={"User-Agent": "pushform-site-bewertung"})
    try:
        with urllib.request.urlopen(req, timeout=30) as antwort:
            daten = json.load(antwort)
    except (OSError, ValueError) as fehler:   # Netz, TLS, kaputtes JSON
        raise SystemExit(f"Apple nicht erreichbar ({land}: {fehler}) – nichts geaendert.")
    treffer = daten.get("results") or []
    if not treffer:                            # App in diesem Land nicht im Store
        return 0.0, 0
    r = treffer[0]
    return float(r.get("averageUserRating") or 0), int(r.get("userRatingCount") or 0)


def holen():
    """Gewichteter Schnitt ueber alle Laender. Faellt ein Land aus, wird abgebrochen,
    statt mit einem verzerrten Schnitt weiterzurechnen."""
    summe, anzahl = 0.0, 0
    for land in LAENDER:
        schnitt, n = land_holen(land)
        summe += schnitt * n
        anzahl += n
    if anzahl == 0:
        raise SystemExit("Keine Bewertungen gefunden – nichts geaendert.")
    return summe / anzahl, anzahl


def ersetzen(html, muster, neu, erwartet):
    gefunden = len(re.findall(muster, html))
    if gefunden != erwartet:
        raise SystemExit(f"Textstelle {muster!r}: {gefunden}x gefunden, erwartet {erwartet}x – nichts geaendert.")
    return re.sub(muster, neu, html)


def main():
    trocken = "--trocken" in sys.argv
    schnitt, anzahl = holen()
    if anzahl < MIN_BEWERTUNGEN:
        print(f"Nur {anzahl} Bewertungen – unveraendert gelassen.")
        ausgabe("changed", "false")
        return

    wert = f"{math.floor(schnitt * 10 + 1e-9) / 10:.1f}"   # 4.9 (abgerundet)
    wert_de = wert.replace(".", ",")            # 4,9
    fuellung = round(float(wert) / 5 * 100)     # 98 (Prozent des fuenften Sterns usw.)
    heute = datetime.date.today()

    html = open(DATEI, encoding="utf-8").read()
    alt = re.search(r'<strong>(\d,\d)</strong><span class="vh"> von 5 Sternen</span>', html)
    stand = re.search(r"Stand (\d{2})\.(\d{2})\.(\d{4})", html)
    if not alt or not stand:
        raise SystemExit("Bisherigen Wert oder Stand nicht gefunden – nichts geaendert.")
    alt_de = alt.group(1)
    stand_datum = datetime.date(int(stand.group(3)), int(stand.group(2)), int(stand.group(1)))
    alter = (heute - stand_datum).days

    print(f"Apple: {schnitt:.3f} aus {anzahl} -> {wert_de} (bisher {alt_de}, Stand {stand_datum}, {alter} Tage alt)")
    if wert_de == alt_de and alter < MAX_ALTER_TAGE:
        print("Keine Aenderung noetig.")
        ausgabe("changed", "false")
        return

    # Kopf: Badge + Bewertung (DE sichtbar, EN in data-en), genaue Sternfuellung
    html = ersetzen(html, r'<strong>\d,\d</strong><span class="vh"> von 5 Sternen</span>',
                    f'<strong>{wert_de}</strong><span class="vh"> von 5 Sternen</span>', 1)
    html = ersetzen(html, r'<strong>\d\.\d</strong><span class="vh"> out of 5 stars</span>',
                    f'<strong>{wert}</strong><span class="vh"> out of 5 stars</span>', 1)
    html = ersetzen(html, r"--fill:\d+%", f"--fill:{fuellung}%", 2)
    # Block "Was Nutzer sagen"
    html = ersetzen(html, r'<strong data-en="\d\.\d out of 5 stars">\d,\d von 5 Sternen</strong>',
                    f'<strong data-en="{wert} out of 5 stars">{wert_de} von 5 Sternen</strong>', 1)
    html = ersetzen(html, r"Stand \d{2}\.\d{2}\.\d{4}", f"Stand {heute:%d.%m.%Y}", 1)
    html = ersetzen(html, r"as of \d{1,2} [A-Z][a-z]{2} \d{4}",
                    f"as of {heute.day} {MONATE_EN[heute.month - 1]} {heute.year}", 1)

    zusammenfassung = f"{wert_de} (Stand {heute:%d.%m.%Y})"
    if trocken:
        print(f"Trockenlauf – wuerde schreiben: {zusammenfassung}")
        return
    open(DATEI, "w", encoding="utf-8").write(html)
    print(f"Geschrieben: {zusammenfassung}")
    ausgabe("changed", "true")
    ausgabe("summary", zusammenfassung)


if __name__ == "__main__":
    main()
