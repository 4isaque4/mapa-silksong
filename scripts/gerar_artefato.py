# -*- coding: utf-8 -*-
"""Gera artefato/ — a mesma aplicação, empacotada para publicar como Artifact.

A página do Artifact é embrulhada num skeleton HTML no momento da publicação,
então aqui o arquivo não leva <!doctype>, <html>, <head> nem <body>: só o
<title>, o <style> com tudo embutido e o conteúdo. O Leaflet vem da CDN
permitida; o CSS dele é embutido, porque a CSP só aceita folhas de estilo do
Google Fonts.
"""
import os
import re
import shutil

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(RAIZ, "web")
SAIDA = os.path.join(RAIZ, "artefato")

# níveis de tile que cabem no Artifact (8 = visão geral, 3 = 20480x15360 px)
NIVEIS = [8, 7, 6, 5, 4, 3]
LEAFLET_CDN = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js"


def ler(*partes):
    with open(os.path.join(WEB, *partes), encoding="utf-8") as f:
        return f.read()


def main():
    leaflet_css = ler("vendor", "leaflet.css")
    # o CSS do Leaflet referencia images/ só para os marcadores padrão, que não usamos
    leaflet_css = re.sub(r"url\(images/[^)]+\)", "none", leaflet_css)

    estilo = ler("css", "estilo.css")
    app = ler("js", "app.js")

    corpo = ler("index.html")
    corpo = corpo[corpo.index("<div id=\"app\">"):corpo.index("</div>\n\n<script")] + "</div>"

    pagina = f"""<meta charset="utf-8">
<title>Mapa de Pharloom</title>
<style>
{leaflet_css}
{estilo}
</style>

{corpo}

<script src="{LEAFLET_CDN}"></script>
<script>
{app}
</script>
"""

    if os.path.isdir(SAIDA):
        shutil.rmtree(SAIDA)
    os.makedirs(os.path.join(SAIDA, "dados"))
    os.makedirs(os.path.join(SAIDA, "tiles"))

    with open(os.path.join(SAIDA, "index.html"), "w", encoding="utf-8") as f:
        f.write(pagina)
    shutil.copy(os.path.join(WEB, "dados", "mapa.json"),
                os.path.join(SAIDA, "dados", "mapa.json"))

    copiados = 0
    for nome in os.listdir(os.path.join(WEB, "tiles")):
        if not nome.endswith(".webp"):
            continue
        if int(nome.split("_")[0]) not in NIVEIS:
            continue
        shutil.copy(os.path.join(WEB, "tiles", nome), os.path.join(SAIDA, "tiles", nome))
        copiados += 1

    import json
    with open(os.path.join(SAIDA, "tiles", "niveis.json"), "w", encoding="utf-8") as f:
        json.dump({"niveis": sorted(NIVEIS)}, f)

    tam = sum(os.path.getsize(os.path.join(dp, n))
              for dp, _, ns in os.walk(SAIDA) for n in ns)
    print(f"artefato/ pronto: página {len(pagina)/1024:.0f} KB, "
          f"{copiados} tiles, {tam/1e6:.1f} MB no total")


if __name__ == "__main__":
    main()
