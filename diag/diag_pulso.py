#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnóstico TEMPORAL 6: ¿responde Hentaila ahora? Pide el inicio y 2 páginas cada 20 s durante ~4 min y anota estado y
tiempo. Escribe diag/pulso_out.json."""
import json
import os
import time

from curl_cffi import requests as cr

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, "pulso_out.json")
URLS = ["https://hentaila.io/", "https://hentaila.io/?page=2", "https://hentaila.io/?page=7", "https://hentaila.io/?page=15"]


def pedir(url):
    t0 = time.time()
    try:
        r = cr.get(url, headers={"Referer": "https://hentaila.io/"}, impersonate="chrome", timeout=30)
        return {"status": r.status_code, "bytes": len(r.content), "seg": round(time.time() - t0, 2), "cf": r.headers.get("cf-ray", "")[-3:]}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"[:110], "seg": round(time.time() - t0, 2)}


def main():
    out = {"inicio": time.strftime("%H:%M:%S", time.gmtime()), "rondas": []}
    for i in range(12):
        ronda = {"t": time.strftime("%H:%M:%S", time.gmtime())}
        for u in URLS:
            ronda[u.replace("https://hentaila.io", "") or "/"] = pedir(u)
        out["rondas"].append(ronda)
        print(json.dumps(ronda, ensure_ascii=False), flush=True)
        with open(SALIDA, "w", encoding="utf-8", newline="\n") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        time.sleep(15)


if __name__ == "__main__":
    main()
