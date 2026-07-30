# Hlásič — backend agregátor (zadarmo, bez vlastného servera)

Tento balík stiahne každých 5 minút desiatky slovenských spravodajských
RSS zdrojov (8 krajských portálov siete Mediak + celoslovenské denníky),
ponechá len články mladšie ako pár hodín, odhadne kategóriu a kraj,
a publikuje výsledok ako verejný `output.json`, ktorý appka Hlásič
načítava naživo.

Beží to celé na GitHub Actions — zadarmo, bez kreditky, bez správy
vlastného servera.

## Krok za krokom (bez programovania)

1. **Vytvor si GitHub účet** na github.com, ak ho ešeš nemáš (zadarmo).
2. **Vytvor nový repozitár** (New repository) — nastav ho ako Public,
   pomenuj ho napr. `hlasic-data`.
3. **Nahraj tam tieto súbory** presne v tejto štruktúre (cez "Add file"
   → "Upload files" v GitHub webe, netreba príkazový riadok):
   ```
   aggregate.py
   requirements.txt
   .github/workflows/update.yml
   ```
4. **Zapni GitHub Pages**: choď do Settings → Pages → pod "Build and
   deployment" vyber zdroj "Deploy from a branch" → vetva `gh-pages`
   → priečinok `/ (root)` → Save.
   (Vetva `gh-pages` sa objaví sama po prvom behu workflow, čiže tento
   krok spravíš až po kroku 5.)
5. **Spusti workflow prvý raz ručne**: záložka "Actions" v repozitári
   → "Aktualizuj spravodajský feed" → "Run workflow". Počkaj minútu,
   kým dobehne (zelená fajočka).
6. Po dobehnutí sa objaví tvoja verejná adresa dát, zvyčajne v tvare:
   ```
   https://TVOJE-MENO.github.io/hlasic-data/output.json
   ```
   Nájdeš presnú adresu v Settings → Pages, hore je odkaz "Your site
   is live at ...".
7. **Túto adresu vlož do appky Hlásič** (do premennej `DATA_FEED_URL`
   na začiatku `<script>` časti v `hlasic-prototype.html`) namiesto
   pevných ukážkových dát.

Odteraz sa `output.json` sám aktualizuje každých 5 minút, navždy,
zadarmo — appka bude vždy ukazovať čerstvé dáta.

## Čo ak niektorý z 8 krajských zdrojov nemá presne `/rss`

Overil som naživo len `trencinak.sk/rss`. Ostatné (bratislavak.sk,
zilinak.sk, nitrak.sk, trnavak.sk, bystricak.sk, presovak.sk,
kosicak.sk) bežia na tej istej platforme, takže je vysoká šanca, že
majú rovnaký formát — ale skript má ošetrené, že ak niektorý zdroj
zlyhá, len ho preskočí a pokračuje ďalej (nespadne celý). Ak sa
ukáže, že niektorá adresa je iná, over si ju rovnako ako sme to
robili s trencinak.sk — otvor `https://www.[nazov].sk/` v prehliadači
a pozri si pätičku stránky, kde je zvyčajne priamy odkaz na RSS.

## Nastavenie čerstvosti

`MAX_AGE_HOURS` v `aggregate.py` (default 4) určuje, aké staré články
sa ešte zobrazia. Ak chceš appku ešte "prísnejšiu" na čerstvosť, znížiš
toto číslo na napr. 2.
