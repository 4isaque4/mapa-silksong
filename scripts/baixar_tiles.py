# -*- coding: utf-8 -*-
"""Baixa os tiles do mapa de Pharloom para web/tiles/.

A arte do mapa é da Team Cherry e os tiles são servidos pela CDN do
scripterswar.com. Por isso eles NÃO ficam versionados no repositório:
cada pessoa baixa a própria cópia local com este script.

Uso:
    python scripts/baixar_tiles.py            # níveis 6..3 (~24 MB)
    python scripts/baixar_tiles.py --ate 2    # níveis 6..2 (~90 MB)
    python scripts/baixar_tiles.py --ate 1    # tudo (~300 MB, bem lento)

Níveis: 8 é o mais distante (1 tile), 1 é o mais detalhado (81920x60416 px).
"""
import argparse
import concurrent.futures as cf
import os
import sys
import urllib.error
import urllib.request

URL = "https://scripterswarmap.b-cdn.net/ss_v4/{z}_{x}_{y}.webp?v=1"
TILE = 1024

# tamanho da grade (colunas, linhas) por nível de zoom
GRADE = {8: (1, 1), 7: (2, 1), 6: (3, 2), 5: (5, 4),
         4: (10, 8), 3: (20, 15), 2: (40, 30), 1: (80, 59)}

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "web", "tiles")


def baixar(args):
    z, x, y = args
    caminho = os.path.join(DESTINO, f"{z}_{x}_{y}.webp")
    if os.path.exists(caminho) and os.path.getsize(caminho) > 512:
        return "cache"
    try:
        with urllib.request.urlopen(URL.format(z=z, x=x, y=y), timeout=45) as r:
            dados = r.read()
    except urllib.error.HTTPError as e:
        return "vazio" if e.code == 404 else f"erro {e.code}"
    except Exception as e:                                  # noqa: BLE001
        return f"erro {type(e).__name__}"
    if len(dados) < 512:
        return "vazio"
    with open(caminho, "wb") as f:
        f.write(dados)
    return "ok"


def main():
    p = argparse.ArgumentParser(description="Baixa os tiles do mapa de Pharloom.")
    p.add_argument("--ate", type=int, default=3, metavar="N",
                   help="nível de zoom mais detalhado a baixar (1=máximo, padrão 3)")
    p.add_argument("--de", type=int, default=8, metavar="N",
                   help="nível de zoom mais distante a baixar (padrão 8)")
    p.add_argument("--threads", type=int, default=8)
    a = p.parse_args()

    if not 1 <= a.ate <= 8 or not 1 <= a.de <= 8 or a.ate > a.de:
        sys.exit("Níveis inválidos: use 1..8 com --ate <= --de.")

    os.makedirs(DESTINO, exist_ok=True)
    tarefas = []
    for z in range(a.de, a.ate - 1, -1):
        cols, rows = GRADE[z]
        tarefas += [(z, x, y) for x in range(cols) for y in range(rows)]

    print(f"Baixando níveis {a.de}..{a.ate} ({len(tarefas)} tiles possíveis) -> {DESTINO}")
    contagem = {}
    feitos = 0
    with cf.ThreadPoolExecutor(max_workers=a.threads) as ex:
        for status in ex.map(baixar, tarefas):
            contagem[status] = contagem.get(status, 0) + 1
            feitos += 1
            if feitos % 100 == 0:
                print(f"  {feitos}/{len(tarefas)}...", flush=True)

    import json
    presentes = sorted({int(f.split("_")[0]) for f in os.listdir(DESTINO)
                        if f.endswith(".webp")})
    with open(os.path.join(DESTINO, "niveis.json"), "w", encoding="utf-8") as f:
        json.dump({"niveis": presentes}, f)

    total_mb = sum(os.path.getsize(os.path.join(DESTINO, f))
                   for f in os.listdir(DESTINO)) / 1e6
    print(f"Pronto. {contagem}")
    print(f"{len(os.listdir(DESTINO))} tiles em disco, {total_mb:.1f} MB.")


if __name__ == "__main__":
    main()
