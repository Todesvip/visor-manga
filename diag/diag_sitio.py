#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL (se borra después de leerlo), parte 2.

Responde, desde un servidor de GitHub (el único que llega a hentaila.io):
  1) ¿Dónde pone Hentaila la imagen HORIZONTAL de cada episodio? (/ver/<slug>/ + los scripts de la página)
  2) ¿Existen en Hentaila los backdrops que tenía VeoHentai en su catálogo? ¿Son de verdad horizontales?
  3) ¿Cómo son sus páginas: inicio paginado, /series/, /generos/, /genero/<x>/, /search/, /directorio-hentai/?
Escribe diag/sitio_out.json y guarda el HTML crudo de unas pocas páginas en diag/html/."""
import io
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None
import requests as rq

try:
    from PIL import Image
except ImportError:
    Image = None

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.environ.get("SITIO_SALIDA") or os.path.join(AQUI, "sitio_out.json")
HTMLDIR = os.environ.get("SITIO_HTML") or os.path.join(AQUI, "html")
CASOS = os.environ.get("SITIO_CASOS") or os.path.join(AQUI, "casos.json")
BASE = "https://hentaila.io"
REF = BASE + "/"
VIEJA = re.compile(r"^https?://(?:www\.)?veohentai\.com/media/(.+)$", re.I)

out = {"curl_cffi": cr is not None, "pillow": Image is not None,
       "inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "errores": {}}


def guardar():
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def nueva(u):
    m = VIEJA.match(u or "")
    return BASE + "/uploads/" + m.group(1) if m else u


def nombre(u):
    return (u or "").split("?")[0].rsplit("/", 1)[-1]


def get(url, rango=False, timeout=40):
    """{status, ctype, body, final, error}"""
    h = {"Referer": REF}
    if rango:
        h["Range"] = "bytes=0-4095"
    try:
        if cr is not None:
            r = cr.get(url, headers=h, impersonate="chrome", timeout=timeout, allow_redirects=True)
        else:
            r = rq.get(url, headers=h, timeout=timeout, allow_redirects=True)
        return {"status": r.status_code, "ctype": r.headers.get("content-type"), "body": r.content,
                "final": str(r.url), "error": None}
    except Exception as e:
        return {"status": None, "ctype": None, "body": b"", "final": url, "error": f"{type(e).__name__}: {e}"[:200]}


def pagina(url, intentos=3):
    """GET de una página HTML con reintentos (el sitio a veces contesta 403/5xx de pasada)."""
    r = None
    for i in range(intentos):
        r = get(url)
        if r["status"] == 200 and len(r["body"]) > 1000:
            return r
        time.sleep(1.5 * (i + 1))
    return r


def ok(st):
    return st in (200, 206)


# ── Análisis de un HTML ───────────────────────────────────────────────────────────────────────────────────────

CLAVES = ("backdrop", "banner", "thumbnail", "thumb", "screenshot", "poster", "cover", "preview", "sprite",
          "contenturl", "embedurl", "videoobject", "og:image", "twitter:image")
ATTR = re.compile(r"([A-Za-z_:][\w:.-]*)=\"([^\"]*)\"")


def atributos(tag):
    return {k: v for k, v in ATTR.findall(tag)}


def busca(html, nom):
    """¿Aparece ese nombre de archivo (o su nombre sin extensión) en el HTML? Con un poco de contexto."""
    if not nom:
        return None
    res = {"nombre": nom, "hallado": False, "veces": 0, "contextos": []}
    cand = [nom, nom.rsplit(".", 1)[0]]
    for hay in (html, unquote(html)):
        for c in cand:
            if len(c) < 4:
                continue
            n = hay.count(c)
            if n:
                res["hallado"] = True
                res["veces"] = n
                i = hay.find(c)
                res["contextos"].append(hay[max(0, i - 170): i + len(c) + 130])
                break
        if res["hallado"]:
            break
    return res


def analiza(html, completo=True):
    r = {"bytes": len(html)}
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    r["titulo"] = m.group(1).strip()[:160] if m else None
    meta = {}
    for tag in re.findall(r"<meta\b[^>]*>", html):
        a = atributos(tag)
        k = a.get("property") or a.get("name")
        if k and k.startswith(("og:", "twitter:")) and k not in meta:
            meta[k] = (a.get("content") or "")[:300]
    r["meta"] = meta
    ld = re.findall(r"<script type=\"application/ld\+json\">(.*?)</script>", html, re.S)
    r["ld_json"] = [x[:(3500 if completo else 600)] for x in ld[:4]]
    imgs = []
    for tag in re.findall(r"<img\b[^>]*>", html):
        a = atributos(tag)
        imgs.append({"src": (a.get("src") or a.get("data-src") or "")[:200], "w": a.get("width"), "h": a.get("height"),
                     "alt": (a.get("alt") or "")[:60], "class": a.get("class")})
    r["n_img"] = len(imgs)
    r["tamanos_img"] = dict(Counter(f"{i['w']}x{i['h']}" for i in imgs))
    r["imgs"] = imgs[: (30 if completo else 6)]
    subidas = sorted(set(x.rstrip("\\") for x in re.findall(r"/uploads/[^\"'\\\s)<>&?]+", html)))
    r["uploads_total"] = len(subidas)
    r["uploads"] = subidas[: (80 if completo else 15)]
    otras = []
    for x in re.findall(r"https?://[^\s\"'\\<>)]+?\.(?:jpe?g|png|webp|gif|avif|svg)", html, re.I):
        if "/uploads/" not in x and x not in otras:
            otras.append(x)
    r["imagenes_de_otros_sitios"] = otras[:25]
    r["etiquetas_media"] = [t[:400] for t in re.findall(r"<(?:video|source|iframe|track|embed|object)\b[^>]*>", html, re.I)[:12]]
    low = html.lower()
    r["palabras"] = {k: low.count(k) for k in CLAVES if low.count(k)}
    claves_rsc = Counter(re.findall(r"\\?\"([A-Za-z_]*(?:image|img|thumb|cover|poster|backdrop|banner|screen|preview|photo)[A-Za-z_]*)\\?\":", html, re.I))
    r["claves_de_datos_con_imagen"] = dict(claves_rsc.most_common(25))
    hrefs = re.findall(r"href=\"(/[^\"#]*)\"", html)
    seg = Counter()
    for h in hrefs:
        p = h.split("?")[0].strip("/").split("/")
        seg["/" + p[0] + "/" if p and p[0] else "/"] += 1
    r["enlaces_por_segmento"] = dict(seg.most_common(25))
    otros = []
    for h in hrefs:
        if h.startswith(("/ver/", "/genero/", "/uploads/", "/_next/", "/?page=")) or h in otros:
            continue
        otros.append(h)
    r["enlaces_otros"] = otros[:60]
    r["n_ver"] = len(set(re.findall(r"href=\"(/ver/[^\"]+)\"", html)))
    pags = []
    for h in hrefs:
        if re.search(r"(?:[?&]page=|/page/)\d+", h) and h not in pags:
            pags.append(h)
    r["paginacion"] = pags[:8] + (["…"] + pags[-4:] if len(pags) > 12 else pags[8:12])
    r["scripts"] = re.findall(r"<script[^>]+src=\"([^\"]+)\"", html)[:20]
    return r


def guarda_html(nom, html):
    try:
        os.makedirs(HTMLDIR, exist_ok=True)
        with open(os.path.join(HTMLDIR, nom + ".html"), "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    except Exception as e:
        out["errores"][f"html_{nom}"] = str(e)


# ── Fase 1: páginas de episodio ────────────────────────────────────────────────────────────────────────────

def fase_episodios(casos):
    res = []
    guardados = 0

    def uno(arg):
        i, c = arg
        slug = c["slug"]
        r = pagina(f"{BASE}/ver/{slug}/")
        fila = {"slug": slug, "origen": c.get("origen"), "status": r["status"], "final": r["final"], "error": r["error"]}
        html = ""
        if r["status"] == 200:
            html = r["body"].decode("utf-8", "replace")
            fila["analisis"] = analiza(html, completo=(i < 4))
            fila["backdrop_conocido"] = busca(html, nombre(c.get("backdrop")))
            fila["poster_conocido"] = busca(html, nombre(nueva(c.get("poster"))))
        return fila, html

    with ThreadPoolExecutor(max_workers=4) as ex:
        for i, (fila, html) in enumerate(ex.map(uno, list(enumerate(casos)))):
            res.append(fila)
            if html and guardados < 3 and (i in (0, 2, 12)):
                guarda_html(f"ver_{i}", html)
                guardados += 1
    out["episodios"] = res
    # resumen corto para leer de un vistazo
    out["episodios_resumen"] = {
        "paginas_ok": sum(1 for f in res if f["status"] == 200),
        "paginas_total": len(res),
        "backdrop_hallado_en_html": sum(1 for f in res if (f.get("backdrop_conocido") or {}).get("hallado")),
        "backdrop_con_dato": sum(1 for f in res if f.get("backdrop_conocido")),
        "poster_hallado_en_html": sum(1 for f in res if (f.get("poster_conocido") or {}).get("hallado")),
    }
    guardar()


# ── Fase 2: ¿existen los backdrops viejos en Hentaila? ¿son horizontales? ───────────────────────────────────────

def dims(b):
    if Image is None or not b:
        return None
    try:
        im = Image.open(io.BytesIO(b))
        return [im.size[0], im.size[1]]
    except Exception:
        return None


def fase_backdrops(casos, muestra):
    # (a) los de los casos, completos: tamaño real del backdrop y del póster
    filas = []

    def uno(c):
        f = {"slug": c["slug"], "origen": c.get("origen")}
        for clave, url in (("backdrop", c.get("backdrop")), ("poster", c.get("poster"))):
            if not url:
                f[clave] = None
                continue
            u = nueva(url)
            r = get(u)
            f[clave] = {"url": u, "status": r["status"], "ctype": r["ctype"], "bytes": len(r["body"]),
                        "dims": dims(r["body"]) if ok(r["status"]) else None, "error": r["error"]}
        return f

    with ThreadPoolExecutor(max_workers=4) as ex:
        filas = list(ex.map(uno, casos))
    out["backdrops_casos"] = filas

    def horiz(f):
        d = (f.get("backdrop") or {}).get("dims")
        return None if not d else d[0] > d[1]
    conb = [f for f in filas if f.get("backdrop")]
    out["backdrops_casos_resumen"] = {
        "con_backdrop": len(conb),
        "cargan": sum(1 for f in conb if ok(f["backdrop"]["status"])),
        "horizontales": sum(1 for f in conb if horiz(f) is True),
        "verticales": sum(1 for f in conb if horiz(f) is False),
        "fallan": [f["backdrop"]["url"] for f in conb if not ok(f["backdrop"]["status"])][:20],
    }
    # (b) muestra grande: solo el estado
    def estado(u):
        r = get(nueva(u), rango=True)
        return r["status"]

    with ThreadPoolExecutor(max_workers=4) as ex:
        estados = list(ex.map(estado, muestra))
    out["backdrops_muestra"] = {"n": len(muestra), "estados": dict(Counter(str(s) for s in estados)),
                                "fallan": [nueva(u) for u, s in zip(muestra, estados) if not ok(s)][:30]}
    guardar()


# ── Fase 3: nombres derivados del póster (¿hay un -backdrop, -thumb, -1280x720 al lado?) ────────────────────

def fase_derivados(casos):
    filas = []
    for c in [x for x in casos if x.get("poster")][:5]:
        p = nueva(c["poster"])
        stem, _, ext = p.rpartition(".")
        probar = [f"{stem}-backdrop.{ext}", f"{stem}-thumb.{ext}", f"{stem}-1280x720.{ext}", f"{stem}-768x432.{ext}",
                  f"{stem}-300x169.{ext}", f"{stem}-scaled.{ext}", f"{stem}-16x9.{ext}"]
        d = {"poster": p, "probados": {}}
        for u in probar:
            d["probados"][u.rsplit("/", 1)[-1]] = get(u, rango=True)["status"]
        filas.append(d)
    out["derivados"] = filas
    guardar()


# ── Fase 4: los scripts de la página (¿hay un API? ¿cómo se arma el póster del reproductor?) ────────────────────

def fase_scripts(url_ep):
    r = pagina(url_ep)
    if r["status"] != 200:
        out["scripts"] = {"error": f"episodio {r['status']}"}
        return
    html = r["body"].decode("utf-8", "replace")
    srcs = []
    for s in re.findall(r"<script[^>]+src=\"([^\"]+)\"", html):
        if s.startswith("/"):
            s = BASE + s
        if s.startswith(BASE) and s not in srcs:
            srcs.append(s)
    res = {"archivos": [], "api": Counter(), "contextos": []}
    for s in srcs[:14]:
        g = get(s, timeout=60)
        if g["status"] != 200:
            res["archivos"].append({"url": s, "status": g["status"]})
            continue
        js = g["body"].decode("utf-8", "replace")
        low = js.lower()
        res["archivos"].append({"url": s, "bytes": len(js), "backdrop": low.count("backdrop"), "poster": low.count("poster"),
                                "thumbnail": low.count("thumbnail"), "screenshot": low.count("screenshot")})
        for a in re.findall(r"[\"'`](/api/[A-Za-z0-9_/\-\[\]${}.]*)", js):
            res["api"][a] += 1
        for k in ("backdrop", "thumbnail", "poster="):
            for mm in list(re.finditer(re.escape(k), js, re.I))[:2]:
                i = mm.start()
                res["contextos"].append({"archivo": s.rsplit("/", 1)[-1], "clave": k, "texto": js[max(0, i - 150): i + 220]})
    res["api"] = dict(res["api"].most_common(40))
    res["contextos"] = res["contextos"][:14]
    out["scripts"] = res
    guardar()


# ── Fase 5: las demás páginas del sitio ──────────────────────────────────────────────────────────────────────

PAGINAS = [
    ("home", "/"), ("home_p2", "/?page=2"), ("home_p64", "/?page=64"), ("home_p65", "/?page=65"),
    ("series", "/series/"), ("series_p2", "/series/?page=2"),
    ("generos", "/generos/"), ("genero_anal", "/genero/anal/"), ("genero_anal_p2", "/genero/anal/?page=2"),
    ("directorio", "/directorio-hentai/"), ("buscar", "/search/?q=maid"), ("trending", "/trending/"),
    ("orden_newest", "/sort/newest/"), ("orden_vistas", "/sort/most-views/"), ("orden_valorados", "/sort/most-likes/"),
]
GUARDAR_HTML = {"home_p2", "series", "generos", "genero_anal", "directorio", "buscar"}


def fase_paginas():
    res = {}
    htmls = {}
    for nom, ruta in PAGINAS:
        r = pagina(BASE + ruta, intentos=2)
        fila = {"ruta": ruta, "status": r["status"], "final": r["final"], "error": r["error"]}
        if r["status"] == 200:
            html = r["body"].decode("utf-8", "replace")
            htmls[nom] = html
            fila["analisis"] = analiza(html, completo=nom in ("series", "generos", "buscar", "directorio"))
            if nom in GUARDAR_HTML:
                guarda_html(nom, html)
        res[nom] = fila
    out["paginas"] = res
    guardar()
    # series: seguir 3 enlaces de ficha de serie (lo que no sea /ver/ ni /genero/ ni /sort/ …)
    seguir = []
    base_html = htmls.get("series") or ""
    for h in re.findall(r"href=\"(/[a-z0-9][a-z0-9_-]*/[a-z0-9][^\"#?]*/?)\"", base_html):
        if h.startswith(("/ver/", "/genero/", "/sort/", "/uploads/", "/_next/", "/series/", "/search/", "/generos/",
                         "/directorio-hentai/", "/trending/", "/ingresar/", "/registrar/", "/images/")):
            continue
        if h not in seguir:
            seguir.append(h)
    # y las fichas que cuelguen de /series/<algo>/
    for h in re.findall(r"href=\"(/series/[^\"#?]+/?)\"", base_html):
        if h.strip("/") != "series" and h not in seguir:
            seguir.append(h)
    out["series_enlaces_encontrados"] = seguir[:12]
    fichas = {}
    for i, h in enumerate(seguir[:3]):
        r = pagina(BASE + h, intentos=2)
        fila = {"ruta": h, "status": r["status"], "final": r["final"]}
        if r["status"] == 200:
            html = r["body"].decode("utf-8", "replace")
            fila["analisis"] = analiza(html, completo=True)
            if i == 0:
                guarda_html("serie_0", html)
        fichas[h] = fila
    out["series_fichas"] = fichas
    guardar()


def fase(nombre, fn, *a):
    t0 = time.time()
    try:
        fn(*a)
    except Exception:
        out["errores"][nombre] = traceback.format_exc()[-1500:]
    out.setdefault("tiempos", {})[nombre] = round(time.time() - t0, 1)
    guardar()


def main():
    with open(CASOS, encoding="utf-8") as f:
        datos = json.load(f)
    casos = datos["casos"]
    fase("episodios", fase_episodios, casos)
    fase("backdrops", fase_backdrops, casos, datos["muestra_backdrops"])
    fase("derivados", fase_derivados, casos)
    fase("scripts", fase_scripts, f"{BASE}/ver/{casos[0]['slug']}/")
    fase("paginas", fase_paginas)
    out["fin"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    guardar()


if __name__ == "__main__":
    main()
