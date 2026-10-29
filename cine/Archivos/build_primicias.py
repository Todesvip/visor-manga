#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma los JSON del Home privado para que la app solo los descargue (una petición cada uno) en vez de buscar en
los sitios desde el celular:

  cine/Archivos/primicias.json      "Primicias H en español": calco de MuchoHentaiSearcher.searchEspanol() de la app
                                    (mismas búsquedas, misma fusión Raw/Eng/Es por episodio, mismos PV, misma
                                    consolidación de nombres, mismos ids "mh_..."), para que favoritos e historial
                                    sigan reconociendo las mismas series.
  cine/Archivos/top10.json          Top 10 de la semana (Hentaila*)          ┐ calco de los parsers de la app;
  cine/Archivos/mas_vistos.json     Más vistos (Hentaila*)                   │ cada uno con su fecha (ts). Si un
  cine/Archivos/avances.json        Avances recientes (PV de muchohentai)    │ sitio falla, su archivo no se toca
  cine/Archivos/comics.json         Comics (los dos sitios WordPress)        ┘ (se queda el anterior).

  (*) VeoHentai se mudó a Hentaila (hentaila.io): mismos episodios y mismos slugs, imágenes en /uploads/. Top 10 y Más
      vistos se arman primero de ahí y, si no responde, del sitio viejo. La fila del Top 10 es de imágenes HORIZONTALES:
      la miniatura del episodio en MuchoHentai (del enlaces.json de la otra cuenta) y, solo si MuchoHentai no tiene la
      serie, la captura que Hentaila muestra en la página del episodio; Más vistos usa la portada vertical de Hentaila.

Uso:  python cine/Archivos/build_primicias.py            (lo corre GitHub Actions cada hora)
      python cine/Archivos/build_primicias.py --paginas 10 --salida cine/Archivos/primicias.json
      python cine/Archivos/build_primicias.py --solo-home   (solo las 4 secciones del Home, para probar)
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


# ── Home privado: Top 10 y Más vistos (VeoHentai), Avances (PV de muchohentai) y Comics (WP REST) ──────────────
# Calco de VeoHentaiTopRepository.parse(), VeoHentaiExploreRepository.parsePage() (?orden=vistas) y de
# fetchHentaiVideosForHome() / fetchPostsFromSource() de MainActivity: mismas URLs, mismos selectores, mismos
# filtros, para que la app reciba exactamente la lista que armaría ella misma.
# Cada sección es independiente: si un sitio falla, se conserva la versión anterior de ESA sección (con su fecha).

import html as _html
import os
import threading
from urllib.parse import quote, urljoin, unquote_plus

try:
    from bs4 import BeautifulSoup
    from bs4.element import NavigableString, Tag, Comment, Declaration, Doctype, ProcessingInstruction, CData
    try:
        from bs4.element import Script, Stylesheet, TemplateString
    except ImportError:          # bs4 viejo
        Script = Stylesheet = TemplateString = type("_NoStr", (), {})
    _BS4 = True
except ImportError:
    _BS4 = False

VEO = "https://veohentai.com"
VEO_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": VEO + "/",
}
MH_PREVIEW_URL = BASE + "/g/preview/"
MH_PREVIEW_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": BASE + "/",
}
COMIC_SOURCES = [
    "https://comicspornow.com/wp-json/wp/v2/posts",
    "https://comiquetaxxx.com/wp-json/wp/v2/posts",
]
COMIC_UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.6367.82 Mobile Safari/537.36")
MOST_COUNT = 20
AVANCES_COUNT = 20

# Etiquetas que Jsoup trata como "bloque" al sacar el texto (mete un espacio entre bloques pegados)
_JSOUP_BLOCK = {
    "html", "head", "body", "frameset", "script", "noscript", "style", "meta", "link", "title", "frame", "noframes",
    "section", "nav", "aside", "hgroup", "header", "footer", "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol",
    "pre", "div", "blockquote", "hr", "address", "figure", "figcaption", "form", "fieldset", "ins", "del", "dl",
    "dt", "dd", "li", "table", "caption", "thead", "tfoot", "tbody", "colgroup", "col", "tr", "th", "td", "video",
    "audio", "canvas", "details", "summary", "menu", "plaintext", "template", "article", "main", "svg", "math",
    "center", "dir", "applet", "marquee", "listing",
}
_JSOUP_WS = " \t\n\f\r "


def _get_text_page(url, headers, referer=None):
    """GET de una página HTML (2 intentos). None si no hubo respuesta útil (como httpGetText de la app)."""
    s = requests.Session()
    h = dict(headers)
    if referer:
        h["Referer"] = referer
    for intento in range(2):
        try:
            r = s.get(url, headers=h, timeout=TIMEOUT)
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
            return r.text if r.text.strip() else None
        except requests.RequestException as e:
            print(f"  GET falló {url}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


def _soup(html):
    try:
        return BeautifulSoup(html, "html5lib")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _doc_base(soup, default):
    """Jsoup toma el <base href> del documento (si es absoluto) como base para absUrl()."""
    for b in soup.find_all("base"):
        href = (b.get("href") or "").strip()
        if href.startswith(("http://", "https://")):
            return href
    return default


def _abs_url(el, attr, base):
    """Element.absUrl(attr) de Jsoup: '' si no está el atributo; relativo → resuelto contra la base."""
    if not el.has_attr(attr):
        return ""
    v = (el.get(attr) or "").strip()
    if not base:
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*:", v):
            return v
        return ""
    try:
        return urljoin(base, v)
    except ValueError:
        return v if re.match(r"^[a-zA-Z][a-zA-Z0-9+\-.]*:", v) else ""


def _attr(el, name):
    """Element.attr(name) de Jsoup: '' si no existe."""
    if el is None:
        return ""
    v = el.get(name)
    if v is None:
        return ""
    return " ".join(v) if isinstance(v, list) else v


def _jsoup_text(el):
    """Element.text() de Jsoup 1.15: texto normalizado (espacios colapsados; un espacio entre bloques y texto)."""
    if el is None:
        return ""
    out = []

    def last_ws():
        return not out or out[-1][-1:] == " "

    def walk(node):
        if isinstance(node, (Comment, Declaration, Doctype, ProcessingInstruction, CData, Script, Stylesheet,
                             TemplateString)):
            return
        if isinstance(node, NavigableString):
            buf = []
            for c in str(node):
                if c in ("\u200b", "\u00ad"):
                    continue
                if c in _JSOUP_WS:
                    if (buf and buf[-1] == " ") or (not buf and last_ws()):
                        continue
                    buf.append(" ")
                else:
                    buf.append(c)
            if buf:
                out.append("".join(buf))
            return
        if isinstance(node, Tag):
            if node.name in ("script", "style"):
                return
            is_block = node.name in _JSOUP_BLOCK
            if (is_block or node.name == "br") and not last_ws():
                out.append(" ")
            for ch in node.contents:
                walk(ch)
            if is_block and isinstance(node.next_sibling, NavigableString) and not last_ws():
                out.append(" ")

    walk(el)
    return "".join(out).strip()


def _select_first(el, selector):
    """Element.selectFirst() de Jsoup: el primero en orden de documento, contando al propio elemento."""
    if isinstance(el, Tag) and el.name and el.name != "[document]":
        try:
            import soupsieve
            if soupsieve.match(selector, el):
                return el
        except Exception:
            pass
    return el.select_one(selector)


# ── Top 10 de la semana (VeoHentaiTopRepository.parse) ───────────────────────────────────────────────────────

def _veo_normalize_img(raw):
    if not raw:
        return raw
    if "/_next/image" in raw and "url=" in raw:
        enc = raw.split("url=", 1)[1].split("&", 1)[0]
        try:
            dec = unquote_plus(enc)
        except Exception:
            dec = enc
        return VEO + dec if dec.startswith("/") else dec
    return raw


def parse_top10(html):
    soup = _soup(html)
    base = _doc_base(soup, VEO + "/")
    section = None
    for sec in soup.select("section"):
        if sec.select_one('a[href*="orden=vistas-semana"]') is not None:
            section = sec
            break
    if section is None:
        for sec in soup.select("section"):
            h2 = sec.select_one("h2")
            if h2 is not None and "top 10" in _jsoup_text(h2).lower():
                section = sec
                break
    if section is None:
        return []
    out, seen = [], set()
    for a in section.select('a[href^="/ver/"]'):
        slug = _attr(a, "href").strip().strip("/")
        if slug.startswith("ver/"):
            slug = slug[4:]
        slug = slug.strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        img = _select_first(a, "img")
        if img is None:
            continue
        raw_src = _abs_url(img, "src", base) or _abs_url(img, "data-src", base)
        image_url = _veo_normalize_img(raw_src)
        if not image_url:
            continue
        h3 = _select_first(a, "h3")
        title = _jsoup_text(h3).strip() if h3 is not None else ""
        if not title:
            title = _attr(img, "alt").strip()
        if not title:
            title = slug.replace("-", " ")
        rank = None
        for sp in a.select("span[aria-hidden]"):
            t = _jsoup_text(sp).strip()
            if re.fullmatch(r"\d{1,2}", t):
                rank = int(t)
                break
        if rank is None:
            rank = len(out) + 1
        out.append({"rank": rank, "slug": slug, "title": title, "imageUrl": image_url})
        if len(out) >= 10:
            break
    return sorted(out, key=lambda x: x["rank"])


def _build_top10_veo():
    html = _get_text_page(VEO + "/", VEO_HEADERS)
    if not html:
        return []
    try:
        return parse_top10(html)
    except Exception as e:
        print(f"  Top 10: no se pudo leer la página: {e}", file=sys.stderr)
        return []


# ── Más vistos (VeoHentaiExploreRepository.parsePage con ?orden=vistas) ──────────────────────────────────────

def _rsc_stream(html):
    """El flujo de Next.js: self.__next_f.push([1,"…"]) con el texto escapado como cadena JS (calco de rscStream)."""
    key = 'self.__next_f.push([1,"'
    out = []
    n = len(html)
    start = 0
    while True:
        s = html.find(key, start)
        if s < 0:
            break
        i = s + len(key)
        while i < n:
            c = html[i]
            if c == "\\" and i + 1 < n:
                nx = html[i + 1]
                if nx == "n":
                    out.append("\n")
                elif nx == "r":
                    out.append("\r")
                elif nx == "t":
                    out.append("\t")
                elif nx == "b":
                    out.append("\b")
                elif nx == "f":
                    out.append("\f")
                elif nx == "u":
                    cp = None
                    if i + 6 <= n:
                        hx = html[i + 2:i + 6]
                        if re.fullmatch(r"[+-]?[0-9a-fA-F]+", hx):
                            try:
                                cp = int(hx, 16)
                            except ValueError:
                                cp = None
                    if cp is not None and 0 <= cp <= 0xFFFF:
                        out.append(chr(cp))
                        i += 4
                else:
                    out.append(nx)
                i += 2
            elif c == '"':
                break
            else:
                out.append(c)
                i += 1
        start = i + 1
    s = "".join(out)
    # Los 😀 (parejas sustitutas) se juntan en un solo carácter, como hace Kotlin con su String
    return s.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")


def _read_json_at(stream, start):
    try:
        v, _end = json.JSONDecoder(strict=False).raw_decode(stream, start)
        return v
    except Exception:
        return None


def _prim_str(v):
    """JsonObject.str(k): solo primitivos (string/número/bool), como texto."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return v
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    return None


def _prim_int(v):
    """JsonPrimitive.getAsInt(): número → entero; texto numérico → entero; otra cosa → error (como Gson)."""
    if v is None or isinstance(v, (dict, list)):
        return None
    if isinstance(v, bool):
        raise ValueError("bool no es entero")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        if re.fullmatch(r"[+-]?\d+", v.strip()) and v == v.strip():
            return int(v)
        raise ValueError(f"'{v}' no es entero")
    return None


def _obj(o, k):
    v = o.get(k)
    return v if isinstance(v, dict) else None


def _parse_items(stream):
    key = '"initial":'
    idx = stream.find(key + "[")
    if idx < 0:
        return []
    arr = _read_json_at(stream, idx + len(key))
    if not isinstance(arr, list):
        return []
    out = []
    for o in arr:
        if not isinstance(o, dict):
            continue
        slug = _prim_str(o.get("slug"))
        if slug is None:
            continue
        title = _prim_str(o.get("title"))
        if title is None:
            continue
        featured, backdrop = _obj(o, "featured"), _obj(o, "backdrop")
        path = (_prim_str(featured.get("path")) if featured else None)
        if path is None:
            path = (_prim_str(backdrop.get("path")) if backdrop else None)
        if path is None:
            continue
        date = _prim_str(o.get("releaseDate"))
        if date is None:
            date = _prim_str(o.get("uploadDate"))
        year = 0
        if date is not None:
            y4 = date[:4]
            year = int(y4) if re.fullmatch(r"[+-]?\d+", y4) else 0
        series, studio = _obj(o, "series"), _obj(o, "studio")
        item_id = _prim_int(o.get("id"))
        episode = _prim_int(o.get("episodeNumber"))
        bpath = _prim_str(backdrop.get("path")) if backdrop else None
        out.append({
            "id": item_id if item_id is not None else 0,
            "slug": slug,
            "title": title,
            "episode": episode if episode is not None else 0,
            "seriesName": (_prim_str(series.get("name")) if series else None) or "",
            "imageUrl": f"{VEO}/media/{path}",
            "studioSlug": (_prim_str(studio.get("slug")) if studio else None) or "",
            "year": year,
            "backdropUrl": f"{VEO}/media/{bpath}" if bpath is not None else None,
        })
    return out


def _parse_explore_dom(html):
    """Plan B de la app si cambiara el formato: el HTML visible (sin estudio ni año)."""
    soup = _soup(html)
    base = _doc_base(soup, VEO + "/")
    out, seen = [], set()
    for a in soup.select('main a[href^="/ver/"]'):
        slug = _attr(a, "href").strip().strip("/")
        if slug.startswith("ver/"):
            slug = slug[4:]
        slug = slug.strip("/")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        img = _select_first(a, "img")
        if img is None:
            continue
        src = _abs_url(img, "src", base)
        if not src:
            continue
        h3 = _select_first(a, "h3")
        title = _jsoup_text(h3).strip() if h3 is not None else ""
        if not title:
            title = _attr(img, "alt").strip()
        m = re.search(r"(?i)episodio\s*(\d+)", title)
        ep = int(m.group(1)) if m else 0
        out.append({"id": 0, "slug": slug, "title": title, "episode": ep, "seriesName": "", "imageUrl": src,
                    "studioSlug": "", "year": 0, "backdropUrl": None})
    return out


def parse_explore_page(html):
    """VeoHentaiExploreRepository.parsePage(): los episodios de una página de /explorar/ (None si no se pudo leer)."""
    try:
        items = _parse_items(_rsc_stream(html))
    except Exception as e:
        print(f"  Más vistos: no se pudo leer la página: {e}", file=sys.stderr)
        return None
    if items:
        return items
    try:
        return _parse_explore_dom(html)
    except Exception as e:
        print(f"  Más vistos: no se pudo leer el HTML: {e}", file=sys.stderr)
        return None


def _build_mas_vistos_veo():
    html = _get_text_page(VEO + "/explorar/?orden=vistas", VEO_HEADERS)
    if not html:
        return []
    items = parse_explore_page(html)
    return (items or [])[:MOST_COUNT]


# ── Hentaila (hentaila.io): ahí se mudó VeoHentai ─────────────────────────────────────────────────────────────
# Son los mismos episodios y los mismos slugs (/ver/<slug>/), pero con otro diseño: las imágenes salen de /uploads/AAAA/MM/
# (antes /media/AAAA/MM/), "Más vistos" es /sort/most-views/ y "Trending" es /trending/. Cada episodio es una tarjeta:
#   <a class="a_item" href="/ver/<slug>/"><div class="v_item"><div class="video_cover"><img src="/uploads/…"/>
#   <span class="card_badge">EP 2</span> … </div><div class="video_title">Título Episodio 2</div></div></a>
# Top 10 y Más vistos se arman primero de ahí; si Hentaila no responde se prueba el sitio viejo (VeoHentai).

try:
    # Con la huella TLS de Chrome Cloudflare no pone reto a los servidores de GitHub; si no está instalada se usa requests.
    from curl_cffi import requests as _curl_requests
    _CURL = True
except ImportError:
    _CURL = False

HENTAILA = "https://hentaila.io"
HENTAILA_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9",
    "Referer": HENTAILA + "/",
}
HENTAILA_TOP_PAGES = ["/trending/", "/sort/most-views/"]       # Top 10: si la primera no sirve, se usa la segunda
HENTAILA_MOST_PAGES = ["/sort/most-views/", "/trending/"]      # Más vistos: igual, al revés
_hentaila_pages = {}                                           # páginas ya bajadas en esta corrida (Top 10 y Más vistos comparten)
_hentaila_lock = threading.Lock()
_EP_AL_FINAL = re.compile(r"(?i)\s*[-–:]?\s*episodio\s*\d+\s*$")   # igual que seriesTitle de la app


def _get_hentaila_page(url):
    """GET de una página de hentaila.io (2 intentos). None si no hubo respuesta útil; cada fallo deja escrita su causa."""
    with _hentaila_lock:
        if url in _hentaila_pages:
            return _hentaila_pages[url]
    for intento in range(2):
        try:
            if _CURL:
                r = _curl_requests.get(url, headers={"Accept-Language": "es-ES,es;q=0.9", "Referer": HENTAILA + "/"},
                                       impersonate="chrome", timeout=TIMEOUT)
            else:
                r = requests.get(url, headers=HENTAILA_HEADERS, timeout=TIMEOUT)
            if r.status_code in (429, 503):
                print(f"  Hentaila: HTTP {r.status_code} en {url} (intento {intento + 1})", file=sys.stderr)
                time.sleep(3 + 3 * intento)
                continue
            if r.status_code != 200:
                print(f"  Hentaila: HTTP {r.status_code} en {url}", file=sys.stderr)
                return None
            texto = r.text
            if "Just a moment" in texto[:2000] and "cf-" in texto[:5000]:
                print(f"  Hentaila: Cloudflare pide verificación en {url}", file=sys.stderr)
                return None
            if not texto.strip():
                return None
            with _hentaila_lock:
                _hentaila_pages[url] = texto
            return texto
        except Exception as e:
            print(f"  Hentaila: GET falló {url}: {e}", file=sys.stderr)
            time.sleep(2)
    return None


def _hentaila_portada(img, base):
    """La portada de una tarjeta como dirección absoluta y bien escrita; None si no tiene o es el aviso de 'sin portada'."""
    if img is None:
        return None
    raw = (_attr(img, "src") or _attr(img, "data-src")).strip()
    if "/_next/image" in raw and "url=" in raw:            # el optimizador de Next.js: la imagen de verdad va dentro de url=
        enc = raw.split("url=", 1)[1].split("&", 1)[0]
        try:
            raw = unquote_plus(enc)
        except Exception:
            raw = enc
    if not raw or raw.startswith("data:") or "poster-unavailable" in raw or raw.lower().split("?")[0].endswith(".svg"):
        return None
    return quote(urljoin(base, raw), safe="/:?&=%#+@!$'()*,;~-._[]")   # los %XX que ya traía se respetan


def parse_hentaila_cards(html):
    """Las tarjetas de episodio de una página de Hentaila, en su orden:
    [{"slug", "title", "episode", "seriesName", "imageUrl" (None si no tiene portada)}]."""
    soup = _soup(html)
    base = _doc_base(soup, HENTAILA + "/")
    out, por_slug = [], {}
    for a in soup.select('a[href*="/ver/"]'):
        m = re.search(r"/ver/([^/?#]+)", _attr(a, "href"))
        if not m:
            continue
        slug = m.group(1).strip()
        img = _select_first(a, "img")
        portada = _hentaila_portada(img, base)
        previa = por_slug.get(slug)
        if previa is not None:                    # la misma serie con otro enlace (p. ej. el del título): solo se le completa la portada
            if previa["imageUrl"] is None and portada is not None:
                previa["imageUrl"] = portada
            continue
        titulo_el = _select_first(a, ".video_title")
        titulo = _jsoup_text(titulo_el).strip() if titulo_el is not None else ""
        if not titulo and img is not None:
            titulo = _attr(img, "alt").strip()
        if not titulo:
            titulo = slug.replace("-", " ")
        insignia = _select_first(a, ".card_badge")
        n = re.search(r"\d+", _jsoup_text(insignia)) if insignia is not None else None
        if n is None:
            n = re.search(r"episodio-(\d+)$", slug)
        episodio = int(n.group(1) if n.lastindex else n.group()) if n else 0
        item = {"slug": slug, "title": titulo, "episode": episodio,
                "seriesName": _EP_AL_FINAL.sub("", titulo).strip() or titulo, "imageUrl": portada}
        por_slug[slug] = item
        out.append(item)
    return out


def _hentaila_tarjetas(rutas):
    """Las tarjetas CON portada de la primera página de [rutas] que dé algo ([] si ninguna)."""
    for ruta in rutas:
        html = _get_hentaila_page(HENTAILA + ruta)
        if not html:
            continue
        try:
            tarjetas = parse_hentaila_cards(html)
        except Exception as e:
            print(f"  Hentaila: no se pudo leer {ruta}: {e}", file=sys.stderr)
            continue
        con_portada = [t for t in tarjetas if t["imageUrl"]]
        if con_portada:
            print(f"  Hentaila {ruta}: {len(tarjetas)} tarjetas, {len(con_portada)} con portada")
            return con_portada
        print(f"  Hentaila {ruta}: sin tarjetas con portada ({len(html)} bytes)", file=sys.stderr)
    return []


def parse_hentaila_miniatura(html, slug):
    """La imagen HORIZONTAL de un episodio: la que Hentaila muestra de él en su propia página (/ver/<slug>/). La columna
    de la derecha lista los episodios de la serie («Más de …») y los relacionados, cada uno con una miniatura
    (div.poster > a > img) que es la captura horizontal del episodio; se toma la del enlace a ESTE episodio.
    None si no sale, o si es la misma portada vertical (episodios sin captura: ahí Hentaila repite la portada)."""
    soup = _soup(html)
    base = _doc_base(soup, HENTAILA + "/")
    portada = _hentaila_portada(_select_first(soup, ".cover img"), base)
    for a in soup.select('a[href*="/ver/"]'):
        m = re.search(r"/ver/([^/?#]+)", _attr(a, "href"))
        if not m or m.group(1) != slug:
            continue
        img = _select_first(a, "img")
        if img is None:
            continue
        # la miniatura de la columna derecha (div.poster) o, si cambiaran las clases, cualquier imagen más ancha que alta
        w, h = _attr(img, "width"), _attr(img, "height")
        apaisada = w.isdigit() and h.isdigit() and int(w) > int(h)
        if a.find_parent(class_="poster") is None and not apaisada:
            continue
        url = _hentaila_portada(img, base)
        if url and url != portada:
            return url
    return None


def _hentaila_horizontal(slug, respaldo):
    """La imagen horizontal del episodio `slug`: la de su página en Hentaila; si ahí no sale (los episodios viejos de una
    serie larga no aparecen en su propia lista), la del catálogo (`respaldo`: slug → url). None si no hay ninguna."""
    html = _get_hentaila_page(f"{HENTAILA}/ver/{slug}/")
    if html:
        try:
            url = parse_hentaila_miniatura(html, slug)
        except Exception as e:
            print(f"  Hentaila: no se pudo leer la página de {slug}: {e}", file=sys.stderr)
            url = None
        if url:
            return url
    return respaldo.get(slug)


_VEO_MEDIA = re.compile(r"^https?://(?:www\.)?veohentai\.com/media/(.+)$", re.I)


def _backdrops_del_catalogo(folder):
    """slug → imagen horizontal, leída del catalogo.json que arma build_catalogo.py en la misma carpeta ({} si no existe).
    Las direcciones del sitio viejo (veohentai.com/media/…) se pasan a las de Hentaila (hentaila.io/uploads/…)."""
    try:
        with open(os.path.join(folder, "catalogo.json"), encoding="utf-8") as f:
            items = json.load(f).get("items") or []
    except Exception:
        return {}
    out = {}
    for it in items:
        if not isinstance(it, dict) or not it.get("slug") or not it.get("backdropUrl"):
            continue
        url = str(it["backdropUrl"])
        m = _VEO_MEDIA.match(url)
        out[it["slug"]] = quote(HENTAILA + "/uploads/" + m.group(1), safe="/:?&=%#+@!$'()*,;~-._[]") if m else url
    return out


ENLACES_URL = "https://noads-hue.github.io/noads/cine/Archivos/enlaces.json"    # series ya resueltas en MuchoHentai (las arma la otra cuenta cada 3 h)
_MH_IMAGEN = re.compile(r"^https?://(?:www\.)?muchohentai\.com/\S+\.(?:jpe?g|png|webp)$", re.I)


def _enlaces_muchohentai(url=ENLACES_URL):
    """clave (título de la serie en minúsculas) → serie de MuchoHentai ya resuelta, del enlaces.json que la otra cuenta arma
    con las series del Home. {} si no responde o no trae lo esperado: el Top 10 sale entonces con lo de Hentaila."""
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            print(f"  enlaces.json: HTTP {r.status_code}", file=sys.stderr)
            return {}
        items = r.json().get("items") or []
    except Exception as e:
        print(f"  enlaces.json: no se pudo leer: {e}", file=sys.stderr)
        return {}
    out = {}
    for it in items:
        if isinstance(it, dict) and it.get("clave") and isinstance(it.get("anime"), dict):
            out[str(it["clave"]).strip().lower()] = it["anime"]
    print(f"  enlaces.json: {len(out)} series resueltas en MuchoHentai")
    return out


def _miniatura_muchohentai(serie, episodio, enlaces):
    """La miniatura (rectangular) del episodio `episodio` de la serie `serie` en MuchoHentai; si ese episodio no la trae,
    la imagen de la serie en MuchoHentai. None si MuchoHentai no tiene la serie."""
    anime = (enlaces or {}).get((serie or "").strip().lower())
    if not isinstance(anime, dict):
        return None
    if episodio > 0:                                  # los PV de MuchoHentai llevan número negativo: no son episodios
        for ep in anime.get("episodios") or []:
            if isinstance(ep, dict) and ep.get("num") == episodio and _MH_IMAGEN.match(str(ep.get("thumb") or "")):
                return ep["thumb"]
    poster = str(anime.get("poster") or "")
    return poster if _MH_IMAGEN.match(poster) else None


HENTAILA_MIN_TOP = 5          # una página con menos tarjetas que estas es un error del sitio, no una lista: no se pisa el JSON anterior
HENTAILA_MIN_MAS = 10


def _build_top10_hentaila(respaldo=None, enlaces=None):
    tarjetas = _hentaila_tarjetas(HENTAILA_TOP_PAGES)[:10]
    if 0 < len(tarjetas) < HENTAILA_MIN_TOP:
        print(f"  Top 10: Hentaila dio solo {len(tarjetas)}: se descarta", file=sys.stderr)
        return []
    # La fila del Top 10 es de imágenes HORIZONTALES (la captura de cada episodio), no de portadas verticales. Salen de
    # MuchoHentai: la miniatura de ese episodio, ya resuelta en enlaces.json. Solo las series que MuchoHentai no tiene usan la
    # de la página del episodio en Hentaila (un pedido por episodio, 4 a la vez) y, sin ella, la portada para no dejar un hueco.
    respaldo = respaldo or {}
    miniaturas = [_miniatura_muchohentai(t["seriesName"], t["episode"], enlaces) for t in tarjetas]
    faltan = [t for t, m in zip(tarjetas, miniaturas) if not m]
    with ThreadPoolExecutor(max_workers=4) as pool:
        horizontales = dict(zip((t["slug"] for t in faltan),
                                pool.map(lambda t: _hentaila_horizontal(t["slug"], respaldo), faltan)))
    con_horizontal = sum(1 for h in horizontales.values() if h)
    print(f"  Top 10: {len(tarjetas) - len(faltan)} de {len(tarjetas)} con la miniatura de MuchoHentai"
          + (f", {con_horizontal} con la horizontal de Hentaila" if con_horizontal else "")
          + (f", {len(faltan) - con_horizontal} con la portada" if len(faltan) > con_horizontal else ""))
    return [{"rank": i, "slug": t["slug"], "title": t["title"], "imageUrl": m or horizontales.get(t["slug"]) or t["imageUrl"]}
            for i, (t, m) in enumerate(zip(tarjetas, miniaturas), 1)]


def _build_mas_vistos_hentaila():
    # Hentaila no da id, estudio, año ni imagen horizontal en la tarjeta: van vacíos (la app solo usa slug, título, episodio y portada)
    items = [{"id": 0, "slug": t["slug"], "title": t["title"], "episode": t["episode"], "seriesName": t["seriesName"],
              "imageUrl": t["imageUrl"], "studioSlug": "", "year": 0, "backdropUrl": None}
             for t in _hentaila_tarjetas(HENTAILA_MOST_PAGES)[:MOST_COUNT]]
    if 0 < len(items) < HENTAILA_MIN_MAS:
        print(f"  Más vistos: Hentaila dio solo {len(items)}: se descarta", file=sys.stderr)
        return []
    return items


def build_top10(respaldo=None, enlaces=None):
    """Top 10 de la semana: primero de Hentaila (donde se mudó VeoHentai) y, si no responde, del sitio viejo.
    `enlaces` = las series de MuchoHentai ya resueltas (_enlaces_muchohentai): de ahí sale la imagen de cada episodio.
    `respaldo` = slug → imagen horizontal del catálogo, para las series que MuchoHentai no tiene y cuya página no la trae."""
    try:
        items = _build_top10_hentaila(respaldo, enlaces)
    except Exception as e:
        print(f"  Top 10: Hentaila falló: {e}", file=sys.stderr)
        items = []
    if items:
        return items
    print("  Top 10: Hentaila sin datos, se prueba VeoHentai", file=sys.stderr)
    return _build_top10_veo()


def build_mas_vistos():
    """Más vistos: primero de Hentaila y, si no responde, del sitio viejo."""
    try:
        items = _build_mas_vistos_hentaila()
    except Exception as e:
        print(f"  Más vistos: Hentaila falló: {e}", file=sys.stderr)
        items = []
    if items:
        return items
    print("  Más vistos: Hentaila sin datos, se prueba VeoHentai", file=sys.stderr)
    return _build_mas_vistos_veo()


# ── Avances recientes (fetchHentaiVideosForHome: muchohentai.com/g/preview/) ─────────────────────────────────

_MH_EXCL = ("/tag/", "/category/", "?", "/page/")


def _mh_url_ok(url):
    if url == "https://muchohentai.com/":
        return False
    return not any(x in url for x in _MH_EXCL)


def _first_thumb(img, attrs):
    if img is None:
        return ""
    for a in attrs:
        v = _attr(img, a)
        if v and not v.startswith("data:"):
            return v
    return ""


def parse_avances(html):
    soup = _soup(html)
    base = _doc_base(soup, "")          # la app parsea sin base: solo valen los enlaces absolutos
    videos = []
    for el in soup.select("article, .post, .video-item, .video-card, .thumb-block, .item, li.video"):
        anchor = _select_first(el, "a[href]")
        if anchor is None:
            continue
        url = _abs_url(anchor, "href", base)
        if "muchohentai.com" not in url:
            continue
        if not _mh_url_ok(url):
            continue
        img = _select_first(el, "img")
        thumb = _first_thumb(img, ("data-src", "data-lazy-src", "data-original", "src"))
        tel = _select_first(el, ".entry-title, .title, .video-title, h1, h2, h3, h4, .name")
        title = _jsoup_text(tel) if tel is not None else ""
        if not title:
            title = _attr(anchor, "title")
        if not title:
            title = _attr(img, "alt") if img is not None else ""
        title = title.strip()
        del_ = _select_first(el, ".duration, .time, .length, .thumb-duration")
        duration = _jsoup_text(del_) if del_ is not None else ""
        if title and thumb:
            videos.append({"title": title, "url": url, "thumb": thumb, "duration": duration})

    if not videos:
        for anchor in soup.select("a[href]"):
            url = _abs_url(anchor, "href", base)
            if "muchohentai.com" not in url:
                continue
            if not _mh_url_ok(url):
                continue
            img = _select_first(anchor, "img")
            if img is None:
                continue
            thumb = _first_thumb(img, ("data-src", "data-lazy-src", "src"))
            title = _attr(anchor, "title") or _attr(img, "alt") or ""
            title = title.strip()
            if title and thumb:
                videos.append({"title": title, "url": url, "thumb": thumb, "duration": ""})

    seen, uniq = set(), []
    for v in videos:
        if v["url"] in seen:
            continue
        seen.add(v["url"])
        uniq.append(v)
    pv = [v for v in uniq if ("pv" in v["title"].lower() or "【" in v["title"] or "/g/preview" in v["url"]
                              or "category-pv" in v["url"] or "category/pv" in v["url"])]
    return pv[:AVANCES_COUNT]


def build_avances():
    html = _get_text_page(MH_PREVIEW_URL, MH_PREVIEW_HEADERS)
    if not html:
        return []
    try:
        return parse_avances(html)
    except Exception as e:
        print(f"  Avances: no se pudo leer la página: {e}", file=sys.stderr)
        return []


# ── Comics (fetchPostsFromSource: WP REST de los dos sitios, primera página) ────────────────────────────────

_IMG_SRC_RE = re.compile(r'''src=["']([^"']+\.(?:jpg|jpeg|png|webp))["']''', re.I)


def _from_html_text(s):
    """Html.fromHtml(s).toString().trim() de Android, para títulos: sin etiquetas, entidades decodificadas,
    espacios y saltos de línea seguidos convertidos en un solo espacio."""
    s = re.sub(r"<[^>]*>", "", s or "")
    s = _html.unescape(s)
    s = re.sub(r"[ \n]+", " ", s)
    return s.strip()


def _wp_thumb(post):
    emb = post.get("_embedded")
    media = None
    if isinstance(emb, dict):
        fm = emb.get("wp:featuredmedia")
        if isinstance(fm, list) and fm and isinstance(fm[0], dict):
            media = fm[0]
    thumb = None
    if media is not None:
        md = media.get("media_details")
        sizes = md.get("sizes") if isinstance(md, dict) else None
        if isinstance(sizes, dict):
            for name in ("medium_large", "large", "medium", "full", "thumbnail"):
                sz = sizes.get(name)
                if isinstance(sz, dict) and sz.get("source_url") is not None:
                    thumb = sz.get("source_url")
                    break
        if thumb is None and media.get("source_url") is not None:
            thumb = media.get("source_url")
    if thumb is None:
        thumb = ""
    if thumb == "":
        content = post.get("content")
        html_c = content.get("rendered") if isinstance(content, dict) else None
        m = _IMG_SRC_RE.search(html_c or "")
        thumb = m.group(1) if m else ""
    return thumb


def parse_wp_posts(raw):
    posts = json.loads(raw)
    out = []
    for post in posts:
        title = _from_html_text(post["title"]["rendered"])
        thumb = _wp_thumb(post)
        if not thumb:
            continue
        out.append({"title": title, "url": post["link"], "thumb": thumb})
    return out


def fetch_comics_source(base_url, idx):
    origin = base_url.split("/wp-json", 1)[0]
    url = f"{base_url}?per_page=20&page=1&_embed=1"
    headers = {
        "User-Agent": COMIC_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": origin + "/",
        "Connection": "keep-alive",
    }
    s = requests.Session()
    for attempt in (1, 2):
        try:
            if attempt > 1:
                time.sleep(3)
            r = s.get(url, headers=headers, timeout=25)
            code, raw = r.status_code, r.text
            if code in (429, 503):
                raise Exception(f"HTTP {code} (reintento {attempt})")
            if not raw.lstrip().startswith("["):
                if code < 200 or code > 299:
                    raise Exception(f"HTTP {code} desde {base_url}: {raw[:200]}")
                raise Exception(f"Respuesta inesperada de {base_url} (no es JSON array)")
            out = parse_wp_posts(raw)
            for c in out:
                c["src"] = idx
            return out
        except Exception as e:
            print(f"  Comics [{base_url}] intento {attempt} fallido: {e}", file=sys.stderr)
    return None


def build_comics(previous):
    """La fusión A + B de la primera página. Si un sitio falla, se reutilizan sus cómics del JSON anterior."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda t: fetch_comics_source(t[1], t[0]), list(enumerate(COMIC_SOURCES))))
    out = []
    for idx, res in enumerate(results):
        if res is None:
            prev = [c for c in (previous or []) if c.get("src") == idx]
            print(f"  Comics: sitio {idx + 1} sin respuesta; se conservan {len(prev)} del JSON anterior", file=sys.stderr)
            res = prev
        out.extend(res)
    return out


# ── Armado de los JSON del Home privado (uno por sección, como primicias.json) ───────────────────────────────

HOME_FILES = {"top10": "top10.json", "masVistos": "mas_vistos.json", "avances": "avances.json", "comics": "comics.json"}


def _load_previous(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_section(path, items):
    ahora = datetime.now(timezone.utc)
    doc = {
        "generado": ahora.isoformat(timespec="seconds"),
        "ts": int(ahora.timestamp() * 1000),
        "total": len(items),
        "items": [{a: b for a, b in it.items() if b is not None} for it in items],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def build_home(folder):
    """Escribe top10.json, mas_vistos.json, avances.json y comics.json en `folder` (cada uno solo si salió algo;
    si un sitio falla, su archivo anterior se queda tal cual). True si al menos uno se escribió."""
    if not _BS4:
        print("Falta beautifulsoup4 (pip install beautifulsoup4 html5lib): no se arman las secciones del Home", file=sys.stderr)
        return False
    t0 = time.time()
    paths = {k: os.path.join(folder, v) for k, v in HOME_FILES.items()}
    prev_comics = _load_previous(paths["comics"]).get("items")
    respaldo = _backdrops_del_catalogo(folder)
    enlaces = _enlaces_muchohentai()

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            "top10": pool.submit(build_top10, respaldo, enlaces),
            "masVistos": pool.submit(build_mas_vistos),
            "avances": pool.submit(build_avances),
            "comics": pool.submit(build_comics, prev_comics),
        }
        results = {k: f.result() for k, f in futures.items()}

    escritos = 0
    for k, items in results.items():
        if items:
            _write_section(paths[k], items)
            escritos += 1
            print(f"  {k}: {len(items)} → {HOME_FILES[k]}")
        else:
            print(f"  {k}: sin datos; se conserva {HOME_FILES[k]} anterior", file=sys.stderr)
    print(f"Home privado armado en {time.time() - t0:.0f} s ({escritos} de 4 archivos escritos)")
    return escritos > 0


def build_primicias(paginas, salida):
    """Escribe primicias.json. False (y no toca el archivo) si salieron muy pocas series."""
    t0 = time.time()
    series = search_espanol(paginas)
    print(f"Series: {len(series)}, episodios: {sum(len(s['episodios']) for s in series)}, {time.time() - t0:.0f} s")

    if len(series) < MIN_SERIES:
        print(f"Salieron solo {len(series)} series: parece un fallo del sitio, se conserva el JSON anterior", file=sys.stderr)
        return False

    ahora = datetime.now(timezone.utc)
    doc = {
        "generado": ahora.isoformat(timespec="seconds"),
        "ts": int(ahora.timestamp() * 1000),
        "total": len(series),
        "series": [limpiar(s) for s in series],
    }
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"Escrito {salida}")
    return True


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)   # para que en el log de Actions salga todo en orden
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--paginas", type=int, default=10, help="páginas del buscador por categoría (la app usa 10)")
    ap.add_argument("--salida", default="cine/Archivos/primicias.json")
    ap.add_argument("--home", default=None, help="carpeta de los JSON del Home (por defecto, la misma de --salida)")
    ap.add_argument("--solo-home", action="store_true", help="solo arma las 4 secciones del Home (para probar)")
    args = ap.parse_args()
    home_folder = args.home or (os.path.dirname(args.salida) or ".")

    print("== Home privado: Top 10, Más vistos, Avances, Comics ==")
    ok_home = build_home(home_folder)

    ok_prim = False
    if not args.solo_home:
        print("== Primicias H en español ==")
        ok_prim = build_primicias(args.paginas, args.salida)

    # Solo se marca el run como fallido si no salió NADA (si falla una parte, se conserva la anterior y se sigue)
    if not ok_home and not ok_prim:
        sys.exit(1)


if __name__ == "__main__":
    main()
