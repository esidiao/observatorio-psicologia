/* ============================================================
 * Observatório Nacional da Formação em Psicologia
 * Formatação, escalas de cor, mapas, tabelas e glossário.
 *
 * Depende de `indicadores.js`, GERADO por site/catalogo.py, que traz
 * INDICADOR_META e GLOSSARIO da mesma estrutura. Um indicador usado aqui sem
 * entrada lá faz o build falhar antes de publicar — nenhum valor cai num
 * fallback silencioso de três casas decimais.
 * ============================================================ */

'use strict';

const SEM_DADOS = 'sem dados';
const COR_SEM_DADOS = '#C9CDD2';

const RDBU = ['#2166AC', '#4393C3', '#92C5DE', '#D1E5F0', '#F7F7F7',
              '#FDDBC7', '#F4A582', '#D6604D', '#B2182B'];
const SEQ = ['#EDF6F4', '#CFE7E3', '#A6D3CC', '#74B8AF',
             '#479B92', '#2A7D74', '#1B6259', '#123F3A'];

/* ------------------------------------------------------------------
 * Formatação
 * ------------------------------------------------------------------ */

/* Ausência é "sem dados", nunca 0. O leitor precisa distinguir "medimos e deu
   zero" de "não existe fonte para isto". */
function fmt(valor, chave) {
  if (valor === null || valor === undefined || valor === '') return SEM_DADOS;
  const meta = INDICADOR_META[chave];
  if (!meta) {
    console.warn('indicador sem entrada no catálogo:', chave);
    return String(valor);
  }
  let v = valor;
  if (meta.mult) v = v * meta.mult;
  if (typeof v !== 'number') return String(v);
  return v.toLocaleString('pt-BR', {
    minimumFractionDigits: meta.dec,
    maximumFractionDigits: meta.dec,
  });
}

function rotulo(chave) {
  const meta = INDICADOR_META[chave];
  return meta ? meta.label : chave;
}

function nomeCompleto(chave) {
  const meta = INDICADOR_META[chave];
  return meta ? meta.nome : chave;
}

function ehSemDados(valor) {
  return valor === null || valor === undefined || valor === '';
}

/* ------------------------------------------------------------------
 * Cores
 * ------------------------------------------------------------------ */

/* Divergente sempre RdBu, nunca RdYlGn: vermelho-verde é a combinação que o
   daltonismo mais comum apaga, e um mapa ilegível para parte dos leitores não
   é um mapa. */
function corDivergente(valor, chave) {
  if (ehSemDados(valor)) return COR_SEM_DADOS;
  const meta = INDICADOR_META[chave];
  if (!meta || meta.min === null || meta.max === null) return SEQ[5];
  let t = (valor - meta.min) / (meta.max - meta.min);
  t = Math.max(0, Math.min(1, t));
  const bomAlto = meta.dir !== 'menor';
  const posicao = bomAlto ? 1 - t : t;
  return RDBU[Math.min(RDBU.length - 1, Math.floor(posicao * RDBU.length))];
}

function corSequencial(valor, chave) {
  if (ehSemDados(valor)) return COR_SEM_DADOS;
  const meta = INDICADOR_META[chave];
  if (!meta || meta.min === null || meta.max === null) return SEQ[5];
  let t = (valor - meta.min) / (meta.max - meta.min);
  t = Math.max(0, Math.min(1, t));
  return SEQ[Math.min(SEQ.length - 1, Math.floor(t * SEQ.length))];
}

function corPara(valor, chave) {
  const meta = INDICADOR_META[chave];
  if (!meta) return COR_SEM_DADOS;
  return meta.dir === 'contextual'
    ? corSequencial(valor, chave)
    : corDivergente(valor, chave);
}

/* Escala de cor para indicadores sem min/max declarados (contagens, vagas):
   o intervalo vem dos próprios dados exibidos, não do catálogo. */
function escalaDinamica(valores) {
  const presentes = valores.filter(v => !ehSemDados(v));
  if (!presentes.length) return () => COR_SEM_DADOS;
  const menor = Math.min.apply(null, presentes);
  const maior = Math.max.apply(null, presentes);
  return function (v) {
    if (ehSemDados(v)) return COR_SEM_DADOS;
    if (maior === menor) return SEQ[4];
    const t = (v - menor) / (maior - menor);
    return SEQ[Math.min(SEQ.length - 1, Math.floor(t * SEQ.length))];
  };
}

function montarLegenda(alvo, chave, valores) {
  if (!alvo) return;
  const meta = INDICADOR_META[chave] || {};
  let paradas;
  if (meta.min !== null && meta.min !== undefined) {
    const escala = meta.dir === 'contextual' ? SEQ : RDBU;
    paradas = escala.map((cor, i) => {
      const t = i / (escala.length - 1);
      const bomAlto = meta.dir !== 'menor';
      const bruto = meta.dir === 'contextual'
        ? meta.min + t * (meta.max - meta.min)
        : (bomAlto ? meta.max - t * (meta.max - meta.min)
                   : meta.min + t * (meta.max - meta.min));
      return { cor: cor, texto: fmt(bruto, chave) };
    });
  } else {
    const presentes = (valores || []).filter(v => !ehSemDados(v));
    const menor = presentes.length ? Math.min.apply(null, presentes) : 0;
    const maior = presentes.length ? Math.max.apply(null, presentes) : 0;
    paradas = SEQ.map((cor, i) => ({
      cor: cor,
      texto: fmt(menor + (i / (SEQ.length - 1)) * (maior - menor), chave),
    }));
  }
  alvo.innerHTML = '';
  paradas.forEach(p => {
    const span = document.createElement('span');
    span.className = 'legenda-item';
    const i = document.createElement('i');
    i.style.background = p.cor;
    span.appendChild(i);
    span.appendChild(document.createTextNode(p.texto));
    alvo.appendChild(span);
  });
  const ausente = document.createElement('span');
  ausente.className = 'legenda-item legenda-ausente';
  const i = document.createElement('i');
  i.style.background = COR_SEM_DADOS;
  ausente.appendChild(i);
  ausente.appendChild(document.createTextNode(SEM_DADOS));
  alvo.appendChild(ausente);
}

/* ------------------------------------------------------------------
 * Mapas
 * ------------------------------------------------------------------ */

/* SEM CAMADA DE TILES.
 *
 * A CARTO passou a exigir chave e devolve tile com marca d'água, então o mapa
 * usa só as malhas do IBGE servidas localmente. Três consequências que não são
 * óbvias, todas medidas neste projeto:
 *
 *  1. `maxZoom` vai nas OPÇÕES DO MAPA. Era a camada de tiles que o definia;
 *     sem ela o Leaflet assume Infinity e o zoom foge.
 *
 *  2. O mapa PRECISA de uma view inicial. A intuição contrária — não definir
 *     center/zoom para o fitBounds ser imediato — foi testada e falha:
 *     `getBoundsZoom` projeta as coordenadas usando o zoom corrente, e num
 *     mapa sem view não há zoom corrente. O cálculo degenera e devolve o
 *     maxZoom. A view nasce em zoom 10 sobre o centro do país, todas as
 *     feições caem fora da janela, o Leaflet as recorta para o caminho "M0 0",
 *     e a área do mapa fica em branco — com os paths no DOM, sem exceção e
 *     sem nada no console. Num mapa com tiles isso se corrigiria no primeiro
 *     arrasto; aqui o enquadramento errado é o único que existe.
 *
 *  3. O que realmente precisa ser evitado é o fitBounds ANIMADO, não a view
 *     inicial. A animação depende de requestAnimationFrame, que não roda em
 *     aba oculta, e deixa o enquadramento travado no meio do caminho. A
 *     proteção certa é `{ animate: false }` no fitBounds — ver desenharMalha.
 *
 * A view semente abaixo é só um ponto de partida para o cálculo; o fitBounds
 * a substitui no mesmo quadro, sem transição visível.
 */
const VIEW_SEMENTE = [-15.0, -54.0];
const ZOOM_SEMENTE = 4;

function criarMapa(elemento) {
  return L.map(elemento, {
    center: VIEW_SEMENTE,
    zoom: ZOOM_SEMENTE,
    zoomControl: true,
    attributionControl: false,
    maxZoom: 10,
    minZoom: 3,
    scrollWheelZoom: false,
    zoomAnimation: false,
  });
}

function desenharMalha(mapa, geojson, opcoes) {
  const valorDe = opcoes.valorDe;
  const chave = opcoes.chave;
  const rotuloDe = opcoes.rotuloDe;
  const aoClicar = opcoes.aoClicar;
  const corDe = opcoes.corDe || (v => corPara(v, chave));

  const camada = L.geoJSON(geojson, {
    style: function (feicao) {
      return {
        fillColor: corDe(valorDe(feicao)),
        fillOpacity: 0.92,
        color: '#FFFFFF',
        weight: 1,
      };
    },
    onEachFeature: function (feicao, camadaFeicao) {
      const valor = valorDe(feicao);
      /* Tooltip montado por DOM, nunca por string com onclick embutido: nomes
         como "Olho d'Água" e "Santa Bárbara d'Oeste" carregam apóstrofo, que
         encerraria a string JS no meio e mataria o clique sem erro visível. */
      const div = document.createElement('div');
      div.className = 'tooltip-mapa';
      const forte = document.createElement('strong');
      forte.textContent = rotuloDe(feicao);
      div.appendChild(forte);
      div.appendChild(document.createElement('br'));
      const span = document.createElement('span');
      span.textContent = rotulo(chave) + ': ' + fmt(valor, chave);
      if (ehSemDados(valor)) span.className = 'sem-dados';
      div.appendChild(span);
      camadaFeicao.bindTooltip(div, { sticky: true });

      camadaFeicao.on('mouseover', function () {
        this.setStyle({ weight: 2.5, color: '#123F3A' });
        this.bringToFront();
      });
      camadaFeicao.on('mouseout', function () {
        this.setStyle({ weight: 1, color: '#FFFFFF' });
      });
      if (aoClicar) camadaFeicao.on('click', () => aoClicar(feicao));
    },
  });

  /* O mapa se REENQUADRA sozinho quando o contêiner ganha tamanho, em vez de
   * esperar por um momento "pronto" que pode não chegar.
   *
   * O caso real: o fetch do GeoJSON resolve do cache do navegador ainda
   * durante o parsing do HTML, com o contêiner medindo 2px de largura — as
   * duas bordas, zero de conteúdo. Nesse estado getBoundsZoom devolve o
   * maxZoom, a view nasce em zoom 10, as feições caem fora da janela e o
   * Leaflet as recorta para "M0 0": área do mapa em branco, paths no DOM,
   * nenhuma exceção, nada no console.
   *
   * Adiar a criação até haver largura foi tentado e não basta: numa aba de
   * fundo o contêiner fica em zero indefinidamente, e tanto requestAnimationFrame
   * quanto ResizeObserver ficam suspensos enquanto a aba não pinta — o mapa
   * simplesmente nunca era criado. Criar sempre e corrigir depois é o que
   * sobrevive aos dois cenários: quem abre a página visível vê o enquadramento
   * certo de imediato; quem abre em aba de fundo vê quando trocar para ela.
   *
   * `animate: false` em todo fitBounds: o caminho animado depende de rAF e
   * deixaria o enquadramento congelado no meio do percurso numa aba oculta. */
  const limites = camada.getBounds();
  function ajustar() {
    if (!limites.isValid()) return;
    mapa.invalidateSize({ animate: false });
    mapa.fitBounds(limites, { padding: [8, 8], animate: false });
  }

  ajustar();
  camada.addTo(mapa);

  mapa.__limites = limites;
  if (!mapa.__observando) {
    mapa.__observando = true;
    const reajustar = function () {
      const largura = mapa.getContainer().getBoundingClientRect().width;
      if (largura > 20 && mapa.__limites) {
        mapa.invalidateSize({ animate: false });
        mapa.fitBounds(mapa.__limites, { padding: [8, 8], animate: false });
      }
    };
    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(reajustar).observe(mapa.getContainer());
    }
    window.addEventListener('resize', reajustar);
    document.addEventListener('visibilitychange', reajustar);
  }
  return camada;
}

/* ------------------------------------------------------------------
 * Tabelas ordenáveis
 * ------------------------------------------------------------------ */

/* Ausência vai SEMPRE para o fim, nas duas direções. Tratar null como zero
   colocaria as UFs sem dado no topo de um ranking ascendente como se fossem
   as melhores — e no fim do descendente como se fossem as piores. As duas
   leituras seriam invenção. */
function ordenarTabela(tabela, indiceColuna, ascendente) {
  const corpo = tabela.tBodies[0];
  const linhas = Array.prototype.slice.call(corpo.rows);
  linhas.sort(function (a, b) {
    const ca = a.cells[indiceColuna];
    const cb = b.cells[indiceColuna];
    const va = ca.dataset.valor;
    const vb = cb.dataset.valor;
    const temA = va !== undefined && va !== '';
    const temB = vb !== undefined && vb !== '';
    if (!temA && !temB) return 0;
    if (!temA) return 1;
    if (!temB) return -1;
    const na = parseFloat(va);
    const nb = parseFloat(vb);
    if (isNaN(na) || isNaN(nb)) {
      return ascendente
        ? String(va).localeCompare(String(vb), 'pt-BR')
        : String(vb).localeCompare(String(va), 'pt-BR');
    }
    return ascendente ? na - nb : nb - na;
  });
  linhas.forEach(l => corpo.appendChild(l));
}

function ativarTabelasOrdenaveis() {
  document.querySelectorAll('table[data-ordenavel]').forEach(function (tabela) {
    if (!tabela.tHead) return;
    /* As páginas que remontam a tabela chamam esta função de novo. Sem a
       marca, cada chamada empilha mais um listener na mesma célula, e o
       terceiro clique dispara três ordenações que se desfazem entre si. */
    if (tabela.dataset.ordenavelAtivo === '1') return;
    tabela.dataset.ordenavelAtivo = '1';
    const celulas = Array.prototype.slice.call(tabela.tHead.rows[0].cells);
    celulas.forEach(function (celula, i) {
      celula.tabIndex = 0;
      celula.classList.add('ordenavel');
      /* Cabecalho criado em JS nao passa pelo template e chegaria sem `scope`.
         Sem ele o leitor de tela le os numeros soltos, sem dizer de que coluna
         sao — numa tabela de oito indicadores, a diferenca entre dado e ruido. */
      if (!celula.getAttribute('scope')) celula.setAttribute('scope', 'col');
      let ascendente = false;
      const acionar = function () {
        ascendente = !ascendente;
        ordenarTabela(tabela, i, ascendente);
        celulas.forEach(function (c) {
          c.removeAttribute('aria-sort');
          c.classList.remove('ordenado-asc', 'ordenado-desc');
        });
        celula.setAttribute('aria-sort', ascendente ? 'ascending' : 'descending');
        celula.classList.add(ascendente ? 'ordenado-asc' : 'ordenado-desc');
      };
      celula.addEventListener('click', acionar);
      celula.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); acionar(); }
      });
    });
  });
}

/* ------------------------------------------------------------------
 * Glossário
 * ------------------------------------------------------------------ */

function normalizarBusca(texto) {
  return String(texto || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '');
}

const SETA_DIRECAO = {
  maior: '↑ maior é melhor',
  menor: '↓ menor é melhor',
  contextual: '· sem juízo normativo',
};

function montarGlossario(container, campoBusca, contador) {
  if (!container) return;

  function render(termo) {
    const alvo = normalizarBusca(termo);
    const porCategoria = {};
    GLOSSARIO.forEach(function (item) {
      if (alvo) {
        const campos = [item.sigla, item.nome, item.oque, item.fonte]
          .concat(item.aliases || []).join(' ');
        if (normalizarBusca(campos).indexOf(alvo) === -1) return;
      }
      (porCategoria[item.cat] = porCategoria[item.cat] || []).push(item);
    });

    container.innerHTML = '';
    let total = 0;
    CATEGORIAS.forEach(function (cat) {
      const itens = porCategoria[cat];
      if (!itens || !itens.length) return;
      total += itens.length;
      const secao = document.createElement('section');
      secao.className = 'glossario-cat';
      const h = document.createElement('h2');
      h.textContent = cat;
      secao.appendChild(h);
      itens.forEach(function (item) {
        const art = document.createElement('article');
        art.className = 'verbete';
        art.id = 'g-' + item.key;

        const h3 = document.createElement('h3');
        const sigla = document.createElement('span');
        sigla.className = 'verbete-sigla';
        sigla.textContent = item.sigla;
        h3.appendChild(sigla);
        h3.appendChild(document.createTextNode(' ' + item.nome));
        art.appendChild(h3);

        const p = document.createElement('p');
        p.textContent = item.oque;
        art.appendChild(p);

        const dl = document.createElement('dl');
        dl.className = 'verbete-meta';
        [['Escala', item.escala],
         ['Direção', SETA_DIRECAO[item.dir] || item.dir],
         ['Fonte', item.fonte]].forEach(function (par) {
          const div = document.createElement('div');
          const dt = document.createElement('dt');
          dt.textContent = par[0];
          const dd = document.createElement('dd');
          dd.textContent = par[1];
          div.appendChild(dt);
          div.appendChild(dd);
          dl.appendChild(div);
        });
        art.appendChild(dl);
        secao.appendChild(art);
      });
      container.appendChild(secao);
    });

    if (!total) {
      const vazio = document.createElement('p');
      vazio.className = 'vazio';
      vazio.textContent = 'Nenhum indicador corresponde a "' + termo + '".';
      container.appendChild(vazio);
    }
    if (contador) {
      contador.textContent = total + (total === 1 ? ' indicador' : ' indicadores');
    }
  }

  render('');
  if (campoBusca) {
    campoBusca.addEventListener('input', function () { render(campoBusca.value); });
  }
}

/* ------------------------------------------------------------------
 * Exportação
 * ------------------------------------------------------------------ */

function baixar(nome, conteudo, tipo) {
  /* BOM na frente: sem ele o Excel em pt-BR lê o UTF-8 como latin-1 e
     "Rondônia" vira "RondÃ´nia" na primeira abertura. */
  const blob = new Blob(['﻿' + conteudo], { type: tipo + ';charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

/* Célula vazia para ausência, nunca 0: um CSV que preenche lacuna com zero
   propaga a invenção para toda planilha que o abrir. */
function tabelaParaCSV(tabela) {
  const linhas = [];
  linhas.push(Array.prototype.slice.call(tabela.tHead.rows[0].cells)
    .map(c => c.textContent.trim()).join(';'));
  Array.prototype.slice.call(tabela.tBodies[0].rows).forEach(function (linha) {
    linhas.push(Array.prototype.slice.call(linha.cells).map(function (c) {
      const v = c.dataset.valor;
      if (v !== undefined) return v;
      const t = c.textContent.trim();
      return t === SEM_DADOS ? '' : t;
    }).join(';'));
  });
  return linhas.join('\n');
}

function ativarExportacoes() {
  document.querySelectorAll('[data-exportar]').forEach(function (botao) {
    botao.addEventListener('click', function () {
      const tabela = document.querySelector(botao.dataset.exportar);
      if (!tabela) return;
      baixar(botao.dataset.nome || 'observatorio-psicologia.csv',
             tabelaParaCSV(tabela), 'text/csv');
    });
  });
}

/* ------------------------------------------------------------------ */

document.addEventListener('DOMContentLoaded', function () {
  ativarTabelasOrdenaveis();
  ativarExportacoes();
  montarGlossario(document.getElementById('glossario'),
                  document.getElementById('busca-glossario'),
                  document.getElementById('glossario-contador'));
});
