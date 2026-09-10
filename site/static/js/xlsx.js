/* ============================================================
 * Escritor de XLSX, sem biblioteca.
 *
 * A pasta de trabalho COMPLETA é gerada no build (site/planilha.py) e
 * publicada em dados/observatorio-psicologia.xlsx. Este arquivo resolve
 * outro problema: as páginas de comparação e de índice mostram o recorte que o
 * LEITOR escolheu — indicadores, estados, pesos — e é esse recorte que ele quer
 * levar. Um botão que baixasse o arquivo do build entregaria outra coisa e
 * pareceria defeito.
 *
 * Por que à mão: um empacotador de XLSX custa centenas de kilobytes para
 * produzir o que cabe aqui, e o site carrega tudo do próprio domínio para
 * funcionar offline. Cada dependência é peso que o leitor no celular paga.
 *
 * O ZIP usa método STORE, sem compressão: dispensa carregar um compressor, e
 * uma planilha de trinta linhas não tem o que comprimir.
 * ============================================================ */

'use strict';

const XLSX_CRC = (function () {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1);
    t[n] = c >>> 0;
  }
  return t;
})();

function xlsxCrc32(bytes) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < bytes.length; i++) {
    c = XLSX_CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
  }
  return (c ^ 0xFFFFFFFF) >>> 0;
}

function xlsxEscapar(texto) {
  return String(texto)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    /* Caracteres de controle são ilegais em XML 1.0. Um deles no meio de um
       nome próprio produz um arquivo que o Excel recusa a abrir, com uma
       mensagem que não diz onde está o problema. */
    .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, '');
}

function xlsxColuna(n) {
  let s = '';
  while (n > 0) {
    const r = (n - 1) % 26;
    s = String.fromCharCode(65 + r) + s;
    n = (n - r - 1) / 26;
  }
  return s;
}

function xlsxZipStore(arquivos) {
  const cod = new TextEncoder();
  const partes = [];
  const central = [];
  let deslocamento = 0;

  arquivos.forEach(function (a) {
    const nome = cod.encode(a.nome);
    const dados = cod.encode(a.conteudo);
    const crc = xlsxCrc32(dados);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);
    local.setUint16(4, 20, true);
    /* Bit 11 do general purpose flag: nomes em UTF-8. */
    local.setUint16(6, 0x0800, true);
    local.setUint16(8, 0, true);                 /* método STORE */
    local.setUint32(14, crc, true);
    local.setUint32(18, dados.length, true);
    local.setUint32(22, dados.length, true);
    local.setUint16(26, nome.length, true);
    partes.push(new Uint8Array(local.buffer), nome, dados);

    const cd = new DataView(new ArrayBuffer(46));
    cd.setUint32(0, 0x02014b50, true);
    cd.setUint16(4, 20, true);
    cd.setUint16(6, 20, true);
    cd.setUint16(8, 0x0800, true);
    cd.setUint16(10, 0, true);
    cd.setUint32(16, crc, true);
    cd.setUint32(20, dados.length, true);
    cd.setUint32(24, dados.length, true);
    cd.setUint16(28, nome.length, true);
    cd.setUint32(42, deslocamento, true);
    central.push(new Uint8Array(cd.buffer), nome);

    deslocamento += 30 + nome.length + dados.length;
  });

  let tamanhoCentral = 0;
  central.forEach(function (p) { tamanhoCentral += p.length; });

  const fim = new DataView(new ArrayBuffer(22));
  fim.setUint32(0, 0x06054b50, true);
  fim.setUint16(8, arquivos.length, true);
  fim.setUint16(10, arquivos.length, true);
  fim.setUint32(12, tamanhoCentral, true);
  fim.setUint32(16, deslocamento, true);

  const todas = partes.concat(central, [new Uint8Array(fim.buffer)]);
  let total = 0;
  todas.forEach(function (p) { total += p.length; });
  const saida = new Uint8Array(total);
  let pos = 0;
  todas.forEach(function (p) { saida.set(p, pos); pos += p.length; });
  return saida;
}

/* Monta o XLSX de uma matriz [[cabeçalho...], [linha...], ...].
   Número entra como número; ausência entra como célula AUSENTE — nunca zero e
   nunca o texto "sem dados". Numa planilha os dois contaminam toda fórmula que
   atravesse a coluna, e é justamente a diferença que este projeto preserva. */
function xlsxDeMatriz(nomeAba, matriz) {
  const linhas = matriz.map(function (linha, i) {
    const celulas = linha.map(function (v, j) {
      if (v === null || v === undefined || v === '') return '';
      const ref = xlsxColuna(j + 1) + (i + 1);
      if (typeof v === 'number' && isFinite(v)) {
        return '<c r="' + ref + '"><v>' + v + '</v></c>';
      }
      return '<c r="' + ref + '" t="inlineStr"><is><t xml:space="preserve">'
        + xlsxEscapar(v) + '</t></is></c>';
    }).join('');
    return '<row r="' + (i + 1) + '">' + celulas + '</row>';
  }).join('');

  const sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    + '<sheetViews><sheetView workbookViewId="0">'
    + '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
    + '</sheetView></sheetViews>'
    + '<sheetData>' + linhas + '</sheetData></worksheet>';

  const tipos = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    + '<Default Extension="xml" ContentType="application/xml"/>'
    + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    + '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    + '</Types>';

  const rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
    + '</Relationships>';

  const workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    + ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    + '<sheets><sheet name="' + xlsxEscapar(nomeAba).slice(0, 31)
    + '" sheetId="1" r:id="rId1"/></sheets></workbook>';

  const wbRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
    + '</Relationships>';

  return xlsxZipStore([
    { nome: '[Content_Types].xml', conteudo: tipos },
    { nome: '_rels/.rels', conteudo: rels },
    { nome: 'xl/workbook.xml', conteudo: workbook },
    { nome: 'xl/_rels/workbook.xml.rels', conteudo: wbRels },
    { nome: 'xl/worksheets/sheet1.xml', conteudo: sheet }
  ]);
}

/* Lê a tabela do DOM preservando o TIPO. `data-valor` traz o número cru, que é
   o que deve ir para a planilha; o texto visível já está formatado em pt-BR e
   entraria como string, inutilizando soma e ordenação. */
function xlsxDaTabela(tabela) {
  const matriz = [];
  matriz.push(Array.prototype.slice.call(tabela.tHead.rows[0].cells)
    .map(function (c) { return c.textContent.trim(); }));
  Array.prototype.slice.call(tabela.tBodies[0].rows).forEach(function (linha) {
    matriz.push(Array.prototype.slice.call(linha.cells).map(function (c) {
      const bruto = c.dataset.valor;
      if (bruto === undefined) {
        const t = c.textContent.trim();
        return (t === 'sem dados' || t === '') ? null : t;
      }
      if (bruto === '') return null;
      const n = parseFloat(bruto);
      return (!isNaN(n) && String(n) === String(bruto).trim()) ? n : bruto;
    }));
  });
  return matriz;
}

function xlsxAtivarBotoes() {
  document.querySelectorAll('[data-exportar-xlsx]').forEach(function (botao) {
    if (botao.dataset.xlsxAtivo === '1') return;
    botao.dataset.xlsxAtivo = '1';
    botao.addEventListener('click', function () {
      const tabela = document.querySelector(botao.dataset.exportarXlsx);
      if (!tabela || !tabela.tHead || !tabela.tBodies.length) return;
      const bytes = xlsxDeMatriz(botao.dataset.aba || 'Dados',
                                 xlsxDaTabela(tabela));
      const url = URL.createObjectURL(new Blob([bytes], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      }));
      const a = document.createElement('a');
      a.href = url;
      a.download = botao.dataset.nome || 'observatorio-psicologia.xlsx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    });
  });
}

document.addEventListener('DOMContentLoaded', xlsxAtivarBotoes);
