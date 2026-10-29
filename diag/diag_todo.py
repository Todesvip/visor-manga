#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 4: ¿cuántas portadas del catálogo (las 2541) están muertas AHORA? Se baja cada una (solo el
principio) como lo haría la app, y para las muertas se prueba la portada de hstream.moe. Escribe diag/todo_out.json."""
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "todo_out.json")
CATALOGO = "https://todesvip.github.io/visor-manga/cine/Archivos/catalogo.json"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")
HEADERS = {"User-Agent": UA, "Referer": "https://hentaila.io/", "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
EPISODIO = re.compile(r"-episodio-(\d+)$")
MAGIAS = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")          # jpeg, png, gif, webp

local = threading.local()


def sesion():
    s = getattr(local, "s", None)
    if s is None:
        s = local.s = requests.Session()
        s.headers.update(HEADERS)
    return s


def probar(url, referer=None):
    t0 = time.time()
    try:
        h = {"Referer": referer} if referer else {}
        r = sesion().get(url, headers=h, stream=True, timeout=30)
        cuerpo = b""
        if r.status_code == 200:
            for trozo in r.iter_content(2048):
                cuerpo = trozo
                break
        tipo = r.headers.get("content-type", "")
        r.close()
        ok = r.status_code == 200 and tipo.startswith("image/") and any(cuerpo.startswith(m) for m in MAGIAS)
        return {"status": r.status_code, "tipo": tipo, "ok": ok, "seg": round(time.time() - t0, 2)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:160], "ok": False, "seg": round(time.time() - t0, 2)}


def hstream(slug):
    m = EPISODIO.search(slug)
    if not m:
        return None
    return f"https://hstream.moe/images/hentai/{slug[:m.start()]}/cover-ep-{int(m.group(1))}.webp"


def main():
    t0 = time.time()
    cat = requests.get(CATALOGO, timeout=60).json()
    items = cat["items"]
    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), "catalogo_ts": cat.get("ts"), "total_items": len(items)}
    urls = sorted({i["imageUrl"] for i in items})
    out["urls_distintas"] = len(urls)
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(probar, urls))
    por_url = dict(zip(urls, res))
    muertas = [i for i in items if not por_url[i["imageUrl"]]["ok"]]
    out["muertas"] = [{"slug": i["slug"], "title": i["title"], "imageUrl": i["imageUrl"], **{k: por_url[i["imageUrl"]].get(k) for k in ("status", "tipo", "error")}}
                      for i in muertas]
    estados = {}
    for r in res:
        k = str(r.get("status") or r.get("error", "?")[:30])
        estados[k] = estados.get(k, 0) + 1
    out["estados"] = estados
    out["lentas_mas_de_5s"] = sum(1 for r in res if r.get("seg", 0) > 5)
    # para las muertas: ¿hstream tiene la portada del mismo episodio?
    cand = [(i["slug"], hstream(i["slug"])) for i in muertas]
    cand = [(s, u) for s, u in cand if u]
    with ThreadPoolExecutor(max_workers=6) as ex:
        hs = list(ex.map(lambda su: probar(su[1], "https://hstream.moe/"), cand))
    out["hstream"] = [{"slug": s, "url": u, **r} for (s, u), r in zip(cand, hs)]
    out["hstream_ok"] = sum(1 for r in hs if r["ok"])
    out["segundos"] = round(time.time() - t0, 1)
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("total_items", "urls_distintas", "estados", "lentas_mas_de_5s", "hstream_ok", "segundos")}, ensure_ascii=False, indent=1))
    print("muertas:", len(out["muertas"]))
    for m in out["muertas"][:60]:
        print("  ", m["slug"][:56].ljust(56), m.get("status"), m.get("error") or "", m["imageUrl"][-50:])


if __name__ == "__main__":
    main()
