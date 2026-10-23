#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma cine/Archivos/primicias.json: la lista "Primicias H en español" del Home privado, ya lista para que la app
solo la descargue (una petición) en vez de buscar en muchohentai.com desde el celular.

Es un calco de MuchoHentaiSearcher.searchEspanol() de la app (mismas búsquedas, misma fusión Raw/Eng/Es por
episodio, mismos PV, misma consolidación de nombres, mismos ids "mh_..."), para que favoritos e historial sigan
reconociendo las mismas series.

Uso:  python scripts/build_primicias.py            (lo corre GitHub Actions cada hora)
      python scripts/build_primicias.py --paginas 10 --salida cine/Archivos/primicias.json
"""
import argparse
import json
import re
import struct
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote_plus

import requests

BASE = "https://muchohentai.com"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Referer": BASE + "/",
    "Origin": BASE,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
}
PARALELO = 6          # peticiones a la vez contra el sitio (más de ~8 y Cloudflare se pone nervioso)
TIMEOUT = 30
MIN_SERIES = 5        # si salen menos, algo falló: NO se pisa el JSON que ya existe

RAW, ENG, ES, PV = "RAW", "ENG", "ES", "PV"

session = requests.Session()
session.headers.update(HEADERS)
_page_cache = {}


# ── HTTP ────────────────────────────────────────────────────────────────────────

def http_get(url, referer=None):
    """GET con 2 intentos. Devuelve el HTML o None."""
    headers = {"Referer": referer} if referer else None
    for intento in range(2):
        try:
            r = session.get(url, headers=headers, timeout=TIMEOUT)
            if r.status_code in (429, 503):
                print(f"  HTTP {r.status_code} en {url} (intento {intento + 1})", file=sys.stderr)
                time.sleep(3 + 3 * intento)
                continue
            if r.status_code != 200:
                print(f"  HTTP {r.status_code} en {url}", file=sys.stderr)
                return None
            if "Just a moment" in r.text[:2000] and "cf-" in r.text[:5000]:
                print(f"  Cloudflare pide verificación en {url}", file=sys.stderr)
                return None
            return r.text
        except requests.RequestException as e:
            print(f"  GET falló {url}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


# ── Buscador (igual que searchPage / parseResults) ──────────────────────────────

BLOCK_RE = re.compile(
    r'<a\s+class="clip-link"\s+data-id="(\d+)"\s+title="([^"]+)"\s+href="([^"]+)"[^>]*>.*?'
    r'<img[^>]+src="(https://muchohentai\.com/wp-content/uploads/[^"]+?\.(?:jpg|png))"',
    re.S | re.I,
)


def html_unescape(s):
    # Las MISMAS sustituciones que la app (no html.unescape), para que los títulos salgan idénticos
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&#8211;", "–").replace("&#8212;", "—").replace("&#038;", "&")
             .replace("&#8217;", "'").replace("&#039;", "'"))


def parse_results(html):
    out = []
    for m in BLOCK_RE.finditer(html):
        post_id, title, link, thumb = m.group(1), html_unescape(m.group(2)), html_unescape(m.group(3)), m.group(4)
        if title.strip() and thumb.strip() and link.strip():
            out.append({"postId": post_id, "title": title, "link": link, "thumb": thumb})
    return out


def search_page(query, page=1):
    query = query.strip()
    if not query:
        return []
    key = (query.lower(), page)
    if key in _page_cache:
        return _page_cache[key]
    enc = quote_plus(query)
    url = f"{BASE}/?s={enc}" if page <= 1 else f"{BASE}/page/{page}/?s={enc}"
    html = http_get(url)
    res = parse_results(html) if html and len(html) >= 500 else []
    _page_cache[key] = res
    return res


def search_all_pages(pool, queries, max_pages):
    """Todas las páginas de todas las búsquedas a la vez (como en la app). Devuelve {query: [resultados]}."""
    tasks = [(q, p) for q in queries for p in range(1, max_pages + 1)]
    pages = list(pool.map(lambda t: search_page(*t), tasks))
    out = {q: [] for q in queries}
    for (q, _p), res in zip(tasks, pages):
        out[q].extend(res)
    for q in queries:
        print(f"  '{q}': {len(out[q])} resultados en {max_pages} páginas")
    return out


# ── Clasificación y nombres (calco de la app) ───────────────────────────────────

def extract_episode_number(title):
    m = re.search(r"(?i)episode\s+(\d+)", title) or re.search(r"(?i)ep\.?\s*(\d+)", title)
    return int(m.group(1)) if m else 0


def classify(hit):
    title = hit["title"]
    low = title.lower()
    if "【pv】" in low:
        lang = PV
    elif re.search(r"(?i)\bRaw\s*$", title.strip()):
        lang = RAW
    elif "english subbed" in low:
        lang = ENG
    elif "en español" in low:
        lang = ES
    else:
        return None
    return {**hit, "lang": lang, "ep": extract_episode_number(title)}


def extract_series_name(title):
    s = re.sub(r"(?i)\s+episode\s+\d+.*$", "", title)
    s = re.sub(r"(?i)\s+ep\.?\s*\d+.*$", "", s)
    s = re.sub(r"(?i)\s+ova\s+\d+.*$", "", s)
    s = re.sub(r"^【PV】\s*", "", s)
    s = s.strip()
    s = re.sub(r"[\s\-‐‑‒–—―:|]+$", "", s)
    return s.strip()


def series_key(title):
    s = extract_series_name(title).lower()
    s = re.sub(r"\s*[\-‐‑‒–—―−]\s*", " - ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _is_letter_or_digit(c):
    # Character.isLetterOrDigit de Java: letras (Lu, Ll, Lt, Lm, Lo) y dígitos decimales (Nd)
    return unicodedata.category(c) in ("Lu", "Ll", "Lt", "Lm", "Lo", "Nd")


def fuzzy_alnum_key(title):
    return "".join(c for c in extract_series_name(title).lower() if _is_letter_or_digit(c))


def strip_lang_suffix(title):
    return re.sub(r"(?i)\s+(raw|english subbed|en español)\s*$", "", title).strip()


def levenshtein(a, b):
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        curr = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            curr[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev = curr
    return prev[len(b)]


def is_near_same_name(fa, fb):
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    return abs(len(fa) - len(fb)) <= 3 and levenshtein(fa, fb) <= 2


def is_fuzzy_same_series(fa, fb):
    if not fa or not fb:
        return False
    if is_near_same_name(fa, fb):
        return True
    return len(fa) >= 5 and len(fb) >= 5 and (fa.startswith(fb) or fb.startswith(fa))


def java_hash(s):
    """String.hashCode() de Kotlin/Java, para que los ids "mh_<hash>" sean los mismos que arma la app."""
    h = 0
    data = s.encode("utf-16-le")
    for (cu,) in struct.iter_unpack("<H", data):
        h = (31 * h + cu) & 0xFFFFFFFF
    return h - 0x100000000 if h >= 0x80000000 else h


def post_id_num(hit):
    try:
        return int(hit["postId"])
    except ValueError:
        return 2 ** 63 - 1


def distinct_by_post(hits):
    seen, out = set(), []
    for h in hits:
        if h["postId"] not in seen:
            seen.add(h["postId"])
            out.append(h)
    return out


def assoc_by_key(hits):
    """associateBy de Kotlin: el último gana el valor, pero se conserva la posición del primero."""
    d = {}
    for h in hits:
        d[(series_key(h["title"]), h["ep"])] = h
    return d


SUBS_RE = re.compile(r'var\s+subs\s*=\s*"([^"]+)"')


def fetch_subtitle_url(page_url):
    html = http_get(page_url)
    if not html:
        return None
    m = SUBS_RE.search(html)
    if not m:
        return None
    return BASE + m.group(1).replace("\\/", "/")


def sort_episodes(eps):
    # PV primero (PV 1, PV 2, …) y luego los episodios 1..N (orden estable, como en la app)
    return sorted(eps, key=lambda e: (0 if e["num"] < 0 else 1, -e["num"] if e["num"] < 0 else e["num"]))


def distinct_by_num(eps):
    seen, out = set(), []
    for e in eps:
        if e["num"] not in seen:
            seen.add(e["num"])
            out.append(e)
    return out


# ── buildAnimes ─────────────────────────────────────────────────────────────────

def build_animes(pool, raw_hits, eng_hits, es_hits, pv_hits, fill_gaps=True, fetch_eng_subs=True):
    display_name = {}
    for h in (sorted(es_hits, key=post_id_num) + sorted(raw_hits, key=post_id_num)
              + sorted(eng_hits, key=post_id_num) + sorted(pv_hits, key=post_id_num)):
        display_name.setdefault(series_key(h["title"]), extract_series_name(h["title"]))

    raw_by = assoc_by_key(distinct_by_post(raw_hits))
    eng_by = assoc_by_key(distinct_by_post(eng_hits))
    es_by = assoc_by_key(distinct_by_post(es_hits))

    all_keys = list(dict.fromkeys(list(es_by.keys()) + list(raw_by.keys()) + list(eng_by.keys())))

    def merge_one(key):
        es_hit, raw_hit, eng_hit = es_by.get(key), raw_by.get(key), eng_by.get(key)
        primary = es_hit or raw_hit or eng_hit
        if primary is None:
            return None
        if primary is es_hit:
            alt = raw_hit or eng_hit
        elif primary is raw_hit:
            alt = eng_hit
        else:
            alt = None
        eng_sub = None
        if fetch_eng_subs and eng_hit is not None and eng_hit is not primary:
            eng_sub = fetch_subtitle_url(eng_hit["link"])
        ep = {"num": primary["ep"], "nombre": strip_lang_suffix(primary["title"]), "thumb": primary["thumb"],
              "link": primary["link"], "linkAlt": alt["link"] if alt else None, "subtitulo_eng": eng_sub}
        return key, ep

    merged = [m for m in pool.map(merge_one, all_keys) if m is not None]

    grouped, poster_map, id_map = {}, {}, {}
    for (serie, _ep_num), ep in merged:
        lst = grouped.setdefault(serie, [])
        if all(e["num"] != ep["num"] for e in lst):
            lst.append(ep)
        if serie not in poster_map:
            poster_map[serie] = ep["thumb"] or ""
            id_map[serie] = f"mh_{java_hash(display_name.get(serie, serie))}"

    # PV aparte, numerados por el "Episode N" real del título; los que no traen número, después, por orden de publicación
    pv_groups = {}
    for h in distinct_by_post(pv_hits):
        pv_groups.setdefault(series_key(h["title"]), []).append(h)
    for serie, pvs in pv_groups.items():
        with_num, seen_n = [], set()
        for p in pvs:
            if p["ep"] > 0 and p["ep"] not in seen_n:
                seen_n.add(p["ep"])
                with_num.append(p)
        without_num = sorted([p for p in pvs if p["ep"] <= 0], key=post_id_num)
        base_n = max((p["ep"] for p in with_num), default=0)
        lst = grouped.setdefault(serie, [])
        for p in with_num:
            lst.append({"num": -p["ep"], "nombre": f"PV {p['ep']}", "thumb": p["thumb"], "link": p["link"]})
        for idx, p in enumerate(without_num):
            n = base_n + idx + 1
            lst.append({"num": -n, "nombre": f"PV {n}", "thumb": p["thumb"], "link": p["link"]})
        if serie not in poster_map:
            first = with_num[0] if with_num else (without_num[0] if without_num else None)
            poster_map[serie] = first["thumb"] if first else ""
            id_map[serie] = f"mh_pv_{java_hash(display_name.get(serie, serie))}"

    consolidated, c_poster, c_id, c_name = consolidate_fuzzy_series(grouped, poster_map, id_map, display_name)

    built = []
    for root, episodes in consolidated.items():
        built.append({
            "id": c_id.get(root) or f"mh_esp_{java_hash(root)}",
            "titulo": c_name.get(root) or root,
            "poster": c_poster.get(root) or "",
            "episodios": sort_episodes(distinct_by_num(episodes)),
        })

    return fill_episode_gaps(pool, built) if fill_gaps else built


def consolidate_fuzzy_series(grouped, poster_map, id_map, display_name):
    keys = list(grouped.keys())
    fuzzy_of = {k: fuzzy_alnum_key(display_name.get(k, k)) for k in keys}
    parent = {k: k for k in keys}

    def find(k):
        while parent[k] != k:
            k = parent[k]
        return k

    pos_eps = {k: {e["num"] for e in grouped[k] if e["num"] > 0} for k in keys}

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            fa, fb = fuzzy_of[keys[i]], fuzzy_of[keys[j]]
            if not is_fuzzy_same_series(fa, fb):
                continue
            ra, rb = find(keys[i]), find(keys[j])
            if ra == rb:
                continue
            # Parecidas SOLO por prefijo y con algún episodio en común → series distintas
            if not is_near_same_name(fa, fb) and (pos_eps[ra] & pos_eps[rb]):
                continue
            parent[ra] = rb
            pos_eps[rb] |= pos_eps[ra]

    consolidated, c_poster, c_id, c_name = {}, {}, {}, {}
    for k in keys:
        root = find(k)
        consolidated.setdefault(root, []).extend(grouped.get(k, []))
        c_poster.setdefault(root, poster_map.get(k, ""))
        c_id.setdefault(root, id_map.get(k) or f"mh_esp_{java_hash(root)}")
        cand = display_name.get(k, k)
        if root not in c_name or len(cand) > len(c_name[root]):
            c_name[root] = cand
    return consolidated, c_poster, c_id, c_name


def fill_episode_gaps(pool, animes):
    gaps = []
    for a in animes:
        nums = {e["num"] for e in a["episodios"] if e["num"] > 0}
        if not nums:
            continue
        max_num = max(nums)
        if max_num > 50:
            continue
        for n in [n for n in range(1, max_num + 1) if n not in nums][:6]:
            gaps.append((a["id"], a["titulo"], n))
    if not gaps:
        return animes
    print(f"  huecos detectados: {len(gaps)}")

    def patch(gap):
        anime_id, title, n = gap
        try:
            hits = [h for h in (classify(x) for x in search_page(f"{title} Episode {n}", 1))
                    if h and h["ep"] == n and h["lang"] != PV]
            wanted = series_key(title)
            best = next((h for h in hits if series_key(h["title"]) == wanted), None)
            if best is None:
                return None
            return anime_id, {"num": n, "nombre": strip_lang_suffix(best["title"]), "thumb": best["thumb"], "link": best["link"]}
        except Exception as e:  # noqa: BLE001
            print(f"  hueco '{title}' ep {n} falló: {e}", file=sys.stderr)
            return None

    found = [p for p in pool.map(patch, gaps) if p is not None]
    print(f"  huecos rellenados: {len(found)}/{len(gaps)}")
    if not found:
        return animes
    by_id = {}
    for anime_id, ep in found:
        by_id.setdefault(anime_id, []).append(ep)
    out = []
    for a in animes:
        extra = by_id.get(a["id"])
        if not extra:
            out.append(a)
            continue
        out.append({**a, "episodios": sort_episodes(distinct_by_num(a["episodios"] + extra))})
    return out


# ── searchEspanol ───────────────────────────────────────────────────────────────

def search_espanol(max_pages):
    with ThreadPoolExecutor(max_workers=PARALELO) as pool:
        paginas = search_all_pages(pool, ("Raw", "English Subbed", "En Español", "【PV】"), max_pages)
        todo = {q: [h for h in (classify(x) for x in res) if h] for q, res in paginas.items()}
        raw_hits = [h for h in todo["Raw"] if h["lang"] == RAW]
        eng_hits = [h for h in todo["English Subbed"] if h["lang"] == ENG]
        es_hits = [h for h in todo["En Español"] if h["lang"] == ES]
        pv_hits = [h for h in todo["【PV】"] if h["lang"] == PV]
        print(f"Encontrados: raw={len(raw_hits)} eng={len(eng_hits)} es={len(es_hits)} pv={len(pv_hits)}")
        return build_animes(pool, raw_hits, eng_hits, es_hits, pv_hits, fill_gaps=True, fetch_eng_subs=True)


def limpiar(anime):
    """Quita los null para que el JSON sea más chico (la app los trata igual)."""
    return {
        "id": anime["id"], "titulo": anime["titulo"], "poster": anime["poster"],
        "episodios": [{k: v for k, v in ep.items() if v is not None} for ep in anime["episodios"]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=10, help="páginas del buscador por categoría (la app usa 10)")
    ap.add_argument("--salida", default="cine/Archivos/primicias.json")
    args = ap.parse_args()

    t0 = time.time()
    series = search_espanol(args.paginas)
    print(f"Series: {len(series)}, episodios: {sum(len(s['episodios']) for s in series)}, {time.time() - t0:.0f} s")

    if len(series) < MIN_SERIES:
        print(f"Salieron solo {len(series)} series: parece un fallo del sitio, se conserva el JSON anterior", file=sys.stderr)
        sys.exit(1)

    ahora = datetime.now(timezone.utc)
    doc = {
        "generado": ahora.isoformat(timespec="seconds"),
        "ts": int(ahora.timestamp() * 1000),
        "total": len(series),
        "series": [limpiar(s) for s in series],
    }
    with open(args.salida, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Escrito {args.salida}")


if __name__ == "__main__":
    main()
