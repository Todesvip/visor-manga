#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Medición TEMPORAL: cuánto pesan los pósters de Hentaila y cuánto pesarían como miniaturas WebP.
Escribe diag/pesos_out.json."""
import io
import json
import os
import random
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None
import requests as rq

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
SALIDA = os.environ.get("PESOS_SALIDA") or os.path.join(AQUI, "pesos_out.json")
REF = "https://hentaila.io/"
VIEJA = re.compile(r"^https?://(?:www\.)?veohentai\.com/media/(.+)$", re.I)


def nueva(u):
    m = VIEJA.match(u)
    return "https://hentaila.io/uploads/" + m.group(1) if m else u


def bajar(url):
    """(status, bytes, segundos)"""
    t0 = time.time()
    try:
        if cr is not None:
            r = cr.get(url, headers={"Referer": REF}, impersonate="chrome", timeout=40)
        else:
            r = rq.get(url, headers={"Referer": REF}, timeout=40)
        return r.status_code, r.content, time.time() - t0
    except Exception:
        return None, b"", time.time() - t0


def webp(img, ancho, calidad):
    im = img
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGB")
    w, h = im.size
    if w > ancho:
        im = im.resize((ancho, max(1, round(h * ancho / w))), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=calidad, method=4)
    return len(out.getvalue())


def medir(url):
    st, b, dt = bajar(url)
    if st != 200 or len(b) < 500:
        return {"url": url, "status": st, "bytes": len(b)}
    try:
        im = Image.open(io.BytesIO(b))
        im.load()
    except Exception as e:
        return {"url": url, "status": st, "bytes": len(b), "error": f"{type(e).__name__}: {e}"[:120]}
    return {"url": url, "status": st, "bytes": len(b), "ancho": im.size[0], "alto": im.size[1], "formato": im.format,
            "segundos": round(dt, 2),
            "webp300_q70": webp(im, 300, 70), "webp360_q75": webp(im, 360, 75), "webp480_q75": webp(im, 480, 75)}


def kb(x):
    return round(x / 1024, 1)


def resumen(filas):
    ok = [f for f in filas if "webp360_q75" in f]
    if not ok:
        return {"n": 0}
    def est(clave):
        v = [f[clave] for f in ok]
        return {"media_kb": kb(statistics.mean(v)), "mediana_kb": kb(statistics.median(v)),
                "p90_kb": kb(sorted(v)[int(0.9 * (len(v) - 1))]), "max_kb": kb(max(v)), "total_kb": kb(sum(v))}
    r = {"n": len(ok), "original": est("bytes"), "webp300_q70": est("webp300_q70"), "webp360_q75": est("webp360_q75"),
         "webp480_q75": est("webp480_q75"),
         "ancho_mediano_px": int(statistics.median(f["ancho"] for f in ok)),
         "formatos": {k: sum(1 for f in ok if f["formato"] == k) for k in {f["formato"] for f in ok}},
         "ahorro_webp360_pct": round(100 * (1 - sum(f["webp360_q75"] for f in ok) / sum(f["bytes"] for f in ok)), 1),
         "segundos_por_imagen_mediana": round(statistics.median(f["segundos"] for f in ok), 2)}
    return r


def main():
    jsons = []
    for nombre in ("top10.json", "mas_vistos.json"):
        d = json.load(open(os.path.join(RAIZ, "cine", "Archivos", nombre), encoding="utf-8"))
        jsons += [i["imageUrl"] for i in d["items"]]
    jsons = list(dict.fromkeys(jsons))
    entradas = json.load(open(os.path.join(AQUI, "entradas.json"), encoding="utf-8"))["imagenes"]
    azar = random.Random(7).sample(entradas, min(60, len(entradas)))
    catalogo = [nueva(u) for u in azar]

    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "curl_cffi": cr is not None}
    with ThreadPoolExecutor(max_workers=4) as ex:
        a = list(ex.map(medir, jsons))
        out["home_nuevos"] = {"resumen": resumen(a), "filas": a}
        b = list(ex.map(medir, catalogo))
        out["catalogo_muestra"] = {"resumen": resumen(b), "fallos": [f["url"] for f in b if "webp360_q75" not in f],
                                   "filas": b}
    out["fin"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
