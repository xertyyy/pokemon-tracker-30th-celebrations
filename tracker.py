"""
Pokémon-Stock-Tracker für GitHub Actions (läuft in der Cloud, PC muss nicht an sein).
Prüft bei jedem Lauf alle Produkte einmal, merkt sich den Status in status.json
und schickt per ntfy eine Push-Nachricht, wenn etwas neu verfügbar wird
UND der Preis pro Booster-Pack unter dem Limit liegt.
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

NTFY_TOPIC = os.environ["NTFY_TOPIC"]   # kommt aus dem GitHub-Secret
MAX_PREIS_PRO_PACK = 7.00               # Standard-Limit in € pro Booster-Pack
PAUSE_SEKUNDEN = 2                      # Pause zwischen Shops (höflich bleiben)
STATUS_DATEI = Path("status.json")

# packs = Anzahl Booster im Produkt
# max_pro_pack (optional) = eigenes Limit für dieses Produkt, z. B. wegen Promokarten
# faktor (optional) = Umrechnung in € (z. B. Pfund), nur ungefähr
PRODUKTE = [
    # ---------- Boosterbundle (6 Packs) ----------
    {"name": "Bundle – Smyths DE", "packs": 6,
     "url": "https://www.smythstoys.com/de/de-de/spielzeug/action-spielzeug/pokemon/pokemon-figuren-und-sets/pokemon-30-jahre-boosterbundle/p/265602"},
    {"name": "Bundle – Card-Corner", "packs": 6,
     "url": "https://www.card-corner.de/Pokemon-30-Jahre-Booster-Bundle"},
    {"name": "Bundle – Comic Planet", "packs": 6,
     "url": "https://www.comicplanet.de/sammelkarten/pokemon/deutsch/displays-pkm/booster-pkm/pokemon-30-jahre-booster-bundle-deutsch"},
    {"name": "Bundle – VEDES", "packs": 6,
     "url": "https://www.vedes.com/p/pokemon-sammelkartenspiel-boosterbundle-30-jahre-14524-61219366"},
    {"name": "Bundle – SpielRaum AT", "packs": 6,
     "url": "https://www.spielraum.co.at/de/pokemon/product/30-jahre-30c-boosterbundle-de"},
    {"name": "Bundle EN – Chaos Cards UK (GBP)", "packs": 6, "faktor": 1.15,
     "url": "https://www.chaoscards.co.uk/prod/booster-packs-pokemon/pokemon-30th-celebration-booster-bundle"},
    {"name": "Bundle – MediaMarkt AT", "packs": 6,
     "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-30-jahre-boosterbundle-sammelkarten-2090542.html"},
    {"name": "Bundle – CrispyCards", "packs": 6,
     "url": "https://crispycards.de/products/pokemon-30-jahre-boosterbundle-de"},
    {"name": "Bundle – Kaufland (Marktplatz)", "packs": 6,
     "url": "https://www.kaufland.de/product/569964092/"},
    {"name": "Bundle EN – Smyths Irland", "packs": 6,
     "url": "https://www.smythstoys.com/ie/en-ie/toys/action-figures-and-playsets/pokemon/pokemon-trading-card-game/pokemon-trading-card-game-tcg-30th-celebration-booster-bundle/p/263935"},
    {"name": "Bundle EN – Fnac Portugal", "packs": 6,
     "url": "https://www.fnac.pt/Trading-Card-Game-Pokemon-30th-Celebration-Booster-Bundle-Pokemon-Jogos-de-Sociedade-Jogos-de-Cartas/a14660983"},

    # ---------- Top-Trainer-Box (9 Packs) ----------
    {"name": "Top-Trainer-Box – Smyths DE", "packs": 9,
     "url": "https://www.smythstoys.com/de/de-de/spielzeug/action-spielzeug/pokemon/pokemon-karten/pokemon-karten-top-trainer-box-30-jahre-edition/p/264148"},
    {"name": "Top-Trainer-Box – MediaMarkt AT", "packs": 9,
     "url": "https://www.mediamarkt.at/de/product/_pokemon-company-international-top-trainer-box-30-jahre-sammelkarten-2087300.html"},
    {"name": "Top-Trainer-Box – Toys for Fun", "packs": 9,
     "url": "https://www.toys-for-fun.com/de/pokemon-30-jahre-top-trainer-box.html"},
    {"name": "Top-Trainer-Box – Card-Corner", "packs": 9,
     "url": "https://www.card-corner.de/Pokemon-30-Jahre-Top-Trainer-Box"},
    {"name": "Top-Trainer-Box – Comic Planet", "packs": 9,
     "url": "https://www.comicplanet.de/sammelkarten/pokemon/deutsch/top-trainer-boxen-pkm/pokemon-30-jahre-top-trainer-box-deutsch"},
    {"name": "Top-Trainer-Box – CardCosmos", "packs": 9,
     "url": "https://cardcosmos.de/products/pokemon-30-jahre-top-trainer-box-deutsch"},
    {"name": "Top-Trainer-Box – SpielRaum AT", "packs": 9,
     "url": "https://www.spielraum.co.at/de/pokemon/product/30-jahre-top-trainer-box-de"},
    {"name": "Top-Trainer-Box – PushDich TCG", "packs": 9,
     "url": "https://www.pushdich-tcg.de/products/pokemon-30-jahre-top-trainer-box-deutsch"},
    {"name": "Top-Trainer-Box – Toy Treasure", "packs": 9,
     "url": "https://toy-treasure.com/products/pokemon-sammelkartenspiel-top-trainer-box-30-jahre-deutsch"},
    {"name": "Top-Trainer-Box – Racoon Cave", "packs": 9,
     "url": "https://racoon-rises.com/products/pkm-30-jahre-top-trainer-box-de"},
    {"name": "Top-Trainer-Box – Kaufland (Marktplatz)", "packs": 9,
     "url": "https://www.kaufland.de/product/568721940/"},
    {"name": "Top-Trainer-Box – Smyths Schweiz (CHF)", "packs": 9, "faktor": 1.07,
     "url": "https://www.smythstoys.com/ch/de-ch/spielzeug/action-spielzeug/pokemon/pokemon-karten/pokemon-karten-top-trainer-box-30-jahre-edition/p/264148"},

    # ---------- Tin-Box ex (4 Packs + Promo) ----------
    {"name": "Tin Quajutsu-ex – Smyths AT", "packs": 4,
     "url": "https://www.smythstoys.com/at/de-at/spielzeug/action-spielzeug/pokemon/pokemon-karten/pokemon-tin-box-mit-quajutsu-ex-30-jahre-edition/p/264164"},

    # ---------- Poster-Kollektion (3 Packs + 3 Promos) ----------
    {"name": "Poster-Kollektion – Smyths AT", "packs": 3, "max_pro_pack": 8.50,
     "url": "https://www.smythstoys.com/at/de-at/spielzeug/action-spielzeug/pokemon/pokemon-karten/pokemon-poster-kollektion-30-jahre-edition/p/264190"},

    # ---------- 2er-Blister (2 Packs + Promo + Münze) ----------
    {"name": "Blister DE – Comic Planet", "packs": 2,
     "url": "https://www.comicplanet.de/sammelkarten/pokemon/deutsch/specials-pkm/pokemon-30-jahre-2-pack-blister-deutsch"},
    {"name": "Blister DE – Nanis Kinderparadies", "packs": 2,
     "url": "https://www.nanis-kinderparadies.de/shop/spielwelten/sammelkarten/19839/pokemon-30-jahre-2-pack-blister"},
    {"name": "Blister EN – Card-Corner", "packs": 2,
     "url": "https://www.card-corner.de/Pokemon-30th-Celebration-2-Pack-Blister"},

    # ---------- Mini-Tin (2 Packs) ----------
    {"name": "Mini-Tin DE – KEEPSEVEN", "packs": 2,
     "url": "https://keepseven.de/product/pokemon-30-jahre-mini-tin-de-zufaellig/"},
    {"name": "Mini-Tin DE – Spiele-Riese", "packs": 2,
     "url": "https://www.spiele-riese.de/shop/spielwelten/sammelkarten/19852/pokemon-30-jahre-mini-tin"},
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}


def finde_produkte(obj):
    """Sammelt rekursiv alle schema.org-Objekte vom Typ 'Product'."""
    gefunden = []
    if isinstance(obj, dict):
        typ = obj.get("@type", "")
        typen = typ if isinstance(typ, list) else [typ]
        if any("Product" in str(t) for t in typen):
            gefunden.append(obj)
        for v in obj.values():
            gefunden += finde_produkte(v)
    elif isinstance(obj, list):
        for v in obj:
            gefunden += finde_produkte(v)
    return gefunden


def lies_status(html):
    """
    Liest Verfügbarkeit und Preis NUR aus den offiziellen Produktdaten (schema.org, Typ Product).
    Rückgabe: (verfuegbar, preis, quelle)
    Ein "In den Warenkorb"-Text auf der Seite reicht NICHT, weil er oft zu anderen
    empfohlenen Produkten gehört (Fehlalarm-Gefahr).
    """
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            daten = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for produkt in finde_produkte(daten):
            offers = produkt.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else None
            if not isinstance(offers, dict):
                continue
            avail = str(offers.get("availability", "")).lower()
            verfuegbar = avail.endswith("instock")   # "outofstock", "preorder" usw. zählen nicht
            try:
                preis = float(str(offers.get("price") or offers.get("lowPrice")).replace(",", "."))
            except (TypeError, ValueError):
                preis = None
            return verfuegbar, preis, "Produktdaten"
    return False, None, "keine Produktdaten – wird nie gemeldet"


def push(titel, text, url):
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=text.encode("utf-8"),
        headers={"Title": titel.encode("utf-8"), "Click": url, "Priority": "high", "Tags": "zap"},
        timeout=10,
    )


def euro(betrag):
    return f"{betrag:.2f} €".replace(".", ",")


def main():
    status = json.loads(STATUS_DATEI.read_text()) if STATUS_DATEI.exists() else {}
    zeit = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    for p in PRODUKTE:
        try:
            r = requests.get(p["url"], headers=HEADERS, timeout=20)
            verfuegbar, preis, quelle = lies_status(r.text)
            print(f"  HTTP {r.status_code}, {len(r.text)} Zeichen, Quelle: {quelle}")
        except requests.RequestException as fehler:
            print(f"[{zeit}] {p['name']}: Fehler – {fehler}")
            continue

        if preis is not None:
            preis = preis * p.get("faktor", 1.0)
            pro_pack = preis / p["packs"]
            preis_txt = f"{euro(preis)} = {euro(pro_pack)}/Pack"
        else:
            pro_pack = None
            preis_txt = "Preis unbekannt"

        print(f"[{zeit}] {p['name']}: {'VERFÜGBAR' if verfuegbar else 'nicht verfügbar'} ({preis_txt})")

        limit = p.get("max_pro_pack", MAX_PREIS_PRO_PACK)
        preis_ok = pro_pack is None or pro_pack <= limit
        if verfuegbar and preis_ok and not status.get(p["url"], False):
            push(f"Auf Lager: {p['name']}", f"{preis_txt} – jetzt kaufen!", p["url"])
        status[p["url"]] = bool(verfuegbar)

        time.sleep(PAUSE_SEKUNDEN)

    STATUS_DATEI.write_text(json.dumps(status, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
