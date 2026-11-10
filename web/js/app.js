/* Mapa de Pharloom — Hollow Knight: Silksong
 *
 * Coordenadas: o dataset guarda lat/lng já no espaço do Leaflet com CRS.Simple
 * (lat = pos[0]/2, lng = pos[1]/2). O mapa completo tem 1024x1024 unidades no
 * zoom 0 e cada nível dobra a resolução, até 81920x60416 px no zoom 7.
 */
(function () {
  "use strict";

  var CHAVE = "pharloom.progresso.v1";
  var TILE = 1024;
  var ZOOM_MAX_ABSOLUTO = 7;          // nível 1 dos tiles de origem
  var PIXEL_TRANSPARENTE =
    "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

  var mapa, dados, limitesConteudo;
  var camadaMarcadores, camadaAreas;
  var porId = {};                      // uid -> marcador
  var visiveis = {};                   // id da categoria -> bool
  var coletados = carregarProgresso();
  var marcadoresNaTela = new Map();    // uid -> L.Marker
  var catPorId = {};

  // ------------------------------------------------------------- início
  iniciar();

  function iniciar() {
    Promise.all([
      buscarJson("dados/mapa.json"),
      buscarJson("tiles/niveis.json").catch(function () { return null; })
    ]).then(function (res) {
      dados = res[0];
      montarMapa(res[1]);
      montarPainel();
      ligarEventos();
      redesenhar();
      atualizarProgresso();
    }).catch(mostrarErro);
  }

  function buscarJson(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + " → HTTP " + r.status);
      return r.json();
    });
  }

  function mostrarErro(e) {
    var d = document.createElement("div");
    d.className = "aviso";
    d.innerHTML =
      "<div><strong>Não consegui carregar os dados do mapa.</strong>" +
      "<p>Abra a pasta <code>web/</code> por um servidor local — o navegador bloqueia " +
      "<code>fetch</code> em arquivos abertos direto do disco.</p>" +
      "<code>python -m http.server -d web 8000</code>" +
      "<p>E confira se os tiles já foram baixados:</p>" +
      "<code>python scripts/baixar_tiles.py</code>" +
      "<p style='opacity:.6;margin-top:14px'>" + String(e && e.message || e) + "</p></div>";
    document.body.appendChild(d);
  }

  // -------------------------------------------------------------- mapa
  function montarMapa(niveis) {
    var zoomNativoMax = 4;
    if (niveis && niveis.niveis && niveis.niveis.length) {
      // nível de tile 1 == zoom 7 do Leaflet
      zoomNativoMax = 8 - Math.min.apply(null, niveis.niveis);
    }
    zoomNativoMax = Math.max(2, Math.min(ZOOM_MAX_ABSOLUTO, zoomNativoMax));

    mapa = L.map("mapa", {
      crs: L.CRS.Simple,
      minZoom: 1,
      maxZoom: Math.min(ZOOM_MAX_ABSOLUTO + 1, zoomNativoMax + 2),
      zoomControl: true,
      attributionControl: true,
      preferCanvas: false,
      zoomSnap: 0.5,
      wheelPxPerZoomLevel: 90
    });

    var Tiles = L.TileLayer.extend({
      getTileUrl: function (c) {
        return "tiles/" + (8 - c.z) + "_" + c.x + "_" + c.y + ".webp";
      }
    });

    new Tiles("", {
      tileSize: TILE,
      minZoom: 1,
      maxNativeZoom: zoomNativoMax,
      noWrap: true,
      errorTileUrl: PIXEL_TRANSPARENTE,
      attribution:
        'Arte do mapa © Team Cherry · dados da comunidade ' +
        '<a href="https://github.com/RainingChain/silksong-map-data" target="_blank" rel="noopener">' +
        'RainingChain/silksong-map-data</a>'
    }).addTo(mapa);

    // limites do conteúdo (81920x60416 px no zoom 7 → /128 no zoom 0)
    var sul = -(60416 / 128), leste = 81920 / 128;
    mapa.setMaxBounds(L.latLngBounds([sul - 40, -40], [40, leste + 40]));

    camadaAreas = L.layerGroup().addTo(mapa);
    camadaMarcadores = L.layerGroup().addTo(mapa);

    limitesConteudo = L.latLngBounds([sul, 0], [0, leste]);
    mapa.fitBounds(limitesConteudo, { padding: [12, 12] });
    window.mapaPharloom = mapa;   // útil para depurar no console

    mapa.on("moveend zoomend", redesenhar);
    mapa.on("zoomend", escalaDosPinos);
    escalaDosPinos();
    mapa.on("mousemove", function (e) {
      document.getElementById("dica-coords").textContent =
        (e.latlng.lat * 2).toFixed(1) + " , " + (e.latlng.lng * 2).toFixed(1);
    });

    desenharAreas();
  }

  function escalaDosPinos() {
    var z = mapa.getZoom();
    var f = z <= 1 ? 0.5 : z <= 2 ? 0.62 : z <= 3 ? 0.78 : z <= 4 ? 0.9 : 1;
    mapa.getContainer().style.setProperty("--escala-pino", f);
  }

  function desenharAreas() {
    dados.areas.forEach(function (a) {
      var principal = a.nome === a.nome.toUpperCase();
      L.marker([a.lat, a.lng], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: "",
          html: '<div class="rotulo-area" style="color:' + a.cor +
                ";font-size:" + (principal ? 12 : 10) + "px" +
                ";opacity:" + (principal ? 1 : .8) + '">' + escapar(a.nome) + "</div>",
          iconSize: [0, 0]
        })
      }).addTo(camadaAreas);
    });
  }

  // --------------------------------------------------------- marcadores
  function uidDe(m) { return m.c + "@" + m.lat + "," + m.lng + "#" + m.i; }

  function redesenhar() {
    if (!mapa) return;
    var ocultarColetados = document.getElementById("opt-ocultar-coletados").checked;
    var limites = mapa.getBounds().pad(0.25);
    var querem = new Set();

    dados.marcadores.forEach(function (m) {
      if (!visiveis[m.c]) return;
      var uid = uidDe(m);
      if (ocultarColetados && coletados[uid]) return;
      if (!limites.contains([m.lat, m.lng])) return;
      querem.add(uid);
      if (!marcadoresNaTela.has(uid)) {
        marcadoresNaTela.set(uid, criarMarcador(m, uid).addTo(camadaMarcadores));
      }
    });

    marcadoresNaTela.forEach(function (mk, uid) {
      if (!querem.has(uid)) {
        camadaMarcadores.removeLayer(mk);
        marcadoresNaTela.delete(uid);
      }
    });
  }

  function criarMarcador(m, uid) {
    var cat = catPorId[m.c];
    var tam = tamanhoPino(m.c);
    var mk = L.marker([m.lat, m.lng], {
      title: m.n,
      riseOnHover: true,
      icon: L.divIcon({
        className: "",
        html: '<div class="pino' + (coletados[uid] ? " coletado" : "") +
              '" data-uid="' + escapar(uid) + '" style="width:' + tam + "px;height:" + tam +
              "px;background:" + cat.cor + '">' + cat.glifo + "</div>",
        iconSize: [tam, tam],
        iconAnchor: [tam / 2, tam / 2],
        popupAnchor: [0, -tam / 2]
      })
    });
    mk.bindPopup(function () { return conteudoPopup(m, uid); }, { closeButton: true });
    return mk;
  }

  function tamanhoPino(cat) {
    if (cat === "shortcut" || cat === "rosary" || cat === "shard" || cat === "permFlags") return 15;
    if (cat === "boss" || cat === "ability" || cat === "heart" || cat === "crest") return 24;
    return 20;
  }

  function conteudoPopup(m, uid) {
    var cat = catPorId[m.c];
    var el = document.createElement("div");
    var tags = "";
    if (m.atos && m.atos.length) {
      tags += m.atos.map(function (a) {
        return '<span class="tag">Ato ' + escapar(String(a)) + "</span>";
      }).join("");
    }
    if (m.perdivel) tags += '<span class="tag perdivel">perdível</span>';

    el.innerHTML =
      '<div class="pop-cat">' + escapar(cat.nome) + "</div>" +
      '<p class="pop-nome">' + escapar(m.n || cat.nome) + "</p>" +
      (m.nota ? '<p class="pop-nota">' + escapar(m.nota) + "</p>" : "") +
      (tags ? '<div class="pop-tags">' + tags + "</div>" : "") +
      '<button type="button" class="btn-coletar' + (coletados[uid] ? " feito" : "") + '">' +
      (coletados[uid] ? "✓ coletado" : "marcar como coletado") + "</button>";

    el.querySelector(".btn-coletar").addEventListener("click", function () {
      alternarColetado(uid);
      mapa.closePopup();
    });
    return el;
  }

  function alternarColetado(uid) {
    if (coletados[uid]) delete coletados[uid];
    else coletados[uid] = 1;
    salvarProgresso();
    var mk = marcadoresNaTela.get(uid);
    if (mk) { camadaMarcadores.removeLayer(mk); marcadoresNaTela.delete(uid); }
    redesenhar();
    atualizarProgresso();
  }

  // ------------------------------------------------------------ painel
  function montarPainel() {
    dados.categorias.forEach(function (c) { catPorId[c.id] = c; });

    var porGrupo = {};
    dados.categorias.forEach(function (c) {
      (porGrupo[c.grupo] = porGrupo[c.grupo] || []).push(c);
    });

    var nav = document.getElementById("camadas");
    dados.grupos.forEach(function (g) {
      var cats = porGrupo[g.id];
      if (!cats || !cats.length) return;

      var det = document.createElement("details");
      det.className = "grupo";
      det.open = g.visivel;

      var total = cats.reduce(function (s, c) { return s + c.total; }, 0);
      var sum = document.createElement("summary");
      sum.innerHTML = "<span>" + escapar(g.nome) + "</span><span>" + total + "</span>";
      det.appendChild(sum);

      cats.forEach(function (c) {
        visiveis[c.id] = !!g.visivel;
        var lab = document.createElement("label");
        lab.className = "cat-item";
        lab.dataset.cat = c.id;
        lab.innerHTML =
          '<input type="checkbox"' + (g.visivel ? " checked" : "") + ">" +
          '<span class="glifo" style="background:' + c.cor + '">' + c.glifo + "</span>" +
          '<span class="nome">' + escapar(c.nome) + "</span>" +
          '<span class="cont" data-cont="' + c.id + '"></span>';
        lab.querySelector("input").addEventListener("change", function (e) {
          visiveis[c.id] = e.target.checked;
          redesenhar();
        });
        det.appendChild(lab);
      });

      nav.appendChild(det);
    });
  }

  function atualizarProgresso() {
    var totalGeral = 0, feitosGeral = 0;
    var porCat = {};
    dados.marcadores.forEach(function (m) {
      porCat[m.c] = porCat[m.c] || { t: 0, f: 0 };
      porCat[m.c].t++;
      totalGeral++;
      if (coletados[uidDe(m)]) { porCat[m.c].f++; feitosGeral++; }
    });

    dados.categorias.forEach(function (c) {
      var p = porCat[c.id] || { t: c.total, f: 0 };
      var el = document.querySelector('[data-cont="' + c.id + '"]');
      if (el) el.textContent = p.f + "/" + p.t;
      var lab = document.querySelector('.cat-item[data-cat="' + c.id + '"]');
      if (lab) lab.classList.toggle("completa", p.t > 0 && p.f === p.t);
    });

    var pct = totalGeral ? (feitosGeral / totalGeral * 100) : 0;
    document.getElementById("barra-geral").style.width = pct.toFixed(1) + "%";
    document.getElementById("texto-progresso").textContent =
      feitosGeral + " / " + totalGeral + "  (" + pct.toFixed(1) + "%)";
  }

  // ------------------------------------------------------------- busca
  function buscar(termo) {
    var lista = document.getElementById("resultados");
    termo = termo.trim().toLowerCase();
    if (termo.length < 2) { lista.hidden = true; lista.innerHTML = ""; return; }

    var achados = [];
    for (var i = 0; i < dados.marcadores.length && achados.length < 40; i++) {
      var m = dados.marcadores[i];
      var nome = (m.n || "") + " " + (m.nota || "") + " " + catPorId[m.c].nome;
      if (nome.toLowerCase().indexOf(termo) >= 0) achados.push(m);
    }

    lista.innerHTML = "";
    if (!achados.length) {
      lista.innerHTML = '<li style="color:#7d8ba3;cursor:default">nada encontrado</li>';
      lista.hidden = false;
      return;
    }
    achados.forEach(function (m) {
      var li = document.createElement("li");
      li.innerHTML = escapar(m.n || catPorId[m.c].nome) +
        '<span class="cat">' + escapar(catPorId[m.c].nome) + "</span>";
      li.addEventListener("click", function () { irPara(m); });
      lista.appendChild(li);
    });
    lista.hidden = false;
  }

  function irPara(m) {
    if (!visiveis[m.c]) {
      visiveis[m.c] = true;
      var cb = document.querySelector('.cat-item[data-cat="' + m.c + '"] input');
      if (cb) cb.checked = true;
    }
    mapa.setView([m.lat, m.lng], Math.max(mapa.getZoom(), 5), { animate: true });
    redesenhar();
    var uid = uidDe(m);
    setTimeout(function () {
      var mk = marcadoresNaTela.get(uid);
      if (mk) {
        mk.openPopup();
        var el = mk.getElement() && mk.getElement().querySelector(".pino");
        if (el) { el.classList.add("realce"); setTimeout(function(){ el.classList.remove("realce"); }, 3500); }
      }
    }, 320);
  }

  // ----------------------------------------------------------- eventos
  function ligarEventos() {
    document.getElementById("busca").addEventListener("input", function (e) {
      buscar(e.target.value);
    });
    document.addEventListener("click", function (e) {
      if (!e.target.closest(".busca")) document.getElementById("resultados").hidden = true;
    });

    document.getElementById("opt-ocultar-coletados").addEventListener("change", redesenhar);
    document.getElementById("opt-areas").addEventListener("change", function (e) {
      if (e.target.checked) camadaAreas.addTo(mapa);
      else mapa.removeLayer(camadaAreas);
    });

    document.getElementById("alternar-painel").addEventListener("click", function () {
      document.getElementById("painel").classList.toggle("oculto");
      setTimeout(function () { mapa.invalidateSize(); }, 240);
    });

    document.querySelectorAll("[data-acao]").forEach(function (b) {
      b.addEventListener("click", function () {
        var ligar = b.dataset.acao === "todos";
        dados.categorias.forEach(function (c) { visiveis[c.id] = ligar; });
        document.querySelectorAll(".cat-item input").forEach(function (cb) { cb.checked = ligar; });
        redesenhar();
      });
    });

    document.getElementById("btn-enquadrar").addEventListener("click", function () {
      mapa.fitBounds(limitesConteudo, { padding: [12, 12] });
    });

    document.getElementById("btn-zerar").addEventListener("click", function () {
      if (!confirm("Zerar todo o progresso marcado neste navegador?")) return;
      coletados = {};
      salvarProgresso();
      marcadoresNaTela.forEach(function (mk) { camadaMarcadores.removeLayer(mk); });
      marcadoresNaTela.clear();
      redesenhar();
      atualizarProgresso();
    });
  }

  // --------------------------------------------------------- progresso
  function carregarProgresso() {
    try { return JSON.parse(localStorage.getItem(CHAVE)) || {}; }
    catch (e) { return {}; }
  }
  function salvarProgresso() {
    try { localStorage.setItem(CHAVE, JSON.stringify(coletados)); } catch (e) { /* modo privado */ }
  }

  function escapar(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
})();
