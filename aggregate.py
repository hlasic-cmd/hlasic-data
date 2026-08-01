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
    "https://www.pluska.sk/rss.xml",      # alternatívna adresa, ak vyššia nefunguje
    "https://www.topky.sk/rss.xml",       # najrýchlejší bulvárny zdroj na SK, adresa neoverená
    "https://sita.sk/spravy/feed/",
    "http://www.aktuality.sk/rss/?path=/discover/topic/top-news/slovakia",
    "https://tnlive.sk/feed",             # skúšame WordPress konvenciu namiesto /rss
    # TASR (teraz.sk): vyžaduje registráciu na https://www.teraz.sk/rss.
    # Po schválení sem doplň svoju adresu — TASR je zvyčajne najrýchlejší
    # zdroj na Slovensku a stojí za tú jednu registráciu.
]

METEOALARM_FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovakia"

CATEGORY_KEYWORDS = {
    "nehoda": ["nehod", "zrážk", "zrazk", "havári", "havari", "kolízi", "kolizi"],
    "poziar": ["požiar", "poziar", "vypukol oheň", "vypukol ohen", "zhorel", "vyhorel", "vyhorela", "plamene zachvátili", "plamene zachvatili", "hasiči zasahujú pri požiari", "horí les", "hori les", "horí dom", "hori dom"],
    "zasah": ["zásah hasič", "zasah hasic", "záchranári zasahovali", "zachranari zasahovali", "vrtuľník", "vrtulnik", "evakuo"],
    "patranie": ["pátra polícia", "patra policia", "nezvestn", "hľadá polícia", "hlada policia", "pohreš", "pohres"],
    "burka": ["búrka", "burka", "búrky", "burky", "výstraha pred", "vystraha pred", "prívalov", "privalov", "krupobiti", "veterná smršť", "veterna smrst", "víchric", "vichric", "povoden", "povodeň", "zosuv pôdy", "zosuv pody"],
}

# Slová, ktoré ak sú v článku, článok sa zahodí aj keď zasiahlo kľúčové slovo vyššie
# (typicky historické/cestopisné/výročné články, nie aktuálne udalosti)
EXCLUDE_HINTS = ["pred rokmi", "pred storočím", "pred storocim", "v minulosti", "história mesta", "historia mesta", "výročie", "vyrocie"]

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


import calendar

def parse_time(entry):
    # feedparser si sám normalizuje dátumy (RFC822 aj ISO8601/Atom) do struct_time v UTC
    for field in ("published_parsed", "updated_parsed"):
        struct = entry.get(field)
        if struct:
            try:
                return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc)
            except Exception:
                pass
    # záložný pokus pre prípady, čo feedparser nezvládol automaticky
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
    if any(h in text_l for h in EXCLUDE_HINTS):
        return None
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


def fetch_feed(url, fixed_region=None, force_category=None, skip_age_filter=False):
    items = []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"  [CHYBA] {url}: {e}")
        return items

    total_entries = len(parsed.entries)
    no_date = 0
    too_old = 0

    now = datetime.now(timezone.utc)
    for entry in parsed.entries:
        pub = parse_time(entry)
        if pub is None:
            no_date += 1
            continue
        age_hours = (now - pub).total_seconds() / 3600
        if not skip_age_filter and age_hours > MAX_AGE_HOURS:
            too_old += 1
            continue

        title = entry.get("title", "").strip()
        summary = entry.get("description", "") or entry.get("summary", "")
        combined = f"{title} {summary}"

        cat = force_category or guess_category(combined)
        if cat is None:
            continue

        region = fixed_region or guess_region(combined)

        items.append({
            "title": title,
            "link": entry.get("link", ""),
            "time": pub.isoformat(),
            "cat": cat,
            "region": region,
            "src": url.split("/")[2].replace("www.", ""),
        })

    print(f"    (spolu v feede: {total_entries}, bez dátumu: {no_date}, staršie ako {MAX_AGE_HOURS}h: {too_old}, relevantné: {len(items)})")
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
    meteo_all = fetch_feed(METEOALARM_FEED, fixed_region=None, force_category="burka", skip_age_filter=True)
    print(f"MeteoAlarm: {len(meteo_all)} výstrah nájdených (zatiaľ sa do appky nezahŕňajú — príliš veľa šumu/v angličtine, appka rieši aktuálne počasie priamo cez Open-Meteo v appke)")
    # all_items.extend(meteo) -- zámerne vypnuté, pozri komentár vyššie

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
