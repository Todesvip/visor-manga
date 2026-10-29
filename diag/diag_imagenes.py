#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL: ¿se pueden bajar de verdad las portadas del catálogo? Se prueban como lo haría la app (con y sin
Referer) y como un navegador, y se intenta decodificar cada imagen. Escribe diag/imagenes_out.json."""
import io
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image

try:
    from curl_cffi import requests as cr
except ImportError:
    cr = None

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "imagenes_out.json")
UA_APP = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
          "Chrome/124.0.0.0 Mobile Safari/537.36")
UA_OKHTTP = "okhttp/4.12.0"
CATALOGO = "https://todesvip.github.io/visor-manga/cine/Archivos/catalogo.json"
HENTAILA = "https://hentaila.io"
PROBLEMAS = ["oushun-jogakuen", "netorareta-bakunyuu-tsuma-tachi-2", "kokuhaku-episodio", "1ldk-jk-ikinari"]
HSTREAM = [
    "https://hstream.moe/images/hentai/1ldk-jk-ikinari-doukyo-micchaku-hatsu-ecchi/cover-ep-7.webp",       # el que encontró el usuario
    "https://hstream.moe/images/hentai/1ldk-jk-ikinari-doukyo-micchaku-hatsu-ecchi/cover-ep-8.webp",
    "https://hstream.moe/images/hentai/1ldk-jk-ikinari-doukyo-micchaku-hatsu-ecchi/cover-ep-1.webp",
    "https://hstream.moe/images/hentai/oushun-jogakuen-no-danyuu/cover-ep-1.webp",
    "https://hstream.moe/images/hentai/netorareta-bakunyuu-tsuma-tachi-2/cover-ep-1.webp",
    "https://hstream.moe/images/hentai/kokuhaku/cover-ep-4.webp",
]


def decodifica(b):
    try:
        im = Image.open(io.BytesIO(b))
        fmt = im.format
        im.load()
        return {"formato": fmt, "modo": im.mode, "tamano": list(im.size)}
    except Exception as e:
        return {"error_decodificar": f"{type(e).__name__}: {e}"[:160]}


def resumen(r, dt):
    b = r.content or b""
    out = {"status": r.status_code, "tipo": r.headers.get("content-type"), "bytes": len(b), "seg": round(dt, 2),
           "magia": b[:12].hex(), "cf": r.headers.get("cf-cache-status"), "servidor": r.headers.get("server")}
    if r.status_code == 200 and len(b) > 200:
        out.update(decodifica(b))
    elif r.status_code != 200:
        out["inicio"] = b[:160].decode("utf-8", "replace")
    return out


def bajar(url, modo, referer):
    t0 = time.time()
    try:
        if modo == "app":                      # lo que hace la app con HentailaImagesInterceptor
            r = requests.get(url, headers={"User-Agent": UA_APP, "Referer": referer, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
                             timeout=40)
        elif modo == "okhttp":                 # sin el interceptor: OkHttp a secas
            r = requests.get(url, headers={"User-Agent": UA_OKHTTP}, timeout=40)
        else:                                  # un navegador de verdad
            if cr is None:
                return {"error": "sin curl_cffi"}
            r = cr.get(url, headers={"Referer": referer}, impersonate="chrome", timeout=40)
        return resumen(r, time.time() - t0)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:200], "seg": round(time.time() - t0, 2)}


def probar(par):
    url, referer = par
    return {"url": url, **{m: bajar(url, m, referer) for m in ("app", "okhttp", "chrome")}}


def pagina(slug):
    """El HTML de /ver/<slug>/ con el navegador simulado y lo que dice de su portada."""
    url = f"{HENTAILA}/ver/{slug}/"
    try:
        r = cr.get(url, headers={"Referer": HENTAILA + "/"}, impersonate="chrome", timeout=40)
    except Exception as e:
        return {"slug": slug, "error": f"{type(e).__name__}: {e}"[:200]}
    html = r.text
    portada = re.search(r'<div class="cover">.*?<img[^>]*?src="([^"]+)"', html, re.S)
    return {"slug": slug, "status": r.status_code, "bytes": len(html), "portada": portada.group(1) if portada else None,
            "uploads": re.findall(r'src="(/uploads/[^"]+)"', html)[:12], "sin_portada": "poster-unavailable" in html}


def main():
    t0 = time.time()
    cat = requests.get(CATALOGO, timeout=60).json()
    items = cat["items"]
    por_slug = {i["slug"]: i for i in items}
    problema = [i for i in items if any(p in i["slug"] for p in PROBLEMAS)]
    primeros = items[:40]
    resto = [i for i in items[40:] if i not in problema]
    azar = random.Random(11).sample(resto, 70)
    vistos, lista = set(), []
    for grupo, its in (("problema", problema), ("primeros40", primeros), ("azar", azar)):
        for i in its:
            if i["imageUrl"] not in vistos:
                vistos.add(i["imageUrl"])
                lista.append((grupo, i["slug"], i["imageUrl"]))
    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "catalogo_ts": cat.get("ts"), "total_items": len(items),
           "curl_cffi": cr is not None}
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(probar, [(u, HENTAILA + "/") for _, _, u in lista]))
        out["portadas"] = [{"grupo": g, "slug": s, **r} for (g, s, _), r in zip(lista, res)]
        hs = list(ex.map(probar, [(u, "https://hstream.moe/") for u in HSTREAM]))
        out["hstream"] = hs
        slugs = [i["slug"] for i in problema][:14] + [s for s in por_slug if s.endswith("episodio-7") and "1ldk" in s]
        out["paginas"] = list(ex.map(pagina, slugs))

    def ok(r, m):
        return r.get(m, {}).get("status") == 200 and "error_decodificar" not in r.get(m, {})

    out["resumen"] = {m: {"ok": sum(1 for r in out["portadas"] if ok(r, m)), "de": len(out["portadas"]),
                          "fallan": [r["slug"] for r in out["portadas"] if not ok(r, m)][:30]} for m in ("app", "okhttp", "chrome")}
    out["segundos"] = round(time.time() - t0, 1)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out["resumen"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
