#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 7: lo que sirve GitHub Pages AHORA. catalogo.json y generos.json: la portada del 1LDK ep. 7 y que
baje de verdad; y el resto de portadas del catálogo sigue igual de viva. Escribe diag/final_out.json."""
import io
import json
import os
import time

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "final_out.json")
BASE = "https://todesvip.github.io/visor-manga/cine/Archivos/"
HS7 = "https://hstream.moe/images/hentai/1ldk-jk-ikinari-doukyo-micchaku-hatsu-ecchi/cover-ep-7.webp"
SLUG = "1ldk-jk-ikinari-doukyo-micchaku-hatsu-ecchi-episodio-7"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")


def bajar(nombre):
    r = requests.get(BASE + nombre + "?v=" + str(int(time.time())), timeout=90)
    return r.status_code, r.text


def main():
    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}
    sc, tc = bajar("catalogo.json")
    sg, tg = bajar("generos.json")
    out["status"] = {"catalogo": sc, "generos": sg}
    cat = json.loads(tc)
    gen = json.loads(tg)
    it = next(i for i in cat["items"] if i["slug"] == SLUG)
    out["catalogo"] = {"ts": cat["ts"], "total": cat["total"], "items": len(cat["items"]), "imagen_1ldk_ep7": it["imageUrl"],
                       "es_hstream": it["imageUrl"] == HS7, "ocurrencias_muerta": tc.count("Hatsu-Ecchi-7.jpg")}
    out["generos"] = {"ts": gen["ts"], "total": gen["total"], "ocurrencias_hstream": tg.count(HS7), "ocurrencias_muerta": tg.count("Hatsu-Ecchi-7.jpg")}
    r = requests.get(HS7, headers={"User-Agent": "okhttp/4.12.0"}, timeout=40)
    b = r.content
    info = {"status": r.status_code, "tipo": r.headers.get("content-type"), "bytes": len(b), "magia": b[:12].hex()}
    try:
        from PIL import Image
        im = Image.open(io.BytesIO(b)); im.load()
        info.update({"formato": im.format, "tam": list(im.size)})
    except Exception as e:
        info["error_decodificar"] = str(e)[:100]
    out["hstream"] = info
    # el resto del catálogo sigue vivo
    urls = sorted({i["imageUrl"] for i in cat["items"]})
    from concurrent.futures import ThreadPoolExecutor

    def vivo(u):
        try:
            h = {"User-Agent": UA, "Referer": "https://hentaila.io/" if "hentaila.io" in u else "https://hstream.moe/"}
            with requests.get(u, headers=h, stream=True, timeout=30) as rr:
                return rr.status_code
        except Exception as e:
            return type(e).__name__
    with ThreadPoolExecutor(max_workers=8) as ex:
        estados = list(ex.map(vivo, urls))
    cuenta = {}
    for e in estados:
        cuenta[str(e)] = cuenta.get(str(e), 0) + 1
    out["portadas"] = {"distintas": len(urls), "estados": cuenta}
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
