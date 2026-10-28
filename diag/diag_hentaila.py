#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL (se borra después de leerlo): qué ve un servidor de GitHub en hentaila.io.

1) Repite lo que hace el Action de verdad (build_top10 + build_mas_vistos) y guarda sus mensajes.
2) Mira por separado /trending/, /sort/most-views/ y otras páginas: ¿responden?, ¿son iguales?
3) Prueba si los pósters cargan (los nuevos del JSON y los viejos de VeoHentai pasados a /uploads/).
4) Mira si las fichas /ver/<slug>/ de VeoHentai existen en Hentaila.
Escribe diag/diag_out.json (aunque algo falle por el camino)."""
import concurrent.futures as cf
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import time
import traceback

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.environ.get("DIAG_SALIDA") or os.path.join(AQUI, "diag_out.json")

spec = importlib.util.spec_from_file_location("bp", os.path.join(RAIZ, "cine", "Archivos", "build_primicias.py"))
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None
import requests as rq

REF = "https://hentaila.io/"
UA_MOVIL = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Mobile Safari/537.36")
VIEJA = re.compile(r"^https?://(?:www\.)?veohentai\.com/media/(.+)$", re.I)

out = {"curl_cffi": cr is not None, "bp_usa_curl": getattr(bp, "_CURL", None), "inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}


def guardar():
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


def get(url, chrome=True, headers=None, rango=False, timeout=30):
    """(status, content-type, cuerpo, url final, error, bytes totales)."""
    h = dict(headers or {})
    if rango:
        h["Range"] = "bytes=0-2047"
    try:
        if chrome and cr is not None:
            r = cr.get(url, headers=h, impersonate="chrome", timeout=timeout, allow_redirects=True)
        else:
            r = rq.get(url, headers=h, timeout=timeout, allow_redirects=True)
        c = r.content
        return r.status_code, r.headers.get("content-type"), (c[:64] if rango else c), str(r.url), None, len(c)
    except Exception as e:
        return None, None, b"", url, f"{type(e).__name__}: {e}"[:200], 0


def nueva(u):
    m = VIEJA.match(u)
    return "https://hentaila.io/uploads/" + m.group(1) if m else u


def tipo_imagen(b):
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:4] == b"\x89PNG":
        return "png"
    if b[:4] == b"GIF8":
        return "gif"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[4:8] == b"ftyp":
        return "avif/heic"
    return None


def meta(html, prop):
    for m in re.finditer(r"<meta\b[^>]*>", html, re.I):
        tag = m.group(0)
        if re.search(r'(?:property|name)=["\']' + re.escape(prop) + r'["\']', tag, re.I):
            c = re.search(r'content=["\']([^"\']*)', tag, re.I)
            if c:
                return c.group(1)
    return None


def titulo(html):
    t = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", t.group(1)).strip()[:140] if t else None


def paso(nombre, fn):
    t0 = time.time()
    try:
        fn()
    except Exception:
        out.setdefault("errores", {})[nombre] = traceback.format_exc()[-1500:]
    out.setdefault("segundos", {})[nombre] = round(time.time() - t0, 1)
    guardar()


# 1) Lo que hace el Action de verdad -----------------------------------------------------------------------------
def produccion():
    o, e = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(o), contextlib.redirect_stderr(e):
        top = bp.build_top10()
        mas = bp.build_mas_vistos()
    out["produccion"] = {"stdout": o.getvalue()[-3000:], "stderr": e.getvalue()[-3000:],
                         "top10": [i["slug"] for i in top], "mas_vistos": [i["slug"] for i in mas],
                         "top10_igual_a_los_10_primeros_de_mas_vistos":
                             [i["slug"] for i in top] == [i["slug"] for i in mas][:10]}


# 2) Páginas -----------------------------------------------------------------------------------------------------
def pagina(ruta):
    st, ct, body, final, err, n = get(bp.HENTAILA + ruta, headers={"Accept-Language": "es-ES,es;q=0.9", "Referer": REF}, timeout=40)
    info = {"status": st, "final": final if final.rstrip("/") != (bp.HENTAILA + ruta).rstrip("/") else None,
            "bytes": n, "error": err}
    if st == 200:
        html = body.decode("utf-8", "replace")
        info["titulo"] = titulo(html)
        info["cloudflare"] = "Just a moment" in html[:2000]
        tarjetas = bp.parse_hentaila_cards(html)
        info["tarjetas"] = len(tarjetas)
        info["con_portada"] = sum(1 for t in tarjetas if t["imageUrl"])
        info["slugs_md5"] = hashlib.md5("|".join(t["slug"] for t in tarjetas).encode()).hexdigest()[:10]
        info["primeros"] = [[t["slug"], t["episode"], (t["imageUrl"] or "").replace(bp.HENTAILA, "")] for t in tarjetas[:16]]
    return info


def paginas():
    out["paginas"] = {}
    for ruta in ["/trending/", "/sort/most-views/", "/sort/most-likes/", "/sort/newest/", "/"]:
        out["paginas"][ruta] = pagina(ruta)
        guardar()
        time.sleep(0.5)


# 3) Pósters -----------------------------------------------------------------------------------------------------
def prueba_imagen(url, chrome=True):
    h = {"Referer": REF}
    if not chrome:
        h["User-Agent"] = UA_MOVIL
    st, ct, body, final, err, n = get(url, chrome=chrome, headers=h, rango=True, timeout=30)
    return {"status": st, "ct": (ct or "")[:40], "tipo": tipo_imagen(body), "error": err,
            "final": final if final != url else None}


def en_paralelo(fn, args, trabajadores=6):
    res = {}
    with cf.ThreadPoolExecutor(max_workers=trabajadores) as ex:
        futs = {ex.submit(fn, *a): a[0] for a in args}
        for f in cf.as_completed(futs):
            try:
                res[futs[f]] = f.result()
            except Exception as e:
                res[futs[f]] = {"error": f"{type(e).__name__}: {e}"[:200]}
    return res


def ok(v):
    return v.get("status") in (200, 206) and bool(v.get("tipo"))


def resumen(res):
    c = {}
    for v in res.values():
        k = f"{v.get('status')}/{v.get('tipo') or '-'}" if "tipo" in v else str(v.get("status"))
        c[k] = c.get(k, 0) + 1
    return c


def imagenes():
    entradas = json.load(open(os.path.join(AQUI, "entradas.json"), encoding="utf-8"))
    # a) los pósters que el Action acaba de poner en los JSON nuevos
    nuevos = []
    for u in (out.get("jsons_nuevos") or []):
        if u not in nuevos:
            nuevos.append(u)
    r_nuevos = en_paralelo(prueba_imagen, [(u,) for u in nuevos])
    out["imagenes_nuevas"] = {"total": len(nuevos), "resumen": resumen(r_nuevos),
                              "fallos": {u.replace(REF, "/"): v for u, v in r_nuevos.items() if not ok(v)}}
    # b) los de siempre (veohentai.com/media/...) pasados a hentaila.io/uploads/...
    viejas = entradas["imagenes"]
    r_viejas = en_paralelo(prueba_imagen, [(nueva(u),) for u in viejas])
    por_mes = {}                                    # "año" (o "2026-MM") -> [bien, mal]
    for u in viejas:
        m = re.search(r"/media/(\d{4})/(\d{2})/", u)
        k = "?" if not m else (m.group(1) if m.group(1) != "2026" else f"2026-{m.group(2)}")
        por_mes.setdefault(k, [0, 0])[0 if ok(r_viejas[nueva(u)]) else 1] += 1
    fallos = {u: r_viejas[nueva(u)] for u in viejas if not ok(r_viejas[nueva(u)])}
    out["imagenes_viejas"] = {"total": len(viejas), "resumen": resumen(r_viejas), "ok_y_fallo_por_mes": dict(sorted(por_mes.items())),
                              "fallos_ejemplos": dict(list(fallos.items())[:25])}
    # c) lo mismo sin la huella de Chrome (más parecido a una app): ¿cambia algo?
    muestra = nuevos[:10] + [nueva(u) for u in viejas[:30]]
    r_sin = en_paralelo(lambda u: prueba_imagen(u, chrome=False), [(u,) for u in muestra])
    out["imagenes_sin_huella_chrome"] = {"total": len(muestra), "resumen": resumen(r_sin),
                                         "fallos": {u.replace(REF, "/"): v for u, v in r_sin.items() if not ok(v)}}


# 4) Fichas ------------------------------------------------------------------------------------------------------
def ficha(slug):
    st, ct, body, final, err, n = get(f"{bp.HENTAILA}/ver/{slug}/", headers={"Accept-Language": "es-ES,es;q=0.9", "Referer": REF}, timeout=40)
    d = {"status": st, "error": err, "final": final if final.rstrip("/") != f"{bp.HENTAILA}/ver/{slug}" else None}
    if st == 200:
        html = body.decode("utf-8", "replace")
        d["titulo"] = titulo(html)
        d["og_image"] = (meta(html, "og:image") or "")[:160] or None
    return d


def fichas():
    entradas = json.load(open(os.path.join(AQUI, "entradas.json"), encoding="utf-8"))
    r = en_paralelo(ficha, [(s,) for s in entradas["slugs"]], trabajadores=4)
    out["fichas"] = {"total": len(r), "resumen": resumen(r), "detalle": {s: r[s] for s in entradas["slugs"]}}


def jsons_nuevos():
    urls = []
    for nombre in ("top10.json", "mas_vistos.json"):
        d = json.load(open(os.path.join(RAIZ, "cine", "Archivos", nombre), encoding="utf-8"))
        urls += [i["imageUrl"] for i in d["items"]]
    out["jsons_nuevos"] = urls


def main():
    paso("produccion", produccion)
    paso("paginas", paginas)
    paso("jsons_nuevos", jsons_nuevos)
    paso("imagenes", imagenes)
    paso("fichas", fichas)
    out["fin"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    guardar()


if __name__ == "__main__":
    main()
