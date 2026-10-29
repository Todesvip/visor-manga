#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 8: ¿qué portadas de Hentaila fallan ahora y cuáles son? Todas las de 2026 + una muestra de las
anteriores + los episodios problemáticos. Para las que fallan se prueba la de hstream.moe. Escribe diag/fallos_out.json."""
import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "fallos_out.json")
BASE = "https://todesvip.github.io/visor-manga/cine/Archivos/"
UA = ("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/124.0.0.0 Mobile Safari/537.36")
ESPECIALES = ("oushun-jogakuen", "netorareta-bakunyuu-tsuma-tachi-2", "kokuhaku-episodio", "1ldk-jk-ikinari")
MES = re.compile(r"/uploads/(\d{4})/(\d{2})/")
EP = re.compile(r"^(.+)-episodio-(\d+)$")


def probar(url, referer):
    t0 = time.time()
    try:
        with requests.get(url, headers={"User-Agent": UA, "Referer": referer, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"},
                          stream=True, timeout=20) as r:
            return {"s": r.status_code, "cf": r.headers.get("cf-cache-status"), "age": r.headers.get("age"), "seg": round(time.time() - t0, 1)}
    except Exception as e:
        return {"s": type(e).__name__, "seg": round(time.time() - t0, 1)}


def hstream(slug):
    m = EP.match(slug)
    return f"https://hstream.moe/images/hentai/{m.group(1)}/cover-ep-{int(m.group(2))}.webp" if m else None


def main():
    cat = requests.get(BASE + "catalogo.json?v=" + str(int(time.time())), timeout=90).json()
    items = cat["items"]
    sel, vistos = [], set()
    rnd = random.Random(5)
    def anio(i):
        m = MES.search(i["imageUrl"])
        return m.group(1) if m else "?"

    de2026 = [i for i in items if anio(i) == "2026"]
    otros = [i for i in items if i not in de2026]
    for grupo, lista in (("especial", [i for i in items if any(p in i["slug"] for p in ESPECIALES)]), ("2026", de2026),
                         ("antes", rnd.sample(otros, min(250, len(otros))))):
        for i in lista:
            if i["imageUrl"] not in vistos:
                vistos.add(i["imageUrl"])
                sel.append((grupo, i))
    with ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(lambda gi: probar(gi[1]["imageUrl"], "https://hentaila.io/") if "hentaila.io" in gi[1]["imageUrl"] else probar(gi[1]["imageUrl"], "https://hstream.moe/"), sel))
    filas = []
    for (g, i), r in zip(sel, res):
        m = MES.search(i["imageUrl"])
        filas.append({"g": g, "slug": i["slug"], "mes": f"{m.group(1)}-{m.group(2)}" if m else "?", **r})
    malas = [f for f in filas if f["s"] != 200]
    hs = [(f, hstream(f["slug"])) for f in malas]
    hs = [(f, u) for f, u in hs if u]
    with ThreadPoolExecutor(max_workers=6) as ex:
        rh = list(ex.map(lambda fu: probar(fu[1], "https://hstream.moe/"), hs))
    for (f, u), r in zip(hs, rh):
        f["hstream"] = r["s"]
    por_mes = {}
    for f in filas:
        d = por_mes.setdefault(f["mes"], {"ok": 0, "mal": 0})
        d["ok" if f["s"] == 200 else "mal"] += 1
    out = {"inicio": time.strftime("%H:%M:%S", time.gmtime()), "total_probadas": len(filas), "malas": len(malas),
           "por_mes": dict(sorted(por_mes.items())), "hstream_con_portada": sum(1 for f in malas if f.get("hstream") == 200),
           "hstream_probadas": len(hs), "especiales": [f for f in filas if f["g"] == "especial"],
           "malas_detalle": [{k: f[k] for k in ("slug", "mes", "s", "cf", "hstream") if k in f} for f in malas][:150]}
    with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("total_probadas", "malas", "por_mes", "hstream_con_portada", "hstream_probadas")}, ensure_ascii=False))
    for f in out["especiales"]:
        print(f["slug"][:56].ljust(56), f["s"], f.get("cf"), f.get("age"))


if __name__ == "__main__":
    main()
