#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 5: ¿bajan de verdad las imágenes del top10.json publicado (MuchoHentai y Hentaila) y las de
mas_vistos.json? Escribe diag/top10_out.json."""
import json
import os
import time

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "top10_out.json")
BASE = "https://todesvip.github.io/visor-manga/cine/Archivos/"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")
MAGIAS = (b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF")


def probar(url):
    t0 = time.time()
    try:
        referer = "https://hentaila.io/" if "hentaila.io" in url else None
        h = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}
        if referer:
            h["Referer"] = referer
        r = requests.get(url, headers=h, timeout=40)
        b = r.content or b""
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image/") and any(b.startswith(m) for m in MAGIAS)
        dim = None
        try:
            from PIL import Image
            import io
            im = Image.open(io.BytesIO(b)); dim = list(im.size)
        except Exception:
            pass
        return {"status": r.status_code, "tipo": r.headers.get("content-type"), "bytes": len(b), "dim": dim, "ok": ok, "seg": round(time.time() - t0, 2)}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:160], "ok": False}


def main():
    out = {"inicio": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}
    top = requests.get(BASE + "top10.json?v=" + str(int(time.time())), timeout=60).json()
    mas = requests.get(BASE + "mas_vistos.json?v=" + str(int(time.time())), timeout=60).json()
    out["top10_ts"] = top.get("ts")
    out["top10"] = [{"rank": i["rank"], "title": i["title"], "url": i["imageUrl"], **probar(i["imageUrl"])} for i in top["items"]]
    out["mas_vistos"] = [{"title": i["title"], "url": i["imageUrl"], **probar(i["imageUrl"])} for i in mas["items"]]
    out["top10_ok"] = sum(1 for r in out["top10"] if r["ok"])
    out["mas_vistos_ok"] = sum(1 for r in out["mas_vistos"] if r["ok"])
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("top10 ok:", out["top10_ok"], "/", len(out["top10"]), "| mas_vistos ok:", out["mas_vistos_ok"], "/", len(out["mas_vistos"]))
    for r in out["top10"]:
        print(r["rank"], r.get("status"), r.get("dim"), r.get("bytes"), r["url"][-60:])


if __name__ == "__main__":
    main()
