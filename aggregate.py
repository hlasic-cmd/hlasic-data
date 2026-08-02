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

MAX_AGE_HOURS = 12  # širšie okno — krajské portály majú málo článkov, potrebujeme viac objemu na kraj

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
    "https://sita.sk/rss/clanky-img/1/",  # SITA legacy odkaz (nový /spravy/feed/ vyžaduje registráciu)
    "http://www.aktuality.sk/rss/?path=/discover/topic/top-news/slovakia",
    "https://tnlive.sk/feed",             # skúšame WordPress konvenciu namiesto /rss
    "https://www.teraz.sk/rss/slovensko.rss",   # TASR — Slovensko
    "https://www.teraz.sk/rss/regiony.rss",     # TASR — Regióny
]

METEOALARM_FEED = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-slovakia"

CATEGORY_KEYWORDS = {
    "burka": ["búrka", "burka", "búrky", "burky", "výstraha pred", "vystraha pred", "prívalov", "privalov", "krupobiti", "veterná smršť", "veterna smrst", "víchric", "vichric", "povoden", "povodeň", "zosuv pôdy", "zosuv pody"],
    "nehoda": ["dopravná nehod", "dopravna nehod", "zrážka vozid", "zrazka vozid", "zrážka áut", "zrazka aut", "zrážka s autom", "zrazka s autom", "havári", "havari", "kolízi", "kolizi", "nehod"],
    "poziar": ["požiar", "poziar", "vypukol oheň", "vypukol ohen", "zhorel", "vyhorel", "vyhorela", "plamene zachvátili", "plamene zachvatili", "hasiči zasahujú pri požiari", "horí les", "hori les", "horí dom", "hori dom"],
    "zasah": ["zásah hasič", "zasah hasic", "záchranári zasahovali", "zachranari zasahovali", "vrtuľník", "vrtulnik", "evakuo"],
    "patranie": ["pátra polícia", "patra policia", "nezvestn", "hľadá polícia", "hlada policia", "pohreš", "pohres"],
}

# Slová, ktoré ak sú v článku, článok sa zahodí aj keď zasiahlo kľúčové slovo vyššie
# (typicky historické/cestopisné/výročné články, nie aktuálne udalosti)
EXCLUDE_HINTS = [
    "pred rokmi", "pred storočím", "pred storocim", "v minulosti", "história mesta", "historia mesta", "výročie", "vyrocie",
    # zjavne zahraničné udalosti bez súvisu so Slovenskom (nedokonalý zoznam, dopĺňať priebežne)
    "neapol", "taliansk", "chorvátsk", "chorvatsk", "srbsk", "rakúsk", "rakusk", "maďarsk", "madarsk",
    "nemeck", "poľsk", "polsk", "ukrajin", "rusk", "franc", "španielsk", "spanielsk",
]

REGION_HINTS = {
    "bratislavsky": [
        "bratislav", "malack", "pezinok", "senec", "stupav", "svätý jur", "svaty jur", "modra",
    ],
    "trnavsky": [
        "trnav", "dunajská streda", "dunajska streda", "galant", "hlohov", "piešťan", "piestan",
        "senic", "skalic", "šamorín", "samorin", "šaštín", "sastin", "sereď", "sered",
        "sládkovičov", "sladkovicov", "gbely", "holíč", "holic", "veľký meder", "velky meder", "vrbové", "vrbove",
    ],
    "trenciansky": [
        "trenčín", "trencin", "bánovce nad bebravou", "banovce nad bebravou", "ilava", "myjav",
        "nové mesto nad váhom", "nove mesto nad vahom", "partizánsk", "partizansk",
        "považská bystrica", "povazska bystrica", "prievidz", "púchov", "puchov",
        "nemšov", "nemsov", "dubnic", "handlov", "nová dubnica", "nova dubnica", "nováky", "novaky",
        "bojnice", "brezová pod bradlom", "brezova pod bradlom", "stará turá", "stara tura",
        "trenčianske teplice", "trencianske teplice",
    ],
    "nitriansky": [
        "nitr", "komárn", "komarn", "levic", "nové zámky", "nove zamky", "šaľ", "sal",
        "topoľčan", "topolcan", "zlaté moravce", "zlate moravce", "hurbanovo", "kolárov", "kolarov",
        "šahy", "sahy", "štúrov", "sturov", "šuran", "suran", "tlmač", "tlmac", "vráble", "vrable",
        "želiezovce", "zeliezovce",
    ],
    "zilinsky": [
        "žilin", "zilin", "bytč", "bytc", "čadc", "cadc", "dolný kubín", "dolny kubin",
        "kysucké nové mesto", "kysucke nove mesto", "liptovský mikuláš", "liptovsky mikulas",
        "martin", "námestov", "namestov", "ružomberok", "ruzomberok", "turčianske teplice", "turcianske teplice",
        "tvrdošín", "tvrdosin", "rajec", "krásno nad kysucou", "krasno nad kysucou",
        "liptovský hrádok", "liptovsky hradok", "trstená", "trstena", "vrútky", "vrutky",
    ],
    "banskobystricky": [
        "banská bystric", "banska bystric", "banská štiavnica", "banska stiavnica", "brezn",
        "detv", "krupin", "lučenec", "lucenec", "poltár", "poltar", "revúc", "revuc",
        "rimavsk", "veľký krtíš", "velky krtis", "zvolen", "žarnovic", "zarnovic",
        "žiar nad hronom", "ziar nad hronom", "dudince", "fiľakov", "filakov", "hnúšť", "hnust",
        "hriňov", "hrinov", "jelšav", "jelsav", "kremnic", "modrý kameň", "modry kamen",
        "nová baňa", "nova bana", "sliač", "sliac", "tisovec", "tornaľ", "tornal",
    ],
    "presovsky": [
        "prešov", "presov", "bardejov", "humenn", "kežmarok", "kezmarok", "levoč", "levoc",
        "medzilaborce", "poprad", "sabinov", "snina", "stará ľubovňa", "stara lubovna",
        "stropkov", "svidník", "svidnik", "vranov nad topľou", "vranov nad toplou",
        "giraltovce", "hanušovce", "hanusovce", "lipany", "podolínec", "podolinec",
        "spišská belá", "spisska bela", "spišská stará ves", "spisska stara ves",
        "spišské podhradie", "spisske podhradie", "svit", "veľký šariš", "velky saris",
        "vysoké tatry", "vysoke tatry",
    ],
    "kosicky": [
        "košic", "kosic", "gelnic", "michalovce", "rožňav", "roznav", "sobranc",
        "spišská nová ves", "spisska nova ves", "trebišov", "trebisov", "čierna nad tisou", "cierna nad tisou",
        "dobšin", "dobsin", "kráľovský chlmec", "kralovsky chlmec", "krompach", "medzev",
        "moldava nad bodvou", "sečovce", "secovce", "spišské vlachy", "spisske vlachy", "strážske", "strazske",
        "veľké kapušany", "velke kapusany",
    ],
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


def fetch_feed(url, fixed_region=None, force_category=None, skip_age_filter=False, assume_slovak=False):
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

        # Regionálne portály (mediak sieť) sú vždy o Slovensku. Celoslovenské
        # zdroje ale môžu obsahovať aj zahraničné správy (cestopisy, zemetrasenia
        # v zahraničí a pod.) — namiesto vymenovávania cudzích krajín vyžadujeme
        # POZITÍVNY slovenský signál: buď sme uhádli konkrétny kraj, alebo text
        # priamo spomína Slovensko.
        if fixed_region is None and force_category is None and not assume_slovak:
            if region is None:
                continue  # bez rozpoznaného konkrétneho slovenského miesta/kraja -> zahodíme

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
    TRUSTED_SLOVAK_FEEDS = {"https://www.teraz.sk/rss/slovensko.rss"}
    for url in NATIONAL_FEEDS:
        found = fetch_feed(url, fixed_region=None, assume_slovak=(url in TRUSTED_SLOVAK_FEEDS))
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
