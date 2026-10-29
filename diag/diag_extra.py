#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 5: ¿están vivas las miniaturas/imágenes de los géneros y las imágenes horizontales (backdrop) del
catálogo? Escribe diag/extra_out.json."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
BASE = "https://todesvip.github.io/visor-manga/cine/Archivos/"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36")
MAGIAS = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")
local = threading.local()


def probar(url):
    s = getattr(local, "s", None)
    if s is None:
        s = local.s = requests.Session()
    try:
        with s.get(url, headers={"User-Agent": UA, "Referer": "https://hentaila.io/"}, stream=True, timeout=30) as r:
            cuerpo = next(r.iter_content(64), b"") if r.status_code == 200 else b""
            tipo = r.headers.get("content-type", "")
            return {"status": r.status_code, "ok": r.status_code == 200 and tipo.startswith("image/") and cuerpo.startswith(MAGIAS), "tipo": tipo}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:140], "ok": False}


def main():
    t0 = time.time()
    gen = requests.get(BASE + "generos.json", timeout=60).json()
    cat = requests.get(BASE + "catalogo.json", timeout=60).json()
    urls = {}
    for g in gen["items"]:
        for campo in ("thumb", "image"):
            if g.get(campo):
                urls.setdefault(g[campo], []).append(f"genero:{g['slug']}:{campo}")
        for it in g.get("items") or []:
            if it.get("imageUrl"):
                urls.setdefault(it["imageUrl"], []).append(f"genero-item:{g['slug']}:{it['slug']}")
    for it in cat["items"]:
        if it.get("backdropUrl"):
            urls.setdefault(it["backdropUrl"], []).append(f"backdrop:{it['slug']}")
    lista = sorted(urls)
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(probar, lista))
    muertas = [{"url": u, "donde": urls[u][:4], **r} for u, r in zip(lista, res) if not r["ok"]]
    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "urls": len(lista), "muertas": muertas,
           "estados": {}, "segundos": round(time.time() - t0, 1)}
    for r in res:
        k = str(r.get("status") or r.get("error", "?")[:30])
        out["estados"][k] = out["estados"].get(k, 0) + 1
    json.dump(out, open(os.path.join(AQUI, "extra_out.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("urls", "estados", "segundos")}, ensure_ascii=False), "muertas:", len(muertas))
    for m in muertas[:40]:
        print("  ", m.get("status"), m.get("error") or "", m["url"][-70:], m["donde"][:2])


if __name__ == "__main__":
    main()
