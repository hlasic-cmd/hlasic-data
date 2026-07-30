#!/usr/bin/env python3
"""
Hlásič — agregátor spravodajstva.

Stiahne desiatky slovenských RSS zdrojov (regionálne + celoslovenské),
ponechá LEN čerstvé články (podľa MAX_AGE_HOURS), odhadne kategóriu
(nehoda/požiar/zásah/pátranie/búrka) podľa kľúčových slov a uloží
všetko do jedného output.json, ktorý appka číta.

Skript je bez štátu (stateless) — pri každom behu znovu prejde feedy
a vygeneruje čerstvý output.json. Spúšťaj ho každých pár minút
(cez cron, alebo cez GitHub Actions — návod v README.md).

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

MAX_AGE_HOURS = 4  # články staršie ako toto sa do výstupu vôbec nedostanú

# Regionálne zdroje — sieť Mediak, jeden portál na kraj, rovnaká platforma
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

# Celoslovenské zdroje — nemajú jednoznačný kraj, idú do "celeSK"
# (región sa priradí len ak sa v texte nájde názov mesta/kraja)
NATIONAL_FEEDS = [
    "https://dennikn.sk/feed",
    "https://spravy.pravda.sk/domace/rss/xml",
    "https://korzar.sme.sk/rss",
    "https://www1.pluska.sk/rss.xml",
    "https://sita.sk/spravy/feed/",                 # tlačová agentúra SITA — otvorené RSS, netreba registráciu
    "http://www.aktuality.sk/rss/?path=/discover/topic/top-news/slovakia",  # najčítanejší spravodajský portál na SK
    # TASR (teraz.sk) má RSS, ale vyžaduje si najprv registráciu a súhlas
    # s podmienkami na https://www.teraz.sk/rss — over si to a prípadne
    # sem doplň svoju schválenú adresu, TASR je zvyčajne najrýchlejší zdroj na SK.
]

# Oficiálny európsky systém včasného varovania (EUMETNET) — agreguje aj
# výstrahy SHMÚ pre Slovensko. Toto je pre kategóriu "búrky" najlepší
# zdroj: štátna/oficiálna inštitúcia, nie médium, takže žiadne obmedzenia
# na použitie a spravidla veľmi rýchle vydávanie výstrah.
METEOALARM_FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovakia"

ALL_FEEDS = {**{k: v for k, v in REGIONAL_FEEDS.items()}, "celeSK": None}

CATEGORY_KEYWORDS = {
    "nehoda": ["nehod", "zrážk", "zrazk", "havári", "havari", "kolízi", "kolizi"],
    "poziar": ["požiar", "poziar", "horí", "hori", "zhorel", "vyhorel"],
    "zasah": ["zásah", "zasah", "záchran", "zachran", "hasič", "hasic", "vrtuľník", "vrtulnik"],
    "patranie": ["pátra", "patra", "nezvestn", "hľadá polícia", "hlada policia"],
    "burka": ["búrk", "burk", "výstraha", "vystraha", "prívalov", "privalov", "krupobiti", "veterná", "vetern"],
}

# Približné priradenie mesta/kraja pre celoslovenské zdroje bez vlastného regiónu
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
    return "ine"


def guess_region(text):
    text_l = text.lower()
    for region, hints in REGION_HINTS.items():
        if any(h in text_l for h in hints):
            return region
    return None


def fetch_feed(url, fixed_region=None):
    items = []
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        parsed = feedparser.parse(resp.content)
    except Exception as e:
        print(f"[CHYBA] {url}: {e}")
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

        region = fixed_region or guess_region(combined)

        items.append({
            "title": title,
            "link": entry.get("link", ""),
            "time": pub.isoformat(),
            "cat": guess_category(combined),
            "region": region,
            "src": url.split("/")[2].replace("www.", ""),
        })
    return items


def fetch_meteoalarm():
    """MeteoAlarm dáva oficiálne výstrahy — vždy ich taguj ako kategóriu 'burka'."""
    items = fetch_feed(METEOALARM_FEED, fixed_region=None)
    for item in items:
        item["cat"] = "burka"
        if not item["region"]:
            item["region"] = guess_region(item["title"])
    return items


def main():
    all_items = []

    for region, url in REGIONAL_FEEDS.items():
        print(f"Sťahujem {region}: {url}")
        all_items.extend(fetch_feed(url, fixed_region=region))
        time.sleep(0.3)

    for url in NATIONAL_FEEDS:
        print(f"Sťahujem celoslovenský zdroj: {url}")
        all_items.extend(fetch_feed(url, fixed_region=None))
        time.sleep(0.3)

    print("Sťahujem MeteoAlarm výstrahy...")
    all_items.extend(fetch_meteoalarm())

    # dedup podľa linku
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

    print(f"\nHotovo: {len(deduped)} čerstvých článkov (< {MAX_AGE_HOURS} h) -> output.json")


if __name__ == "__main__":
    main()
