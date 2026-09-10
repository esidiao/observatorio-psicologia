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

/* As escalas saem das VARIÁVEIS DO CSS, não de uma cópia aqui.
   Duas listas com a mesma informação divergem em silêncio: ao trocar a paleta
   deste projeto, o CSS virou índigo e esta cópia continuou teal — a tabela do
   índice e todo mapa de indicador sequencial passaram a desenhar na cor do
   observatório irmão, sem erro no console e sem nada que acusasse. É o mesmo
   defeito que o catálogo único de indicadores existe para impedir, cometido na
   camada de cor.

   A lista literal fica só como socorro: se o CSS não tiver carregado quando
   isto rodar, um mapa cinza é pior que um mapa em cor aproximada. */
/* Cor institucional pelo NOME do token. Mesma razão de `_escalaDoCss`:
   hexadecimal repetido no JS é uma cópia que sobrevive à troca de
   paleta e passa a mostrar a cor de outro projeto. */
function cor(nome, reserva) {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue('--' + nome).trim();
  return v || reserva || '#262B54';
}

function _escalaDoCss(prefixo, n, reserva) {
  const raiz = getComputedStyle(document.documentElement);
  const cores = [];
  for (let i = 1; i <= n; i++) {
    const c = raiz.getPropertyValue('--' + prefixo + '-' + i).trim();
    if (!c) return reserva;
    cores.push(c);
  }
  return cores;
}

const RDBU = _escalaDoCss('rdbu', 9,
  ['#2166AC', '#4393C3', '#92C5DE', '#D1E5F0', '#F7F7F7',
   '#FDDBC7', '#F4A582', '#D6604D', '#B2182B']);
const SEQ = _escalaDoCss('seq', 8,
  ['#EFF1F9', '#D8DCEF', '#BCC3E2', '#9AA4D0',
   '#7784BC', '#43509A', '#333A72', '#262B54']);

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
 * Célula colorida: o texto escolhe a cor pelo fundo que recebeu
 * ------------------------------------------------------------------ */

/* Uma escala sequencial vai do quase branco ao índigo profundo, e uma
   divergente vai do azul escuro ao vermelho escuro passando pelo branco.
   NENHUMA cor fixa de texto serve para as duas pontas: escura some no extremo
   escuro, clara some no claro. Medido no site: o primeiro colocado do ranking
   saía com contraste 1,33, e o rho mais forte da matriz com 2,81 — nas duas
   células que a cor manda o leitor olhar primeiro.

   `pintarCelula` mede a luminância relativa do fundo e escolhe entre o texto
   institucional e o papel claro, ficando com o que tiver mais contraste. */
function _luminancia(cor) {
  const m = String(cor).match(/[\d.]+/g);
  if (!m || m.length < 3) return 1;
  const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(+m[0]) + 0.7152 * f(+m[1]) + 0.0722 * f(+m[2]);
}

function _hexParaRgb(cor) {
  const h = String(cor).trim();
  if (h.charAt(0) !== '#') return h;
  const n = h.length === 4
    ? h.slice(1).split('').map(c => c + c)
    : [h.slice(1, 3), h.slice(3, 5), h.slice(5, 7)];
  return 'rgb(' + n.map(x => parseInt(x, 16)).join(', ') + ')';
}

function _contraste(a, b) {
  const l1 = _luminancia(a), l2 = _luminancia(b);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

const TEXTO_ESCURO = 'rgb(26, 29, 51)';
const TEXTO_CLARO = 'rgb(243, 244, 250)';

const PAPEL = [250, 250, 252];

function _canais(cor) {
  const m = String(_hexParaRgb(cor)).match(/[\d.]+/g);
  return m ? m.slice(0, 3).map(Number) : [255, 255, 255];
}

function _rgb(c) {
  return 'rgb(' + c.map(v => Math.round(v)).join(', ') + ')';
}

/* Clareia a cor em direção ao papel até o texto escuro alcançar `alvo`.
   Devolve a primeira mistura que passa, ou o papel puro se nem ele bastar —
   o que não acontece, porque o papel contra o texto mede quase 15. */
function _clarearAte(cor, alvo) {
  const base = _canais(cor);
  for (let passo = 0; passo <= 20; passo++) {
    const t = passo / 20;
    const mistura = base.map((v, i) => v + (PAPEL[i] - v) * t);
    if (_contraste(TEXTO_ESCURO, _rgb(mistura)) >= alvo) return _rgb(mistura);
  }
  return _rgb(PAPEL);
}

function pintarCelula(td, cor) {
  const rgb = _hexParaRgb(cor);
  const escuro = _contraste(TEXTO_ESCURO, rgb);
  const claro = _contraste(TEXTO_CLARO, rgb);
  if (Math.max(escuro, claro) >= 4.5) {
    td.style.background = cor;
    td.style.color = escuro >= claro ? TEXTO_ESCURO : TEXTO_CLARO;
    return;
  }
  /* Tom intermediário: não carrega texto escuro nem claro. Em vez de aceitar
     um contraste ruim — ou de esvaziar a célula, o que interrompe o degradê
     no meio e o leitor lê como defeito —, o fundo é clareado em direção ao
     papel até o texto escuro passar. O degradê continua contínuo e o número
     continua legível. */
  td.style.background = _clarearAte(cor, 4.5);
  td.style.color = TEXTO_ESCURO;
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
        this.setStyle({ weight: 2.5, color: cor('deep') });
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
