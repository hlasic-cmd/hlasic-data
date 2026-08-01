#!/usr/bin/env python3
"""
Hlásič — agregátor spravodajstva.

Stiahne slovenské RSS zdroje (regionálne + celoslovenské), ponechá LEN
čerstvé články (podľa MAX_AGE_HOURS) a LEN tie, čo sa dajú zaradiť do
bezpečnostných kategórií (nehoda/požiar/zásah/pátranie/búrka) — všetko
ostatné (kultúra, ekonomika, politika, šport, zahraničie) sa zahodí už
tu, nie až v appke. Výstup: output.json s počtami za každý zdroj kvôli
ladeniu.

pip install requests feedparser python-dateutil --break-system-packages
python3 aggregate.py
"""

import json
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
import requests

# ---------------- NASTAVENIA ----------------

MAX_AGE_HOURS = 6  # o niečo širšie okno, aby appka nebola prázdna mimo špičky

REGIONAL_FEEDS = {
    "bratislavsky":     "https://www.bratislavak.sk/rss",
    "trnavsky":         "https://www.trnavak.sk/rss",
    "trenciansky":      "https://www.trencinak.sk/rss",
    "nitriansky":       "https://www.nitrak.sk/rss",
    "zilinsky":         "https://www.zilinak.sk/rss",
    "banskobystricky":  "https://www.bystricak.sk/rss",
    "presovsky":        "https://www.presovak.sk/rss",
    "kosicky":          "https://www.kosicak.sk/rss",
}

NATIONAL_FEEDS = [
    "https://dennikn.sk/feed",
    "https://spravy.pravda.sk/domace/rss/xml",
    "https://korzar.sme.sk/rss",
    "https://www1.pluska.sk/rss.xml",
    "https://sita.sk/spravy/feed/",
    "http://www.aktuality.sk/rss/?path=/discover/topic/top-news/slovakia",
    "https://tnlive.sk/rss",  # TV Noviny Markíza
    # TASR (teraz.sk): vyžaduje registráciu na https://www.teraz.sk/rss.
    # Po schválení sem doplň svoju adresu — TASR je zvyčajne najrýchlejší
    # zdroj na Slovensku a stojí za tú jednu registráciu.
]

METEOALARM_FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovakia"

CATEGORY_KEYWORDS = {
    "nehoda": ["nehod", "zrážk", "zrazk", "havári", "havari", "kolízi", "kolizi"],
    "poziar": ["požiar", "poziar", "horí", "hori", "zhorel", "vyhorel", "vyhorela", "plameň", "plamen"],
    "zasah": ["zásah", "zasah", "záchran", "zachran", "hasič", "hasic", "vrtuľník", "vrtulnik", "evakuo"],
    "patranie": ["pátra", "patra", "nezvestn", "hľadá polícia", "hlada policia", "pohreš", "pohres"],
    "burka": ["búrk", "burk", "výstraha", "vystraha", "prívalov", "privalov", "krupobiti", "veterná", "vetern", "povoden", "povodeň", "zosuv"],
}

REGION_HINTS = {
    "bratislavsky": ["bratislav", "malacky", "pezinok", "senec"],
    "trnavsky": ["trnav", "piešťan", "piestan", "hlohov", "senic", "skalic", "galant"],
    "trenciansky": ["trenčín", "trencin", "púchov", "puchov", "prievidz", "myjav", "bánovce", "banovce", "dubnic", "nemšov", "nemsov"],
    "nitriansky": ["nitr", "komárno", "komarno", "levic", "nové zámky", "nove zamky", "topoľčan", "topolcan"],
    "zilinsky": ["žilin", "zilin", "martin", "čadc", "cadc", "liptovsk", "kysuck", "ružomberok", "ruzomberok"],
    "banskobystricky": ["banská bystric", "banska bystric", "zvolen", "lučenec", "lucenec", "rimavsk", "brezn", "žiar", "ziar"],
    "presovsky": ["prešov", "presov", "poprad", "humenn", "bardejov", "stará ľubovňa", "stara lubovna", "svidník", "svidnik"],
    "kosicky": ["košic", "kosic", "michalovce", "trebišov", "trebisov", "spišsk", "spissk", "rožňav", "roznav"],
}


def parse_time(entry):
    for field in ("published", "updated"):
        raw = entry.get(field)
        if not raw:
            continue
        try:
            return parsedate_to_datetime(raw).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def guess_category(text):
    text_l = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in text_l for kw in kws):
            return cat
    return None  # None = nepatrí do bezpečnostných kategórií -> zahodí sa


def guess_region(text):
    text_l = text.lower()
    for region, hints in REGION_HINTS.items():
        if any(h in text_l for h in hints):
            return region
    return None


def fetch_feed(url, fixed_region=None, force_category=None):
    items = []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"  [CHYBA] {url}: {e}")
        return items

    now = datetime.now(timezone.utc)
    for entry in parsed.entries:
        pub = parse_time(entry)
        if pub is None:
            continue
        age_hours = (now - pub).total_seconds() / 3600
        if age_hours > MAX_AGE_HOURS:
            continue

        title = entry.get("title", "").strip()
        summary = entry.get("description", "") or entry.get("summary", "")
        combined = f"{title} {summary}"

        cat = force_category or guess_category(combined)
        if cat is None:
            continue  # mimo bezpečnostných kategórií -> zahodíme priamo tu

        region = fixed_region or guess_region(combined)

        items.append({
            "title": title,
            "link": entry.get("link", ""),
            "time": pub.isoformat(),
            "cat": cat,
            "region": region,
            "src": url.split("/")[2].replace("www.", ""),
        })
    return items


def main():
    all_items = []

    print("--- Regionálne zdroje ---")
    for region, url in REGIONAL_FEEDS.items():
        found = fetch_feed(url, fixed_region=region)
        print(f"{region}: {len(found)} relevantných článkov")
        all_items.extend(found)
        time.sleep(0.3)

    print("--- Celoslovenské zdroje ---")
    for url in NATIONAL_FEEDS:
        found = fetch_feed(url, fixed_region=None)
        print(f"{url}: {len(found)} relevantných článkov")
        all_items.extend(found)
        time.sleep(0.3)

    print("--- MeteoAlarm ---")
    meteo = fetch_feed(METEOALARM_FEED, fixed_region=None, force_category="burka")
    print(f"MeteoAlarm: {len(meteo)} výstrah")
    all_items.extend(meteo)

    seen = set()
    deduped = []
    for item in all_items:
        if item["link"] in seen:
            continue
        seen.add(item["link"])
        deduped.append(item)

    deduped.sort(key=lambda i: i["time"], reverse=True)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_age_hours": MAX_AGE_HOURS,
        "count": len(deduped),
        "items": deduped,
    }

    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nHotovo: {len(deduped)} relevantných čerstvých článkov (< {MAX_AGE_HOURS} h) -> output.json")


if __name__ == "__main__":
    main()
