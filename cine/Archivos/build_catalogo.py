#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma, para la app Nimaru, el Catálogo y los Géneros del modo privado ya listos para descargar (en vez de que el
celular pida página por página). Salen de HENTAILA (hentaila.io), donde se mudó VeoHentai: mismos episodios y mismos
slugs, imágenes en /uploads/.

  cine/Archivos/catalogo.json   TODOS los episodios del sitio (el inicio, página por página: de más nuevo a más viejo),
                                con su póster, estudio, año e imagen horizontal; más la lista de estudios y de años.
  cine/Archivos/generos.json    Los géneros de /generos/ con su miniatura (póster del primer episodio), su imagen
                                propia, la primera página de episodios y la lista COMPLETA de episodios (slugs; los
                                datos de cada uno están en catalogo.json). "porPagina" = episodios por página.

Mismo formato que armaba el script de VeoHentai, para que la app lo lea igual. Lo que Hentaila no pone en las tarjetas
(estudio, año e imagen horizontal) se completa con la página de cada episodio, pero solo de los episodios nuevos (unas
decenas por corrida) y se conserva lo que ya estaba en el catalogo.json anterior.

Cada JSON lleva "ts" (cuándo se armó). Solo se reescribe si cambió el contenido (o si el anterior tiene más de 12 h),
así el repo no crece con subidas iguales. Si una página falla o salen muy pocos episodios, NO se escribe un catálogo
incompleto: se conserva el anterior (y el programa termina con código 1, para que el workflow lo reintente).

No se arma el género «Lolicon» ni «Shota» (no se listan en generos.json).

Uso:  python cine/Archivos/build_catalogo.py                       (lo corre GitHub Actions)
      python cine/Archivos/build_catalogo.py --carpeta cine/Archivos --presupuesto 60
"""
import argparse
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_primicias as bp          # los mismos lectores de Hentaila que usa el Home (tarjetas, miniatura, descarga)

HENTAILA = bp.HENTAILA
POR_PAGINA = 40                       # tarjetas por página en Hentaila (inicio y géneros)
MAX_PAGINAS = 150                     # tope de seguridad al recorrer un listado
MIN_ITEMS = 200                       # menos episodios que estos = error del sitio, no un catálogo
FRACCION_MIN = 0.9                    # si salen menos del 90 % de los que ya había, algo falló: no se pisa
PRESUPUESTO = 120                     # páginas de episodio (estudio, año, imagen horizontal) que se piden por corrida
REESCRIBIR_CADA_MS = 12 * 60 * 60 * 1000
PARALELO = 3                          # peticiones a la vez
PAUSA_S = 0.15                        # pausa tras cada petición (para no apurar al sitio)
GENEROS_EXCLUIDOS = {"lolicon", "shota"}

_SAFE = "/:?&=%#+@!$'()*,;~-._[]"


# ── Descarga de listados ────────────────────────────────────────────────────────────────────────────────────

def _ruta(base, n):
    """/  →  /?page=N ;  /genero/anal/  →  /genero/anal/?page=N"""
    return base if n <= 1 else f"{base}?page={n}"


def total_paginas(html):
    """La última página que anuncia la paginación (1 si no hay)."""
    soup = bp._soup(html)
    n = 1
    for a in soup.select('a[href*="page="]'):
        m = re.search(r"[?&]page=(\d+)", bp._attr(a, "href"))
        if m:
            n = max(n, int(m.group(1)))
    return n


def tarjetas_pagina(url, intentos=3):
    """(tarjetas, html) de una página de listado, o (None, None) si no hubo manera. Si alguna tarjeta llega con el aviso
    de «sin portada» (el sitio lo pone a veces de pasada), se vuelve a pedir y se completan las portadas que faltaban."""
    mejor, html_ok = None, None
    for i in range(intentos):
        html = bp._get_hentaila_page(url)
        with bp._hentaila_lock:
            bp._hentaila_pages.pop(url, None)         # que el siguiente intento vuelva a pedirla de verdad
        time.sleep(PAUSA_S)
        cards = []
        if html:
            try:
                cards = bp.parse_hentaila_cards(html)
            except Exception as e:
                print(f"  No se pudo leer {url}: {e}", file=sys.stderr)
        if not cards:
            time.sleep(1.5 * (i + 1))
            continue
        if mejor is None:
            mejor, html_ok = cards, html
        else:
            por = {c["slug"]: c for c in cards}
            for c in mejor:
                if c["imageUrl"] is None and por.get(c["slug"], {}).get("imageUrl"):
                    c["imageUrl"] = por[c["slug"]]["imageUrl"]
        if all(c["imageUrl"] for c in mejor):
            break
        time.sleep(1.0)
    return mejor, html_ok


def recorrer(base, max_paginas=MAX_PAGINAS):
    """Todas las páginas de un listado (en orden). (tarjetas, paginas) o None si alguna página no se pudo leer.
    Las tarjetas repetidas (el mismo episodio en dos páginas porque el listado se movió mientras se leía) se quitan."""
    c1, h1 = tarjetas_pagina(HENTAILA + _ruta(base, 1))
    if c1 is None:
        print(f"  {base}: la primera página no responde", file=sys.stderr)
        return None
    paginas = max(1, min(total_paginas(h1), max_paginas))
    por_pagina = {1: c1}
    if paginas > 1:
        with ThreadPoolExecutor(max_workers=PARALELO) as pool:
            for n, (cards, _h) in zip(range(2, paginas + 1),
                                      pool.map(lambda n: tarjetas_pagina(HENTAILA + _ruta(base, n)), range(2, paginas + 1))):
                if cards is None:
                    print(f"  {base}: la página {n} no responde", file=sys.stderr)
                    return None
                por_pagina[n] = cards
    vistos, out = set(), []
    for n in range(1, paginas + 1):
        for c in por_pagina[n]:
            if c["slug"] not in vistos:
                vistos.add(c["slug"])
                out.append(c)
    return out, paginas


# ── Página de un episodio: estudio, año, serie e imagen horizontal ─────────────────────────────────────────────

def parse_ficha(html, slug):
    """De la página /ver/<slug>/: {"studioSlug", "studioName", "year", "seriesName", "backdropUrl"}
    (lo que no sale queda vacío / 0 / None)."""
    soup = bp._soup(html)
    out = {"studioSlug": "", "studioName": "", "year": 0, "seriesName": "", "backdropUrl": None}
    filas = {}
    for fila in soup.select(".r_item"):
        spans = fila.find_all("span", recursive=False)
        if len(spans) >= 2:
            filas.setdefault(bp._jsoup_text(spans[0]).strip().lower(), spans[1])
    est = filas.get("estudio")
    a = est.select_one('a[href*="/brand/"]') if est is not None else None
    if a is None:                               # si cambiara el rótulo «Estudio»: el de la ficha de ESTE episodio, no el de los relacionados
        a = soup.select_one('.r_info_b a[href*="/brand/"]')
    if a is not None:
        m = re.search(r"/brand/([^/?#]+)", bp._attr(a, "href"))
        if m:
            out["studioSlug"] = m.group(1)
            out["studioName"] = bp._jsoup_text(a).strip()
    for clave in ("fecha de estreno", "fecha de publicación", "fecha de publicacion"):
        celda = filas.get(clave)
        m = re.search(r"\b(\d{4})-\d{2}-\d{2}\b", bp._jsoup_text(celda)) if celda is not None else None
        if m:
            out["year"] = int(m.group(1))
            break
    ser = filas.get("series")
    a = ser.select_one('a[href*="/serie/"]') if ser is not None else None
    if a is not None:
        out["seriesName"] = bp._jsoup_text(a).strip()
    out["backdropUrl"] = bp.parse_hentaila_miniatura(html, slug)
    return out


def anio_de_subida(url):
    """El año en que se subió la portada (…/uploads/2024/05/x.jpg → 2024): último recurso si la página no trae fecha."""
    m = re.search(r"/uploads/((?:19|20)\d{2})/", url or "")
    return int(m.group(1)) if m else 0


# ── Directorio de estudios y lista de géneros ──────────────────────────────────────────────────────────────

def parse_estudios(html):
    """{slug: nombre} de /directorio-hentai/ (la lista «Estudios»). {} si no sale."""
    soup = bp._soup(html)
    out = {}
    for a in soup.select('ul.browse_studios a[href*="/brand/"]'):
        m = re.search(r"/brand/([^/?#]+)", bp._attr(a, "href"))
        sp = a.find("span")
        nombre = bp._jsoup_text(sp).strip() if sp is not None else ""
        if m and nombre:
            out.setdefault(m.group(1), nombre)
    return out


def _imagen_de_estilo(el, base):
    """La url(…) de un style="background:url(…)…"; None si no hay."""
    m = re.search(r"url\(\s*[\"']?([^\"')]+)", bp._attr(el, "style")) if el is not None else None
    if not m:
        return None
    return quote(bp.urljoin(base, m.group(1).strip()), safe=_SAFE)


def parse_generos(html):
    """Los géneros de /generos/ en su orden: [{"slug","name","description","image","count"}]."""
    soup = bp._soup(html)
    base = bp._doc_base(soup, HENTAILA + "/")
    out, vistos = [], set()
    for a in soup.select("a.cat_item"):
        m = re.search(r"/genero/([^/?#]+)", bp._attr(a, "href"))
        if not m or m.group(1) in vistos:
            continue
        slug = m.group(1)
        nombre = bp._jsoup_text(bp._select_first(a, ".cat_ttl")).strip()
        if not nombre:
            continue
        vistos.add(slug)
        cuenta = re.search(r"\d[\d.,]*", bp._jsoup_text(bp._select_first(a, ".cat_count")))
        out.append({"slug": slug, "name": nombre,
                    "description": bp._jsoup_text(bp._select_first(a, ".cat_dsc")).strip(),
                    "image": _imagen_de_estilo(bp._select_first(a, ".cat_ico"), base) or _imagen_de_estilo(bp._select_first(a, ".cat_bg"), base),
                    "count": int(re.sub(r"\D", "", cuenta.group())) if cuenta else 0})
    return out


# ── Catálogo ──────────────────────────────────────────────────────────────────────────────────────────────

def _de_hentaila(url):
    """Las direcciones del sitio viejo (veohentai.com/media/X) pasan a las de Hentaila (hentaila.io/uploads/X)."""
    if not url:
        return url
    m = bp._VEO_MEDIA.match(str(url))
    return quote(HENTAILA + "/uploads/" + m.group(1), safe=_SAFE) if m else url


def _cargar(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clave(slug):
    """El slug con los %xx en mayúsculas: el sitio escribe a veces %e2 y a veces %E2 para el mismo episodio (es la misma
    dirección) y, si se compararan tal cual, ese episodio perdería su id, su estudio, su año y su imagen horizontal."""
    return re.sub(r"%[0-9a-fA-F]{2}", lambda m: m.group().upper(), slug or "")


def armar_items(tarjetas, previo):
    """Los episodios del catálogo, uno por tarjeta y en su orden. De cada slug que ya estaba se conserva lo que el sitio no
    pone en la tarjeta (id, serie, estudio, año, imagen horizontal). (items, omitidos): los omitidos no tienen portada."""
    items, omitidos = [], 0
    previo = {_clave(s): p for s, p in previo.items()}
    for c in tarjetas:
        p = previo.get(_clave(c["slug"])) or {}
        imagen = c["imageUrl"] or _de_hentaila(p.get("imageUrl"))
        if not imagen:
            omitidos += 1
            continue
        items.append({"id": int(p.get("id") or 0), "slug": c["slug"], "title": c["title"], "episode": c["episode"],
                      "seriesName": p.get("seriesName") or c["seriesName"], "imageUrl": imagen,
                      "studioSlug": p.get("studioSlug") or "", "year": int(p.get("year") or 0),
                      "backdropUrl": _de_hentaila(p.get("backdropUrl")) or None})
    return items, omitidos


def completar_fichas(items, presupuesto, estudios_nombres):
    """Pide la página de los episodios sin año (los nuevos) y les pone estudio, año, serie e imagen horizontal.
    Como mucho `presupuesto` por corrida; el resto queda para la siguiente. Devuelve cuántos completó."""
    pendientes = [it for it in items if not it["year"]][:presupuesto]
    if not pendientes:
        return 0

    def uno(it):
        html = bp._get_hentaila_page(f"{HENTAILA}/ver/{it['slug']}/")
        time.sleep(PAUSA_S)
        if not html:
            return it, None
        try:
            return it, parse_ficha(html, it["slug"])
        except Exception as e:
            print(f"  No se pudo leer la página de {it['slug']}: {e}", file=sys.stderr)
            return it, None

    hechos = 0
    with ThreadPoolExecutor(max_workers=PARALELO) as pool:
        for it, f in pool.map(uno, pendientes):
            if f is None:
                continue
            it["studioSlug"] = f["studioSlug"]
            if f["studioSlug"] and f["studioName"]:
                estudios_nombres.setdefault(f["studioSlug"], f["studioName"])
            it["year"] = f["year"] or anio_de_subida(it["imageUrl"])
            if f["backdropUrl"]:
                it["backdropUrl"] = f["backdropUrl"]
            if f["seriesName"] and not it["seriesName"]:
                it["seriesName"] = f["seriesName"]
            hechos += 1
    print(f"  Fichas completadas: {hechos} de {len(pendientes)} pedidas ({sum(1 for it in items if not it['year'])} siguen pendientes)")
    return hechos


def _nombre_de_slug(slug):
    return " ".join(w[:1].upper() + w[1:] for w in slug.replace("-", " ").split())


def build_catalogo(previo_doc, presupuesto=PRESUPUESTO, max_paginas=MAX_PAGINAS):
    """El catálogo completo (dict para escribir) o None si no se pudo armar."""
    previo_items = (previo_doc or {}).get("items") or []
    previo = {it["slug"]: it for it in previo_items if isinstance(it, dict) and it.get("slug")}
    r = recorrer("/", max_paginas)
    if r is None:
        return None
    tarjetas, paginas = r
    items, omitidos = armar_items(tarjetas, previo)
    print(f"Catálogo: {len(tarjetas)} episodios en {paginas} páginas" + (f" ({omitidos} sin portada, omitidos)" if omitidos else ""))
    minimo = max(MIN_ITEMS, int(FRACCION_MIN * len(previo_items)))
    if len(items) < minimo:
        print(f"Salieron solo {len(items)} episodios (hacen falta al menos {minimo}): parece un fallo del sitio, "
              f"se conserva el catálogo anterior", file=sys.stderr)
        return None

    nombres = {}
    for e in (previo_doc or {}).get("estudios") or []:
        if isinstance(e, dict) and e.get("slug") and e.get("name"):
            nombres[e["slug"]] = e["name"]
    html_dir = bp._get_hentaila_page(HENTAILA + "/directorio-hentai/")
    if html_dir:
        try:
            nombres.update(parse_estudios(html_dir))
        except Exception as e:
            print(f"  No se pudo leer el directorio de estudios: {e}", file=sys.stderr)
    completar_fichas(items, presupuesto, nombres)

    usados = sorted({it["studioSlug"] for it in items if it["studioSlug"]})
    estudios = sorted(({"slug": s, "name": nombres.get(s) or _nombre_de_slug(s)} for s in usados), key=lambda e: e["name"].lower())
    anios = sorted({it["year"] for it in items if it["year"]}, reverse=True)
    return {"items": items, "extra": {"paginas": paginas, "porPagina": POR_PAGINA, "estudios": estudios, "anios": anios}}


# ── Géneros ───────────────────────────────────────────────────────────────────────────────────────────────

def _item_corto(c):
    """Un episodio de una tarjeta, con el formato del catálogo, para cuando el género lista uno que el catálogo no tiene."""
    return {"id": 0, "slug": c["slug"], "title": c["title"], "episode": c["episode"], "seriesName": c["seriesName"],
            "imageUrl": c["imageUrl"], "studioSlug": "", "year": 0}


def build_generos(previo_doc, items_por_slug, max_paginas=MAX_PAGINAS):
    """Los géneros (dict para escribir) o None si no se pudieron armar. De cada género solo se vuelve a recorrer lo que
    cambió de tamaño desde la vez anterior (un episodio nuevo mueve unos pocos géneros)."""
    html = bp._get_hentaila_page(HENTAILA + "/generos/")
    if not html:
        print("Géneros: /generos/ no responde", file=sys.stderr)
        return None
    try:
        lista = [g for g in parse_generos(html) if g["slug"] not in GENEROS_EXCLUIDOS]
    except Exception as e:
        print(f"Géneros: no se pudo leer /generos/: {e}", file=sys.stderr)
        return None
    if len(lista) < 5:
        print(f"Géneros: solo salieron {len(lista)}, parece un fallo del sitio", file=sys.stderr)
        return None
    previo = {g["slug"]: g for g in (previo_doc or {}).get("items") or [] if isinstance(g, dict) and g.get("slug")}
    out, recorridos = [], 0
    for g in lista:
        p = previo.get(g["slug"]) or {}
        slugs, primera, thumb, paginas = None, None, None, 1
        episodios = g["count"]
        if p.get("slugs") and p.get("episodios") == g["count"] and p.get("thumb"):
            slugs, thumb, paginas = list(p["slugs"]), _de_hentaila(p["thumb"]), int(p.get("pageCount") or 1)
        else:
            r = recorrer(f"/genero/{g['slug']}/", max_paginas)
            if r is None:
                if p.get("slugs"):
                    print(f"  Género {g['slug']}: no responde, se conserva el anterior", file=sys.stderr)
                    slugs, thumb, paginas = list(p["slugs"]), _de_hentaila(p.get("thumb")), int(p.get("pageCount") or 1)
                    episodios = p.get("episodios") or 0         # sigue con la cuenta vieja: la próxima corrida lo vuelve a intentar
                else:
                    print(f"  Género {g['slug']}: no responde y no hay anterior: se omite", file=sys.stderr)
                    continue
            else:
                tarjetas, paginas = r
                slugs = [c["slug"] for c in tarjetas]
                thumb = next((c["imageUrl"] for c in tarjetas if c["imageUrl"]), None)
                primera = tarjetas[:POR_PAGINA]
                recorridos += 1
        if primera is not None:
            items = [items_por_slug.get(c["slug"]) or (_item_corto(c) if c["imageUrl"] else None) for c in primera]
        else:
            items = [items_por_slug.get(s) for s in slugs[:POR_PAGINA]]
        items = [{k: v for k, v in i.items() if v is not None} for i in items if i]
        out.append({"slug": g["slug"], "name": g["name"], "description": g["description"],
                    "image": g["image"], "thumb": thumb, "pageCount": paginas, "episodios": episodios,
                    "items": items, "slugs": slugs})
    print(f"Géneros: {len(out)} (recorridos de nuevo: {recorridos})")
    if len(out) < max(5, int(FRACCION_MIN * len(previo))):
        print("Salieron muy pocos géneros: se conserva el archivo anterior", file=sys.stderr)
        return None
    return {"items": out, "extra": {"porPagina": POR_PAGINA}}


# ── Escritura: solo si cambió (o si la fecha anterior tiene más de 12 h) ─────────────────────────────────────────

def _limpiar(items):
    return [{k: v for k, v in it.items() if v is not None} for it in items]


def write_if_changed(path, doc_parcial):
    prev = _cargar(path)
    now_ms = int(time.time() * 1000)
    nuevos = _limpiar(doc_parcial["items"])
    extra = doc_parcial.get("extra") or {}
    if (prev is not None and prev.get("items") == nuevos and all(prev.get(k) == v for k, v in extra.items())
            and now_ms - int(prev.get("ts") or 0) < REESCRIBIR_CADA_MS):
        print(f"  {path}: sin cambios, no se reescribe")
        return False
    doc = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": now_ms, "total": len(nuevos)}
    doc.update(extra)
    doc["items"] = nuevos
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"  Escrito {path} ({len(nuevos)} elementos)")
    return True


def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--carpeta", default="cine/Archivos")
    ap.add_argument("--presupuesto", type=int, default=PRESUPUESTO, help="páginas de episodio a pedir por corrida")
    ap.add_argument("--max-paginas", type=int, default=MAX_PAGINAS)
    ap.add_argument("--solo", choices=["catalogo", "generos"], default=None, help="armar solo uno (para probar)")
    args = ap.parse_args()
    if not bp._BS4:
        print("Falta beautifulsoup4 (pip install beautifulsoup4 html5lib)", file=sys.stderr)
        sys.exit(1)
    ruta_cat = os.path.join(args.carpeta, "catalogo.json")
    ruta_gen = os.path.join(args.carpeta, "generos.json")

    pedidos, ok = 0, 0
    t0 = time.time()
    previo_cat = _cargar(ruta_cat)
    items_por_slug = {it["slug"]: it for it in (previo_cat or {}).get("items") or [] if isinstance(it, dict) and it.get("slug")}
    if args.solo != "generos":
        pedidos += 1
        print("== Catálogo ==")
        cat = build_catalogo(previo_cat, args.presupuesto, args.max_paginas)
        if cat is not None:
            print(f"Catálogo armado en {time.time() - t0:.0f} s")
            write_if_changed(ruta_cat, cat)
            items_por_slug = {it["slug"]: it for it in cat["items"]}
            ok += 1
    if args.solo != "catalogo":
        pedidos += 1
        print("== Géneros ==")
        t1 = time.time()
        gen = build_generos(_cargar(ruta_gen), items_por_slug, args.max_paginas)
        if gen is not None:
            print(f"Géneros armados en {time.time() - t1:.0f} s")
            write_if_changed(ruta_gen, gen)
            ok += 1
    if ok < pedidos:                  # lo que sí salió ya quedó escrito; el código 1 es para que el workflow lo reintente
        sys.exit(1)


if __name__ == "__main__":
    main()
