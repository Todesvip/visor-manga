#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Arma, para la app Nimaru, el Catálogo y los Géneros del modo privado ya listos para descargar (en vez de que el
celular pida página por página). El catálogo sale de VEOHENTAI (veohentai.com) y, si no responde, de HENTAILA
(hentaila.io); los géneros, de Hentaila.

  cine/Archivos/catalogo.json   TODOS los episodios del sitio (el inicio, página por página: de más nuevo a más viejo),
                                con su póster, estudio, año e imagen horizontal; más la lista de estudios y de años.
  cine/Archivos/generos.json    Los géneros de /generos/ con su miniatura (póster del primer episodio), su imagen
                                propia, la primera página de episodios y la lista COMPLETA de episodios (slugs; los
                                datos de cada uno están en catalogo.json). "porPagina" = episodios por página.
  cine/Archivos/ediciones.json  Copia de lo que el staff editó desde la app (Firebase /ediciones): póster, logo y
                                descripción de una serie y la descripción de cada episodio. Los pósters editados entran
                                al catálogo (todos los episodios de esa serie): así se ven también en Explorar y la lupa.

VeoHentai volvió (veohentai.com): es la fuente principal del catálogo porque trae TODAS las portadas y, en la misma tarjeta,
el estudio, el año y la imagen horizontal (sin pedir la página de cada episodio). Si VeoHentai no responde, el catálogo se
arma desde Hentaila (hentaila.io, donde se mudó mientras estuvo caído: mismos episodios y mismos slugs). Las imágenes son
las mismas en los dos sitios (veohentai.com/media/X ↔ hentaila.io/uploads/X): una portada muerta en uno se busca en el otro.

Mismo formato que armaba el script de VeoHentai, para que la app lo lea igual. Lo que Hentaila no pone en las tarjetas
(estudio, año e imagen horizontal) se completa con la página de cada episodio, pero solo de los episodios nuevos (unas
decenas por corrida) y se conserva lo que ya estaba en el catalogo.json anterior.

Antes de escribir se comprueba que cada portada exista de verdad (unos 20 s con las 2541): la que el sitio dice que no existe
se cambia por la del mismo episodio en hstream.moe o, si ahí no está, por la de otro episodio de la serie.

Las portadas se copian a ImgBB (cine/Archivos/espejo.json: dirección original → copia) y el catálogo lleva la copia, así la
app no depende de Hentaila para las imágenes. Se suben de a tandas por corrida (las que aún no tienen copia), con la clave
del secreto IMGBB_KEY (sin clave solo se usan las copias que ya hay). Cada corrida comprueba que las copias sigan existiendo:
la que murió vuelve a la original (y se vuelve a subir); si casi todas murieron (ImgBB caído o la cuenta cerrada) esa
corrida no se usa el espejo.

Hentaila frena a quien pide muy seguido desde GitHub (páginas que se quedan colgadas o dan 520 de pasada, aunque desde un
navegador carguen al instante). Por eso se pide de a 2 con pausa, una página colgada se corta a los 20 s y se vuelve a pedir,
las que no respondieron se repescan de una en una esperando cada vez más, y las fichas y la revisión de portadas (extras)
tienen un tiempo máximo por corrida.

Cada JSON lleva "ts" (cuándo se armó). Solo se reescribe si cambió el contenido (o si el anterior tiene más de 12 h),
así el repo no crece con subidas iguales. Si una página falla o salen muy pocos episodios, NO se escribe un catálogo
incompleto: se conserva el anterior (y el programa termina con código 1, para que el workflow lo reintente).

No se arma el género «Lolicon» ni «Shota» (no se listan en generos.json).

Uso:  python cine/Archivos/build_catalogo.py                       (lo corre GitHub Actions)
      python cine/Archivos/build_catalogo.py --carpeta cine/Archivos --presupuesto 60
"""
import argparse
import base64
import json
import math
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import quote, unquote

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_primicias as bp          # los mismos lectores de Hentaila que usa el Home (tarjetas, miniatura, descarga)

HENTAILA = bp.HENTAILA
POR_PAGINA = 40                       # tarjetas por página en Hentaila (inicio y géneros)
MAX_PAGINAS = 150                     # tope de seguridad al recorrer un listado
MIN_ITEMS = 200                       # menos episodios que estos = error del sitio, no un catálogo
FRACCION_MIN = 0.9                    # si salen menos del 90 % de los que ya había, algo falló: no se pisa
PRESUPUESTO = 120                     # páginas de episodio (estudio, año, imagen horizontal) que se piden por corrida
REESCRIBIR_CADA_MS = 12 * 60 * 60 * 1000
PARALELO = 2                          # peticiones a la vez (desde GitHub, Hentaila frena a quien pide muy seguido)
PAUSA_S = 0.5                         # pausa tras cada petición (para no apurar al sitio)
LISTADO_TIMEOUT_S = 20                # una página que tarda más que esto se da por colgada y se vuelve a pedir (las buenas tardan < 2 s)
LISTADO_TIEMPO_MAX_S = 600            # la primera pasada por un listado no pasa de 10 min: lo que falte va a la repesca
REPESCA_ESPERA_S = 10                 # las páginas que no respondieron se vuelven a pedir de una en una, esperando 10, 20, 40… s
REPESCA_RONDAS = 5                    # …hasta 5 rondas
REPESCA_TIEMPO_MAX_S = 240            # …y sin pasar de 4 min
FICHAS_TIEMPO_MAX_S = 300             # las fichas (estudio, año, imagen horizontal) son un extra: no pasan de 5 min por corrida
PORTADAS_TIEMPO_MAX_S = 300           # la revisión de portadas tampoco (lo que no se alcanzó a comprobar no se toca)
PORTADA_TIMEOUT_S = 15                # una portada que tarda más que esto se da por colgada (las buenas salen del caché en < 1 s)
IMGBB_API = "https://api.imgbb.com/1/upload"
ESPEJO_POR_CORRIDA = 300              # portadas que se suben a ImgBB por corrida (las que aún no tienen copia), de una en una
ESPEJO_PAUSA_S = 0.5                  # pausa entre subidas
ESPEJO_TIEMPO_MAX_S = 600             # comprobar las copias + subir: tope por corrida (10 min); lo que falte, en la siguiente
ESPEJO_COMPROBAR_POR_CORRIDA = 150    # copias que se comprueban por corrida: una tanda distinta cada vez (todas, en unos días)
ESPEJO_COMPROBAR_TIEMPO_S = 120       # …y como mucho 2 min, para que quede tiempo de subir
ESPEJO_TANDA_CADA_S = 6 * 60 * 60     # la tanda avanza cada 6 h (lo que tarda en volver a correr el catálogo)
ESPEJO_FALLOS_SEGUIDOS = 5            # con 5 subidas seguidas fallidas ImgBB no está respondiendo: se deja para la siguiente
ESPEJO_MUERTAS_MIN = 10               # si no existen más de la mitad de las copias (y al menos 10), ImgBB está caído o la cuenta
                                      # cerrada: esa corrida se usan las originales (y no se borra nada del espejo)
IMAGEN_MAX_BYTES = 32 * 1024 * 1024   # tope de ImgBB
GENEROS_EXCLUIDOS = {"lolicon", "shota"}
HSTREAM = "https://hstream.moe/images/hentai"     # portadas de respaldo: <serie>/cover-ep-<N>.webp (verticales, 268×394)
VEO = bp.VEO                                      # https://veohentai.com: la fuente principal del catálogo
EDICIONES_URL = "https://void-670de-default-rtdb.firebaseio.com/ediciones.json"   # lo que el staff editó desde la app (Firebase; lectura pública)
_IMGBB = re.compile(r"^https://i\.ibb\.co(?:\.com)?/[A-Za-z0-9_.~%+/-]+$")
_HENTAILA_UPLOADS = re.compile(r"^https?://(?:www\.)?hentaila\.io/uploads/(.+)$", re.I)
PARALELO_IMG = 4                      # portadas de Hentaila que se comprueban a la vez (sin apurar al sitio)
PARALELO_ESPEJO = 4                   # copias en ImgBB que se comprueban a la vez (ImgBB también frena las ráfagas)
PORTADAS_POR_CORRIDA = 400            # portadas de Hentaila que se comprueban por corrida, de la más nueva a la más vieja
MUERTAS_FRACCION = 0.05               # si el sitio dice «no existe» de más del 5 % de las portadas, es un bloqueo: no se cambia nada
MUERTAS_TOPE_MIN = 25                 # (y nunca menos de 25, para que un catálogo chico no se bloquee por una o dos)
HERMANAS_MAX = 3                      # portadas de otros episodios de la serie que se prueban como último remedio

_SAFE = "/:?&=%#+@!$'()*,;~-._[]"
_SERIE_Y_EPISODIO = re.compile(r"^(.+)-episodio-(\d+)$")
_MAGIA_IMAGEN = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")      # jpg, png, gif y webp
_img_local = threading.local()


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


def tarjetas_pagina(url, intentos=3, limite=None):
    """(tarjetas, html) de una página de listado, o (None, None) si no hubo manera. Si alguna tarjeta llega con el aviso
    de «sin portada» (el sitio lo pone a veces de pasada), se vuelve a pedir y se completan las portadas que faltaban.
    `limite` (time.monotonic): pasado ese momento no se intenta más (lo que falte lo recoge la repesca)."""
    mejor, html_ok = None, None
    for i in range(intentos):
        if limite is not None and time.monotonic() > limite:
            break
        html = bp._get_hentaila_page(url, timeout=LISTADO_TIMEOUT_S)
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


def _repescar(pedir, faltan):
    """Las páginas que no respondieron en la primera pasada se vuelven a pedir de una en una y con calma: antes de cada
    ronda se espera REPESCA_ESPERA_S, el doble, el doble… (Hentaila frena a quien pide muy seguido desde GitHub y, al rato,
    vuelve a responder). `pedir(n)` → tarjetas de la página n o None. {n: tarjetas} de las que respondieron."""
    out, pendientes = {}, list(faltan)
    limite = time.monotonic() + REPESCA_TIEMPO_MAX_S
    espera = REPESCA_ESPERA_S
    for _ronda in range(REPESCA_RONDAS):
        if not pendientes or time.monotonic() > limite:
            break
        time.sleep(espera)
        espera *= 2
        for n in list(pendientes):
            if time.monotonic() > limite:
                break
            cards = pedir(n)
            if cards is not None:
                out[n] = cards
                pendientes.remove(n)
    return out


def _pagina_veo(n, intentos=3, limite=None):
    """(tarjetas, páginas) de la página n de /explorar/ de VeoHentai (cada tarjeta ya trae id, serie, estudio, año, portada e
    imagen horizontal), o (None, None) si no hubo manera. Si el formato cambiara, el HTML visible (sin estudio ni año)."""
    url = VEO + "/explorar/" + ("" if n <= 1 else f"?pagina={n}")
    for i in range(intentos):
        if limite is not None and time.monotonic() > limite:
            break
        html = bp._get_text_page(url, bp.VEO_HEADERS)
        time.sleep(PAUSA_S)
        if html:
            try:
                stream = bp._rsc_stream(html)
                tarjetas = bp._parse_items(stream)
                if tarjetas:
                    m = re.search(r'"pageCount":(\d+)', stream[max(stream.find('"initial":['), 0):])
                    return tarjetas, (int(m.group(1)) if m else 1)
                tarjetas = bp._parse_explore_dom(html)
                if tarjetas:
                    paginas = [int(x) for x in re.findall(r"[?&]pagina=(\d+)", html)]
                    return tarjetas, (max(paginas) if paginas else 1)
            except Exception as e:
                print(f"  No se pudo leer {url}: {e}", file=sys.stderr)
        time.sleep(1.5 * (i + 1))
    return None, None


def recorrer_veo(max_paginas=MAX_PAGINAS):
    """Todas las páginas de /explorar/ de VeoHentai, en orden: (tarjetas, páginas, por_página) o None si alguna página no
    se pudo leer ni en la repesca. Misma mecánica que `recorrer` (primera pasada a la vez, repesca con calma)."""
    c1, total = _pagina_veo(1)
    if not c1:
        print("  VeoHentai: la primera página de /explorar/ no responde", file=sys.stderr)
        return None
    paginas = max(1, min(total, max_paginas))
    por_pagina = {1: c1}
    faltan = []
    if paginas > 1:
        limite = time.monotonic() + LISTADO_TIEMPO_MAX_S
        with ThreadPoolExecutor(max_workers=PARALELO) as pool:
            for n, (cards, _p) in zip(range(2, paginas + 1), pool.map(lambda n: _pagina_veo(n, limite=limite), range(2, paginas + 1))):
                if cards is None:
                    faltan.append(n)
                else:
                    por_pagina[n] = cards
    if faltan:
        print(f"  VeoHentai: no respondieron {len(faltan)} páginas ({', '.join(map(str, faltan[:8]))}{'…' if len(faltan) > 8 else ''}): "
              "se vuelven a pedir de una en una, con calma", file=sys.stderr)
        por_pagina.update(_repescar(lambda n: _pagina_veo(n, intentos=1)[0], faltan))
        faltan = [n for n in faltan if n not in por_pagina]
        if faltan:
            print(f"  VeoHentai: la página {faltan[0]} no responde", file=sys.stderr)
            return None
    vistos, out = set(), []
    for n in range(1, paginas + 1):
        for c in por_pagina[n]:
            if c["slug"] not in vistos:
                vistos.add(c["slug"])
                out.append(c)
    return out, paginas, len(c1)


def recorrer(base, max_paginas=MAX_PAGINAS):
    """Todas las páginas de un listado (en orden). (tarjetas, paginas) o None si alguna página no se pudo leer ni en la
    repesca. Las tarjetas repetidas (el mismo episodio en dos páginas porque el listado se movió mientras se leía) se quitan."""
    c1, h1 = tarjetas_pagina(HENTAILA + _ruta(base, 1))
    if c1 is None:
        print(f"  {base}: la primera página no responde", file=sys.stderr)
        return None
    paginas = max(1, min(total_paginas(h1), max_paginas))
    por_pagina = {1: c1}
    faltan = []
    if paginas > 1:
        limite = time.monotonic() + LISTADO_TIEMPO_MAX_S
        with ThreadPoolExecutor(max_workers=PARALELO) as pool:
            for n, (cards, _h) in zip(range(2, paginas + 1),
                                      pool.map(lambda n: tarjetas_pagina(HENTAILA + _ruta(base, n), limite=limite), range(2, paginas + 1))):
                if cards is None:
                    faltan.append(n)
                else:
                    por_pagina[n] = cards
    if faltan:
        print(f"  {base}: no respondieron {len(faltan)} páginas ({', '.join(map(str, faltan[:8]))}{'…' if len(faltan) > 8 else ''}): "
              "se vuelven a pedir de una en una, con calma", file=sys.stderr)
        por_pagina.update(_repescar(lambda n: tarjetas_pagina(HENTAILA + _ruta(base, n), intentos=1)[0], faltan))
        faltan = [n for n in faltan if n not in por_pagina]
        if faltan:
            print(f"  {base}: la página {faltan[0]} no responde", file=sys.stderr)
            return None
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
    """El año en que se subió la portada (…/uploads/2024/05/x.jpg o …/media/2024/05/x.jpg → 2024): último recurso si la
    página no trae fecha."""
    m = re.search(r"/(?:uploads|media)/((?:19|20)\d{2})/", url or "")
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
    """Las direcciones de VeoHentai (veohentai.com/media/X) en su forma de Hentaila (hentaila.io/uploads/X): es la forma
    «canónica» con la que se guardan las copias del espejo, venga la portada del sitio que venga. Lo demás, tal cual."""
    if not url:
        return url
    m = bp._VEO_MEDIA.match(str(url))
    return quote(HENTAILA + "/uploads/" + m.group(1), safe=_SAFE) if m else url


def _gemela(url):
    """La misma imagen en el otro sitio (veohentai.com/media/X ↔ hentaila.io/uploads/X); None si no es de ninguno."""
    u = str(url or "")
    m = bp._VEO_MEDIA.match(u)
    if m:
        return quote(HENTAILA + "/uploads/" + m.group(1), safe=_SAFE)
    m = _HENTAILA_UPLOADS.match(u)
    return quote(VEO + "/media/" + m.group(1), safe=_SAFE) if m else None


def _referer_de(url):
    """El Referer con el que se pide una imagen: el de su propio sitio."""
    u = str(url or "")
    if "hstream.moe" in u:
        return "https://hstream.moe/"
    if bp._VEO_MEDIA.match(u):
        return VEO + "/"
    return HENTAILA + "/"


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


def armar_items(tarjetas, previo, completas=False):
    """Los episodios del catálogo, uno por tarjeta y en su orden. Con `completas` (tarjetas de VeoHentai: traen id, serie,
    estudio, año e imagen horizontal) manda lo que trae la tarjeta; si no (las de Hentaila solo traen título y portada, y
    la serie se deduce del título) se conserva lo que ya estaba en el catálogo anterior. Una tarjeta sin portada usa la
    del catálogo anterior. (items, omitidos): los omitidos no tienen portada en ningún lado."""
    items, omitidos = [], 0
    previo = {_clave(s): p for s, p in previo.items()}
    for c in tarjetas:
        p = previo.get(_clave(c["slug"])) or {}
        imagen = c["imageUrl"] or p.get("imageUrl")
        if not imagen:
            omitidos += 1
            continue
        if completas:
            serie, estudio = c.get("seriesName") or p.get("seriesName") or "", c.get("studioSlug") or p.get("studioSlug") or ""
            ident, anio, horizontal = c.get("id") or p.get("id") or 0, c.get("year") or p.get("year") or 0, c.get("backdropUrl") or p.get("backdropUrl")
        else:
            serie, estudio = p.get("seriesName") or c.get("seriesName") or "", p.get("studioSlug") or ""
            ident, anio, horizontal = p.get("id") or 0, p.get("year") or 0, p.get("backdropUrl")
        items.append({"id": int(ident), "slug": c["slug"], "title": c["title"], "episode": c["episode"], "seriesName": serie,
                      "imageUrl": imagen, "studioSlug": estudio, "year": int(anio), "backdropUrl": horizontal or None})
    return items, omitidos


def completar_fichas(items, presupuesto, estudios_nombres):
    """Pide la página de los episodios sin año (los nuevos) y les pone estudio, año, serie e imagen horizontal.
    Como mucho `presupuesto` por corrida; el resto queda para la siguiente. Devuelve cuántos completó."""
    pendientes = [it for it in items if not it["year"]][:presupuesto]
    if not pendientes:
        return 0
    limite = time.monotonic() + FICHAS_TIEMPO_MAX_S

    def uno(it):
        if time.monotonic() > limite:                 # se acabó el tiempo: queda para la próxima corrida
            return it, None
        html = bp._get_hentaila_page(f"{HENTAILA}/ver/{it['slug']}/", timeout=LISTADO_TIMEOUT_S)
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


def _serie_y_episodio(slug):
    """«una-serie-episodio-7» → («una-serie», 7); (None, None) si el slug no termina en «-episodio-N»."""
    m = _SERIE_Y_EPISODIO.match(slug or "")
    return (m.group(1), int(m.group(2))) if m else (None, None)


def _portada_hstream(slug):
    """La portada de ese episodio en hstream.moe (puede no existir: hay que comprobarla). None si el slug no es de episodio."""
    serie, n = _serie_y_episodio(slug)
    return f"{HSTREAM}/{serie}/cover-ep-{n}.webp" if serie else None


def _portada_viva(url, limite=None):
    """¿Existe de verdad esta imagen? True: responde con una imagen. False: el sitio dice que no existe (404 o 410 dos veces
    seguidas, o una página en vez de una imagen). None: no se pudo saber (sin red, 429, 5xx, o se pasó `limite`): ahí no se
    toca nada."""
    s = getattr(_img_local, "s", None)
    if s is None:
        s = _img_local.s = requests.Session()
    cabeceras = {"User-Agent": bp.UA, "Referer": _referer_de(url), "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    no_existe = 0
    for intento in range(3):
        if limite is not None and time.monotonic() > limite:
            return None
        try:
            with s.get(url, headers=cabeceras, stream=True, timeout=PORTADA_TIMEOUT_S) as r:
                if r.status_code in (404, 410):
                    no_existe += 1
                    if no_existe >= 2:
                        return False
                elif r.status_code == 200:
                    principio = next(r.iter_content(64), b"")
                    return r.headers.get("content-type", "").startswith("image/") and principio.startswith(_MAGIA_IMAGEN)
        except Exception:
            pass
        time.sleep(1.5)
    return None


def verificar_portadas(items, saltar=()):
    """Comprueba que cada portada exista de verdad y cambia las que no. Cuando la tarjeta de Hentaila sale «sin portada» se
    deja la dirección que había antes (la del sitio viejo) y esa a veces ya no existe: el episodio sale con la tarjeta en blanco
    en la app. Para cada portada que el sitio dice que NO existe se busca, en este orden:
      1. la misma imagen en el otro sitio (veohentai.com/media/X ↔ hentaila.io/uploads/X);
      2. la portada de ese mismo episodio en hstream.moe (…/<serie>/cover-ep-<N>.webp), comprobada;
      3. la portada de otro episodio de la serie que sí exista (los más cercanos);
      4. la imagen horizontal del episodio, si existe.
    Si no hay ninguna se deja como estaba. Lo que no se pudo comprobar (red, 429, 5xx) tampoco se toca; y si el sitio dice «no
    existe» de más del 5 % de las portadas es un bloqueo, no un hueco de datos: no se cambia nada.
    Para no apurar a Hentaila se comprueban como mucho PORTADAS_POR_CORRIDA por corrida, de la más nueva a la más vieja, y
    nunca las de `saltar` (las que ya tienen copia en ImgBB, en la forma de Hentaila con que se guardan: el catálogo lleva la
    copia, y esa se comprueba aparte).
    Devuelve (cambiadas, sin_remedio, sin_comprobar)."""
    urls = [u for u in dict.fromkeys(it["imageUrl"] for it in items) if _de_hentaila(u) not in saltar][:PORTADAS_POR_CORRIDA]
    limite = time.monotonic() + PORTADAS_TIEMPO_MAX_S
    with ThreadPoolExecutor(max_workers=PARALELO_IMG) as pool:
        estado = dict(zip(urls, pool.map(lambda u: _portada_viva(u, limite), urls)))
    muertas = {u for u, v in estado.items() if v is False}
    sin_comprobar = sum(1 for v in estado.values() if v is None)
    if len(muertas) > max(MUERTAS_TOPE_MIN, int(MUERTAS_FRACCION * len(urls))):
        print(f"Portadas: {len(muertas)} de {len(urls)} «no existen»: parece un bloqueo del sitio, no se cambia ninguna", file=sys.stderr)
        return 0, len(muertas), sin_comprobar

    por_serie = {}                          # con las portadas de ANTES de cambiar nada: el orden de los episodios no importa
    for it in items:
        serie, n = _serie_y_episodio(it["slug"])
        if serie:
            por_serie.setdefault(serie, []).append((n, it["imageUrl"]))

    def viva(url):
        if url not in estado:
            estado[url] = _portada_viva(url, limite)
        return estado[url] is True

    cambiadas = sin_remedio = 0
    for it in items:
        malo = it["imageUrl"]
        if malo not in muertas:
            continue
        candidatas = [_gemela(malo), _portada_hstream(it["slug"])]
        serie, n = _serie_y_episodio(it["slug"])
        if serie:
            hermanas = sorted(((abs(m - n), m, u) for m, u in por_serie[serie] if u not in muertas), key=lambda t: t[:2])
            candidatas += [u for _, _, u in hermanas[:HERMANAS_MAX]]
        candidatas.append(it.get("backdropUrl"))
        nueva = next((u for u in candidatas if u and viva(u)), None)
        if nueva:
            print(f"  Portada muerta de {it['slug']}: {malo} → {nueva}")
            it["imageUrl"] = nueva
            cambiadas += 1
        else:
            print(f"  Portada muerta de {it['slug']} y sin remedio: {malo}", file=sys.stderr)
            sin_remedio += 1
    return cambiadas, sin_remedio, sin_comprobar


# ── Espejo de portadas en ImgBB ───────────────────────────────────────────────────────────────────────────────

def _nombre_imagen(url):
    """Un nombre de archivo limpio para la copia: «Oushun-Jogakuen-no-Danyuu-1» (ImgBB lo pone en la dirección)."""
    base = unquote(url.rsplit("/", 1)[-1].split("?")[0].rsplit(".", 1)[0])
    base = re.sub(r"-{2,}", "-", re.sub(r"[^A-Za-z0-9._-]+", "-", base)).strip("-.")
    return base[:60] or "portada"


def _bajar_imagen(url):
    """La imagen completa (bytes) o None si no responde, no es una imagen o es demasiado grande."""
    s = getattr(_img_local, "s", None)
    if s is None:
        s = _img_local.s = requests.Session()
    cabeceras = {"User-Agent": bp.UA, "Referer": _referer_de(url), "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
    try:
        with s.get(url, headers=cabeceras, stream=True, timeout=PORTADA_TIMEOUT_S) as r:
            if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                return None
            datos = b""
            for trozo in r.iter_content(65536):
                datos += trozo
                if len(datos) > IMAGEN_MAX_BYTES:
                    return None
    except Exception:
        return None
    return datos if datos.startswith(_MAGIA_IMAGEN) else None


def _subir_imgbb(datos, nombre, key):
    """Sube una imagen a ImgBB y devuelve la dirección directa de la copia (https://i.ibb.co/…) o None.
    La clave va solo en la petición: ningún mensaje la repite (el texto de un error de red trae la dirección completa)."""
    try:
        r = requests.post(IMGBB_API, params={"key": key},
                          data={"image": base64.b64encode(datos).decode("ascii"), "name": nombre}, timeout=90)
    except Exception as e:
        print(f"  ImgBB: no se pudo subir {nombre}: {type(e).__name__}", file=sys.stderr)
        return None
    try:
        j = r.json()
    except Exception:
        j = None
    if not isinstance(j, dict):
        j = {}
    data = j.get("data") if isinstance(j.get("data"), dict) else {}
    url = str(data.get("url") or "")
    if r.status_code == 200 and url.startswith("https://") and ".ibb.co/" in url:
        return url
    msg = str(j["error"].get("message") or "")[:80] if isinstance(j.get("error"), dict) else ""
    print(f"  ImgBB: HTTP {r.status_code} al subir {nombre}" + (f": {msg}" if msg else ""), file=sys.stderr)
    return None


def cargar_espejo(doc):
    """El mapa original → copia del espejo.json anterior (solo las entradas bien formadas)."""
    items = doc.get("items") if isinstance(doc, dict) else None
    if not isinstance(items, dict):
        return {}
    return {o: c for o, c in items.items() if isinstance(o, str) and isinstance(c, str)
            and o.startswith("https://") and c.startswith("https://") and ".ibb.co/" in c}


def _tanda(con_copia):
    """Las copias que se comprueban en esta corrida: todas si son pocas; si no, una ventana de ESPEJO_COMPROBAR_POR_CORRIDA
    que avanza cada ESPEJO_TANDA_CADA_S (así en unos días pasan todas, sin ráfagas que ImgBB frene)."""
    if len(con_copia) <= ESPEJO_COMPROBAR_POR_CORRIDA:
        return list(con_copia)
    desde = int(time.time() // ESPEJO_TANDA_CADA_S) * ESPEJO_COMPROBAR_POR_CORRIDA % len(con_copia)
    return (con_copia + con_copia)[desde:desde + ESPEJO_COMPROBAR_POR_CORRIDA]


def espejar(items, espejo, key):
    """Pone a cada episodio la copia de su portada en ImgBB (espejo: original → copia; se actualiza aquí mismo):
      1. se comprueba que una tanda de las copias que se van a usar siga existiendo (una tanda distinta por corrida, 2 min
         como mucho): la que no, vuelve a la original y sale del espejo (se volverá a subir); si no existen más de la
         mitad de las comprobadas, ImgBB está caído o la cuenta cerrada: esta corrida se usan las originales y el espejo
         no se toca;
      2. se suben las portadas que aún no tienen copia (hasta ESPEJO_POR_CORRIDA, mientras haya tiempo y clave);
      3. cada episodio con copia lleva la copia.
    Devuelve (con_copia, subidas, muertas, sin_comprobar)."""
    limite = time.monotonic() + ESPEJO_TIEMPO_MAX_S
    originales = list(dict.fromkeys(it["imageUrl"] for it in items))        # en el orden del catálogo: lo más nuevo primero
    con_copia = [u for u in originales if _de_hentaila(u) in espejo]       # (la copia se guarda con la forma de Hentaila: vale para los dos sitios)
    tanda = _tanda(con_copia)
    limite_comprobar = min(limite, time.monotonic() + ESPEJO_COMPROBAR_TIEMPO_S)
    with ThreadPoolExecutor(max_workers=PARALELO_ESPEJO) as pool:
        estado = dict(zip(tanda, pool.map(lambda u: _portada_viva(espejo[_de_hentaila(u)], limite_comprobar), tanda)))
    muertas = [u for u in tanda if estado[u] is False]
    sin_comprobar = sum(1 for v in estado.values() if v is None)
    if len(muertas) > max(ESPEJO_MUERTAS_MIN, len(tanda) // 2):
        print(f"Espejo: no existen {len(muertas)} de {len(tanda)} copias comprobadas: ImgBB parece caído o la cuenta cerrada; "
              "esta corrida se usan las portadas originales", file=sys.stderr)
        return 0, 0, len(muertas), sin_comprobar
    for u in muertas:
        print(f"  Espejo: la copia de {u} ya no existe: vuelve la original y se volverá a subir", file=sys.stderr)
        del espejo[_de_hentaila(u)]

    subidas = 0
    faltan = [u for u in originales if _de_hentaila(u) not in espejo and ".ibb.co/" not in u]   # (una copia heredada del catálogo anterior ya es copia)
    if faltan and not key:
        print(f"  Espejo: sin IMGBB_KEY no se sube nada ({len(faltan)} portadas sin copia)")
    elif faltan:
        seguidos = 0
        for u in faltan[:ESPEJO_POR_CORRIDA]:
            if time.monotonic() > limite:
                break
            datos = _bajar_imagen(u)
            copia = _subir_imgbb(datos, _nombre_imagen(u), key) if datos else None
            time.sleep(ESPEJO_PAUSA_S)
            if copia:
                espejo[_de_hentaila(u)] = copia
                subidas += 1
                seguidos = 0
            else:
                seguidos += 1
                if seguidos >= ESPEJO_FALLOS_SEGUIDOS:
                    print(f"  Espejo: {seguidos} subidas seguidas fallaron: se sigue en la próxima corrida", file=sys.stderr)
                    break

    con = 0
    for it in items:
        it["imageUrl"] = espejo.get(_de_hentaila(it["imageUrl"]), it["imageUrl"])
        con += ".ibb.co/" in it["imageUrl"]
    return con, subidas, len(muertas), sin_comprobar


def _nombre_de_slug(slug):
    return " ".join(w[:1].upper() + w[1:] for w in slug.replace("-", " ").split())


def build_catalogo(previo_doc, presupuesto=PRESUPUESTO, max_paginas=MAX_PAGINAS, espejo=None, key=None):
    """El catálogo completo (dict para escribir) o None si no se pudo armar. `espejo` (original → copia en ImgBB) se
    actualiza aquí mismo; None = sin espejo."""
    previo_items = (previo_doc or {}).get("items") or []
    previo = {it["slug"]: it for it in previo_items if isinstance(it, dict) and it.get("slug")}
    r = recorrer_veo(max_paginas)
    if r is not None:
        tarjetas, paginas, por_pagina = r
        fuente, completas = "VeoHentai", True
    else:
        print("Catálogo: VeoHentai no respondió: se arma desde Hentaila", file=sys.stderr)
        r = recorrer("/", max_paginas)
        if r is None:
            return None
        tarjetas, paginas = r
        por_pagina, fuente, completas = POR_PAGINA, "Hentaila", False
    items, omitidos = armar_items(tarjetas, previo, completas)
    print(f"Catálogo ({fuente}): {len(tarjetas)} episodios en {paginas} páginas" + (f" ({omitidos} sin portada, omitidos)" if omitidos else ""))
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
    try:
        cambiadas, sin_remedio, sin_comprobar = verificar_portadas(items, saltar=espejo or ())
        print(f"Portadas: {cambiadas} cambiadas" + (f", {sin_remedio} sin remedio" if sin_remedio else "")
              + (f", {sin_comprobar} sin poder comprobar" if sin_comprobar else ""))
    except Exception as e:                  # la revisión es un extra: si falla, el catálogo sale igual (con las portadas como estaban)
        print(f"Portadas: no se pudieron revisar ({type(e).__name__}: {e})", file=sys.stderr)
    if espejo is not None:
        try:
            con, subidas, muertas, sin_comprobar = espejar(items, espejo, key)
            print(f"Espejo: {con} de {len(items)} con copia en ImgBB, {subidas} subidas ahora"
                  + (f", {muertas} copias muertas" if muertas else "") + (f", {sin_comprobar} sin poder comprobar" if sin_comprobar else ""))
        except Exception as e:              # el espejo también es un extra
            print(f"Espejo: falló ({type(e).__name__})", file=sys.stderr)

    usados = sorted({it["studioSlug"] for it in items if it["studioSlug"]})
    estudios = sorted(({"slug": s, "name": nombres.get(s) or _nombre_de_slug(s)} for s in usados), key=lambda e: e["name"].lower())
    anios = sorted({it["year"] for it in items if it["year"]}, reverse=True)
    return {"items": items, "extra": {"paginas": paginas, "porPagina": por_pagina, "estudios": estudios, "anios": anios}}


# ── Géneros ───────────────────────────────────────────────────────────────────────────────────────────────

def _item_corto(c):
    """Un episodio de una tarjeta, con el formato del catálogo, para cuando el género lista uno que el catálogo no tiene."""
    return {"id": 0, "slug": c["slug"], "title": c["title"], "episode": c["episode"], "seriesName": c["seriesName"],
            "imageUrl": c["imageUrl"], "studioSlug": "", "year": 0}


def build_generos(previo_doc, items_por_slug, max_paginas=MAX_PAGINAS, espejo=None):
    """Los géneros (dict para escribir) o None si no se pudieron armar. De cada género solo se vuelve a recorrer lo que
    cambió de tamaño desde la vez anterior (un episodio nuevo mueve unos pocos géneros). `espejo`: original → copia en
    ImgBB, para la miniatura del género y los episodios que el catálogo no tiene."""
    espejo = espejo or {}
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
        for i in items:
            i["imageUrl"] = espejo.get(_de_hentaila(i.get("imageUrl")), i.get("imageUrl"))
        thumb = espejo.get(_de_hentaila(thumb), thumb)
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


# ── Ediciones del staff (desde la app: póster, logo y descripciones) ──────────────────────────────────────────

def cargar_ediciones(url=EDICIONES_URL):
    """Lo que el staff editó desde la app, tal como está en Firebase: {clave de serie: {poster, logo, descripcion,
    episodios}}. {} si no hay nada; None si Firebase no respondió (entonces se deja el ediciones.json anterior)."""
    try:
        r = requests.get(url, headers={"User-Agent": bp.UA}, timeout=bp.TIMEOUT)
        if r.status_code != 200:
            print(f"  Ediciones: HTTP {r.status_code}", file=sys.stderr)
            return None
        doc = r.json()
    except Exception as e:
        print(f"  Ediciones: no se pudieron leer: {type(e).__name__}", file=sys.stderr)
        return None
    if doc is None:
        return {}
    return doc if isinstance(doc, dict) else None


def escribir_ediciones(path, ediciones):
    """Guarda ediciones.json (una copia en GitHub de lo editado; las claves ordenadas) si cambió. True si se escribió."""
    prev = _cargar(path)
    if isinstance(prev, dict) and prev.get("items") == ediciones:
        return False
    doc = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": int(time.time() * 1000),
           "total": len(ediciones), "items": dict(sorted(ediciones.items()))}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"  Escrito {path} ({len(ediciones)} series editadas)")
    return True


def _clave_app(id_):
    """La clave con que la app guarda una serie en /ediciones (Ediciones.claveDe): su id dejando solo letras, números, _ y -."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", str(id_ or "").strip())[:120]


def aplicar_ediciones(items, ediciones, enlaces):
    """Pone a todos los episodios de una serie el póster que el staff le editó (así Explorar, los géneros y la lupa lo
    muestran, no solo la ficha). La edición se guarda con el id de la serie en MuchoHentai («mh_…»); `enlaces` (clave =
    título de la serie en minúsculas → serie de MuchoHentai, del enlaces.json) dice a qué serie del catálogo corresponde.
    Devuelve cuántos episodios cambiaron."""
    por_id = {}
    for clave, anime in (enlaces or {}).items():
        if isinstance(anime, dict) and anime.get("id"):
            por_id[_clave_app(anime["id"])] = clave
    posters = {}
    for serie_id, ed in (ediciones or {}).items():
        poster = ed.get("poster") if isinstance(ed, dict) else None
        clave = por_id.get(str(serie_id))
        if clave and isinstance(poster, str) and _IMGBB.match(poster):
            posters[clave] = poster
    cambiados = 0
    for it in items:
        poster = posters.get((it.get("seriesName") or "").strip().lower())
        if poster and it["imageUrl"] != poster:
            it["imageUrl"] = poster
            cambiados += 1
    return cambiados


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


def escribir_espejo(path, espejo, antes):
    """Guarda espejo.json si el mapa cambió. True si se escribió."""
    if espejo == antes:
        return False
    doc = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ts": int(time.time() * 1000),
           "total": len(espejo), "items": dict(sorted(espejo.items()))}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    print(f"  Escrito {path} ({len(espejo)} copias)")
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
    ruta_esp = os.path.join(args.carpeta, "espejo.json")
    ruta_ed = os.path.join(args.carpeta, "ediciones.json")
    espejo = cargar_espejo(_cargar(ruta_esp))
    espejo_antes = dict(espejo)
    key = os.environ.get("IMGBB_KEY", "").strip() or None      # el secreto del workflow; nunca se imprime

    pedidos, ok = 0, 0
    t0 = time.time()
    previo_cat = _cargar(ruta_cat)
    items_por_slug = {it["slug"]: it for it in (previo_cat or {}).get("items") or [] if isinstance(it, dict) and it.get("slug")}
    if args.solo != "generos":
        pedidos += 1
        print("== Catálogo ==")
        cat = build_catalogo(previo_cat, args.presupuesto, args.max_paginas, espejo, key)
        if cat is not None:
            print(f"Catálogo armado en {time.time() - t0:.0f} s")
            # Lo editado por el staff desde la app: se copia a ediciones.json y los pósters editados entran al catálogo
            ediciones = cargar_ediciones()
            if ediciones is not None:
                escribir_ediciones(ruta_ed, ediciones)
            else:                                     # Firebase no respondió: vale la copia de la corrida anterior
                anterior = _cargar(ruta_ed)
                ediciones = anterior.get("items") if isinstance(anterior, dict) else None
            if ediciones:
                cambiados = aplicar_ediciones(cat["items"], ediciones, bp._enlaces_muchohentai())
                print(f"  Ediciones del staff: {len(ediciones)} series, {cambiados} episodios con póster editado")
            write_if_changed(ruta_cat, cat)
            escribir_espejo(ruta_esp, espejo, espejo_antes)
            items_por_slug = {it["slug"]: it for it in cat["items"]}
            ok += 1
    if args.solo != "catalogo":
        pedidos += 1
        print("== Géneros ==")
        t1 = time.time()
        gen = build_generos(_cargar(ruta_gen), items_por_slug, args.max_paginas, espejo)
        if gen is not None:
            print(f"Géneros armados en {time.time() - t1:.0f} s")
            write_if_changed(ruta_gen, gen)
            ok += 1
    if ok < pedidos:                  # lo que sí salió ya quedó escrito; el código 1 es para que el workflow lo reintente
        sys.exit(1)


if __name__ == "__main__":
    main()
