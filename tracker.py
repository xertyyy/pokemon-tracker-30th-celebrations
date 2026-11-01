"""
Pokémon-Stock-Tracker für GitHub Actions (läuft in der Cloud, PC muss nicht an sein).
Prüft bei jedem Lauf alle Produkte einmal, merkt sich den Status in status.json
und schickt per ntfy eine Push-Nachricht, wenn etwas neu verfügbar wird.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

NTFY_TOPIC = os.environ["NTFY_TOPIC"]      # kommt aus dem GitHub-Secret
MAX_PREIS = 35.00                          # nur melden, wenn Preis <= diesem Wert (None = immer)
STATUS_DATEI = Path("status.json")

PRODUKTE = [
    {
        "name": "Boosterbundle 30 Jahre – Smyths",
        "url": "https://www.smythstoys.com/de/de-de/spielzeug/action-spielzeug/pokemon/pokemon-figuren-und-sets/pokemon-30-jahre-boosterbundle/p/265602",
    },
    {
        "name": "Boosterbundle 30 Jahre – Card-Corner",
        "url": "https://www.card-corner.de/Pokemon-30-Jahre-Booster-Bundle",
    },
]

HEADERS = {"User-Agent": "Mozilla/5.0 (privater Stock-Tracker)"}


def lies_status(html):
    """Liest Verfügbarkeit und Preis aus den strukturierten Produktdaten (schema.org)."""
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            daten = json.loads(block)
        except json.JSONDecodeError:
            continue
        for e in (daten if isinstance(daten, list) else [daten]):
            offers = e.get("offers") if isinstance(e, dict) else None
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if isinstance(offers, dict):
                verfuegbar = "InStock" in str(offers.get("availability", ""))
                try:
                    preis = float(offers.get("price") or offers.get("lowPrice"))
                except (TypeError, ValueError):
                    preis = None
                return verfuegbar, preis
    text = html.lower()
    if "ausverkauft" in text or "nicht verfügbar" in text or "out of stock" in text:
        return False, None
    if "in den warenkorb" in text:
        return True, None
    return False, None


def push(titel, text, url):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=text.encode("utf-8"),
        headers={"Title": titel.encode("utf-8"), "Click": url, "Priority": "high", "Tags": "zap"},
        timeout=10,
    )


def main():
    status = json.loads(STATUS_DATEI.read_text()) if STATUS_DATEI.exists() else {}
    zeit = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    for p in PRODUKTE:
        try:
            r = requests.get(p["url"], headers=HEADERS, timeout=20)
            verfuegbar, preis = lies_status(r.text)
        except requests.RequestException as fehler:
            print(f"[{zeit}] {p['name']}: Fehler – {fehler}")
            continue

        preis_txt = f"{preis:.2f} €".replace(".", ",") if preis else "Preis unbekannt"
        print(f"[{zeit}] {p['name']}: {'VERFÜGBAR' if verfuegbar else 'nicht verfügbar'} ({preis_txt})")

        preis_ok = MAX_PREIS is None or preis is None or preis <= MAX_PREIS
        if verfuegbar and preis_ok and not status.get(p["url"], False):
            push(f"Auf Lager: {p['name']}", f"{preis_txt} – jetzt kaufen!", p["url"])
        status[p["url"]] = bool(verfuegbar)

    STATUS_DATEI.write_text(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
