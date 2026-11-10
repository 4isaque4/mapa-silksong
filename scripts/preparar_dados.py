# -*- coding: utf-8 -*-
"""Gera dados/mapa.json (pt-BR) a partir do dataset público do mapa de Silksong.

Fonte dos dados: bundle público do visualizador do scripterswar.com, mantido
pela comunidade (repo RainingChain/silksong-map-data). Este script baixa o
bundle, extrai o JSON embutido, traduz nomes com scripts/glossario.py e
converte as coordenadas do jogo para pixels do mapa.

Conversão de coordenadas (calibrada contra o visualizador original):
    x_pixel(z) = pos[1] * 2**(7-z)
    y_pixel(z) = -pos[0] * 2**(7-z)
com z=1 no nível mais detalhado (81920x60416 px) e z=8 na visão geral.
No Leaflet com CRS.Simple e tiles de 1024 px isso vira simplesmente:
    lat = pos[0] / 2        lng = pos[1] / 2

Uso:
    python scripts/preparar_dados.py           # usa cache se existir
    python scripts/preparar_dados.py --baixar  # força rebaixar o bundle
"""
import argparse
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glossario as G  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(RAIZ, "dados")
PAGINA = "https://scripterswar.com/silksong/map"
CACHE_BRUTO = os.path.join(DADOS, "cache", "silksong_live.json")
SAIDA = os.path.join(RAIZ, "web", "dados", "mapa.json")
RELATORIO = os.path.join(DADOS, "nao_traduzidos.txt")

# cor + glifo por categoria (usados para desenhar os pinos no mapa)
ESTILO = {
    "benches":    ("#5ec8f2", "▲"),
    "bellway":    ("#f2c14e", "◉"),
    "ventrica":   ("#f29e4e", "◉"),
    "maps":       ("#9bd68a", "▦"),
    "shortcut":   ("#6b7f9e", "↔"),
    "ability":    ("#ff7bd5", "✦"),
    "tool":       ("#ffd166", "⚒"),
    "crest":      ("#c792ea", "❖"),
    "key":        ("#e8c547", "⚷"),
    "mask":       ("#ff6b6b", "◑"),
    "spool":      ("#f8f0e3", "◎"),
    "locket":     ("#b388ff", "♡"),
    "heart":      ("#ff4d6d", "♥"),
    "kit":        ("#8fd694", "⚙"),
    "pouch":      ("#d9a066", "▬"),
    "upgnail":    ("#e0e0e0", "↑"),
    "craftmetal": ("#a8b2c1", "▭"),
    "misc":       ("#9aa0a6", "•"),
    "rosaryitem": ("#ffe08a", "∵"),
    "rosary":     ("#d4b65e", "●"),
    "sharditem":  ("#8ad6d6", "∷"),
    "shard":      ("#5e9ea0", "●"),
    "flea":       ("#ff9f68", "☸"),
    "tradable":   ("#b5e48c", "⇄"),
    "memento":    ("#dda0dd", "✿"),
    "silkeater":  ("#cfcfcf", "◆"),
    "mapitem":    ("#9bd68a", "▤"),
    "npc":        ("#7ecfff", "☺"),
    "vendor":     ("#ffb347", "€"),
    "wish":       ("#ffd700", "★"),
    "wishitem":   ("#ffec99", "☆"),
    "boss":       ("#ff3b3b", "☠"),
    "arena":      ("#ff8c42", "⚔"),
    "permFlags":  ("#8d99ae", "⚑"),
    "info":       ("#78909c", "ℹ"),
}
PADRAO_ESTILO = ("#9aa0a6", "•")


# ------------------------------------------------------------------ fonte
def obter_bruto(forcar=False):
    """Devolve o dicionário bruto do dataset, baixando o bundle se preciso."""
    if os.path.exists(CACHE_BRUTO) and not forcar:
        with open(CACHE_BRUTO, encoding="utf-8") as f:
            return json.load(f)

    print("Baixando a página do visualizador...")
    with urllib.request.urlopen(PAGINA, timeout=60) as r:
        html = r.read().decode("utf-8", "replace")
    m = re.search(r'src="(/compiled/[^"]*?ssMap\.js[^"]*)"', html)
    if not m:
        sys.exit("Não encontrei o bundle ssMap.js na página.")
    url = "https://scripterswar.com" + m.group(1).replace("&amp;", "&")

    print("Baixando", url)
    with urllib.request.urlopen(url, timeout=120) as r:
        js = r.read().decode("utf-8", "replace")

    alvo = "JSON.parse(" + chr(39) + '{"name":"Silksong"'
    i = js.find(alvo)
    if i < 0:
        sys.exit("Não encontrei o JSON embutido no bundle.")
    ini = js.index(chr(39), i + 10)
    j = ini + 1
    while True:
        j = js.index(chr(39), j)
        if js[j - 1] != chr(92):
            break
        j += 1
    bruto = js[ini + 1:j].encode().decode("unicode_escape").encode("latin1").decode("utf-8")
    dados = json.loads(bruto)

    os.makedirs(os.path.dirname(CACHE_BRUTO), exist_ok=True)
    with open(CACHE_BRUTO, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False)
    print("Cache salvo em", CACHE_BRUTO)
    return dados


# -------------------------------------------------------------- tradução
_pendentes = set()


def traduzir(texto):
    if not texto:
        return texto
    t = texto.strip()
    if t in G.EXATOS:
        return G.EXATOS[t]
    for padrao, destino in G.PADROES:
        novo, n = re.subn(padrao, destino, t)
        if n:
            return novo
    original = t
    for de, para in G.FRAGMENTOS:
        t = t.replace(de, para)
    if t == original:
        _pendentes.add(original)
    return t


# ----------------------------------------------------------------- saída
def construir(bruto):
    im = bruto["interactiveMap"]

    grupos = [{
        "id": g["id"],
        "nome": G.GRUPOS.get(g["id"], g.get("name", g["id"])),
        "visivel": bool(g.get("isVisibleByDefault")),
    } for g in bruto["groups"]]

    categorias, marcadores = [], []
    seq = 0
    for c in bruto["categories"]:
        cid = c["id"]
        cor, glifo = ESTILO.get(cid, PADRAO_ESTILO)
        itens = c.get("list", [])
        categorias.append({
            "id": cid,
            "nome": G.CATEGORIAS.get(cid, c.get("name", cid)),
            "grupo": c.get("group", "misc"),
            "cor": cor,
            "glifo": glifo,
            "total": 0,
        })
        for it in itens:
            pos = it.get("pos")
            if not pos or len(pos) != 2:
                continue
            cru = (it.get("name") or "").strip()
            if any(cru.startswith(p) for p in G.LIXO):
                continue
            nota = it.get("note") or it.get("notes") or ""
            atos = it.get("acts") or ([it["act"]] if it.get("act") else [])
            marcadores.append({
                "i": seq,
                "c": cid,
                "n": traduzir(it.get("name", "")),
                "lat": round(pos[0] / 2, 4),
                "lng": round(pos[1] / 2, 4),
                **({"nota": traduzir(nota)} if nota else {}),
                **({"atos": atos} if atos else {}),
                **({"perdivel": True} if it.get("missable") else {}),
            })
            seq += 1

    contagem = {}
    for m in marcadores:
        contagem[m["c"]] = contagem.get(m["c"], 0) + 1
    for c in categorias:
        c["total"] = contagem.get(c["id"], 0)
    categorias = [c for c in categorias if c["total"]]

    areas = [{
        "nome": l["name"],
        "lat": round(l["pos"][0] / 2, 4),
        "lng": round(l["pos"][1] / 2, 4),
        "cor": l.get("color", "rgba(220,220,220,1)"),
    } for l in bruto.get("locations", []) if l.get("pos")]

    return {
        "fonte": "scripterswar.com/silksong/map (dados mantidos pela comunidade)",
        "mapa": {
            "larguraTotal": im["dim"]["w"],
            "alturaTotal": im["dim"]["h"],
            "larguraConteudo": 81920,
            "alturaConteudo": 60416,
            "tile": im["cropSize"],
            "zoomLeafletMax": 7,
            "urlOriginalTiles": im["url"],
        },
        "grupos": grupos,
        "categorias": categorias,
        "areas": areas,
        "marcadores": marcadores,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--baixar", action="store_true", help="ignora o cache e rebaixa o bundle")
    a = p.parse_args()

    bruto = obter_bruto(a.baixar)
    saida = construir(bruto)

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    os.makedirs(DADOS, exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))

    with open(RELATORIO, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(_pendentes)))

    print(f"{SAIDA}  ->  {len(saida['marcadores'])} marcadores, "
          f"{len(saida['categorias'])} categorias, {len(saida['areas'])} áreas")
    print(f"{os.path.getsize(SAIDA)/1024:.0f} KB")
    print(f"Nomes sem tradução dedicada: {len(_pendentes)} (lista em {RELATORIO})")


if __name__ == "__main__":
    main()
