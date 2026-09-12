# Observatório Nacional da Formação em Psicologia

Site estático data-driven com indicadores de acesso territorial, qualidade e cobertura
assistencial dos cursos de Psicologia no Brasil.

Projeto irmão — e independente — do
[Observatório Nacional da Formação Farmacêutica](https://github.com/esidiao/observatorio-formacao-farmaceutica)
e do [Observatório Nacional da Formação em Fonoaudiologia](https://github.com/esidiao/observatorio-fonoaudiologia).
Compartilha o método e o design system; não compartilha código, dados nem dependências.

## O que este observatório mede

| | Psicologia | Fonoaudiologia, para comparar |
|---|---|---|
| Registros no Censo (rótulo CINE exato) | 1.372 | 939 |
| UFs com oferta presencial | **27** de 27 | 24 |
| Municípios com oferta presencial | 498 | 83 |
| Cursos presenciais | 1.256 | 125 |
| Vagas presenciais | 276.250 | 17.028 |
| Vagas EaD (atribuídas à UF-sede) | **549** | 12.876 |
| Participação da EaD | **0,2%** | 43,1% |
| Polos EaD | 114 registros em 105 municípios | 793 em 618 |
| Matrículas | 375.574 | 22.996 |
| Concluintes | 49.065 | 2.027 |
| IES distintas | 1.032 | 129 |
| Cursos avaliados | 746, no **CPC 2022** | 74, no CPC 2023 |

Fontes de cobertura assistencial, medidas no CNES 202607 e no CadSUAS 202608:

| | |
|---|---|
| Municípios com psicólogo no SUS | 5.523 de 5.571 |
| Psicólogos vinculados ao SUS | 71.542 profissionais distintos |
| Municípios com atenção psicossocial **ofertada ao SUS** | 3.733 |
| Estabelecimentos com serviço 115 **ao SUS** | 12.607 |
| Os mesmos, declarados (SUS ou privado) | 3.797 · 22.481 |
| Municípios com CRAS · CREAS | 5.559 · 2.758 |
| Unidades de CRAS · CREAS | 8.977 · 3.039 |

## O fato que define este observatório: Psicologia é presencial

Das 276.799 vagas anuais, **549 são a distância** — 0,2%. Vinte e cinco das 27 unidades da
federação não têm nenhuma vaga EaD, e quatro (AC, AP, RO, RR) não têm nenhum polo. No CPC
2022, os 746 cursos avaliados são **todos** presenciais, sem uma única exceção.

E a modalidade está encolhendo, não crescendo:

| Edição do Censo | Vagas EaD | Polos |
|---|---|---|
| 2021 | 7.624 | 187 |
| 2022 | 4.057 | 755 |
| 2023 | 2.905 | 204 |
| 2024 | **549** | 114 |

Isso tem duas consequências no código, e as duas estão testadas.

**O tratamento sede/polo continua obrigatório.** 549 vagas é pouco, mas é diferente de
zero. Somar `QT_VG_TOTAL` por `SG_UF` sem separar as camadas de `TP_DIMENSAO` devolve as
vagas EaD zeradas — e num campo pequeno o erro passa despercebido para sempre, porque
ninguém confere números pequenos.

**Zero e ausência não são a mesma coisa.** Um estado sem nenhuma vaga a distância tem
`vagas_ead = 0`: isso é uma medida, e uma medida forte. Um estado cujo dado não pôde ser
apurado tem `vagas_ead = null`. Apagar essa diferença custaria justamente o achado mais
interessante do observatório, e por isso ela é vigiada nas **duas direções** —
`test_ausencia_nunca_e_zero` e `test_zero_de_ead_e_medida_nao_ausencia`.

Os indicadores de EaD ficam recolhidos numa **seção própria**, na home e em cada página de
estado. A seção sai da categoria do catálogo, não de uma lista escrita no template: um
indicador de EaD acrescentado depois entra nela sozinho.

## Estrutura

```
/etl                        Scripts ETL (Python): extração, índices, pipeline
/data                       Dados versionados: nacional.json, _proveniencia.json
/etl/dados                  Recortes brutos — NÃO versionados (ver .gitignore)
/site                       Gerador estático (Python/Jinja2) + templates + assets
/site/dist                  Site gerado — NÃO versionar
/tests                      Portão de qualidade (GO) + integridade + verificador de fontes
/.github/workflows/ci.yml   CI: valida -> constrói -> publica
```

## Fontes

| Indicador | Fonte | Acesso |
|---|---|---|
| Oferta, vagas, matrículas, polos | Censo da Educação Superior 2024 (INEP) | HTTPS, ZIP lido por `Range` |
| CPC, IDD, ENADE, perfil docente | **CPC 2022** (INEP), área PSICOLOGIA | HTTPS |
| Força de trabalho no SUS | CNES — vínculos com CBO `2515xx` | FTP DATASUS |
| Rede psicossocial | CNES — serviço especializado `115` | FTP DATASUS |
| CRAS e CREAS por município | CadSUAS, pela API MI Social (SAGI/MDS) | HTTPS |
| População e municípios | IBGE (agregado 6579; API de localidades) | HTTPS |

### O ciclo é o de 2022, não o de 2023

Psicologia **não está** no CPC 2023 — aquele é o ciclo da saúde e das engenharias. Está no
de 2022, com cobertura praticamente total: 746 cursos em 27 UFs, 740 com CPC contínuo e
**746 com IDD**. Procurar no ciclo errado devolve "área não encontrada", e a leitura óbvia
disso é "o curso não é avaliado" — que seria falso.

O arquivo de 2022 tem três diferenças de formato em relação ao de 2023, e as três falham
parecendo ausência da fonte: o nome é **minúsculo** (`cpc_2022.xlsx`; com maiúscula o
servidor responde 404), a aba chama-se `CPC 2022` **com espaço**, e as colunas vêm com
espaço à esquerda. Por isso `extrair_cpc.py` **descobre** o nome do arquivo, o da aba e o
das colunas em vez de montá-los.

### Três indicadores de cobertura, e nenhuma fusão

Para Psicologia, "onde existe rede pública que absorve quem se forma?" tem **três**
respostas, e nenhuma fonte única as dá:

* **ICAP — força de trabalho.** Municípios com ao menos um vínculo de psicólogo no SUS.
* **ICRP — rede psicossocial.** Municípios com estabelecimento que oferta **ao SUS** o
  serviço 115. A RAPS é política pública, e estabelecimento privado que declara o
  mesmo serviço no cadastro não faz parte dela: medido, sem esse filtro a contagem
  sobe de 12.607 para 22.481 estabelecimentos — 44% do que seria publicado como
  rede pública não atende pelo SUS. O total declarado sai ao lado, nos campos
  terminados em `_total`.

  Na mesma tabela do CNES, a coluna `ST_ATIVO_SN` vem **vazia em todas as linhas**
  deste export. O filtro de serviço inativo que existia no extrator lia coluna
  sempre em branco e nunca excluiu nada — agora a ausência é contada e declarada,
  em vez de disfarçada de filtro.
* **ICAS — socioassistencial.** Municípios com ao menos um CREAS.

Fundir os três exigiria decidir quanto vale "tem psicólogo" contra "tem CAPS" contra "tem
CREAS". Não existe resposta defensável, e a resposta arbitrária ficaria escondida dentro
de um número de aparência objetiva. Ficam separados, com escalas próprias.

Psicologia é das poucas formações cuja absorção pública se reparte entre **duas políticas
nacionais** — saúde e assistência social. É o que distingue este observatório dos irmãos.

#### O serviço 115 em três recortes

As onze classificações do serviço 115 vão da promoção da saúde mental à internação em
regime fechado. Somá-las num número só mediria como equivalentes coisas que a política
pública trata como opostas:

| Recorte | Classificações | Municípios |
|---|---|---|
| Atenção psicossocial comunitária (aberta) | 115/002, 010, 011 | 3.664 |
| Moradia assistida e acolhimento | 115/001, 004, 005, 006, 007 | 396 |
| Leito e regime fechado | 115/003, 008, 009 | 1.368 |

O total conta estabelecimentos **distintos** e por isso **não** é a soma dos três: um mesmo
CAPS pode declarar mais de uma classificação.

O 115/008 chama-se *unidade de atenção em regime residencial*, e o nome puxa para o grupo
da moradia. Ele está em "leito e regime fechado" de propósito: é o código das comunidades
terapêuticas, enquanto residência terapêutica e unidade de acolhimento existem justamente
para desfazer a internação. Agrupar pelo nome juntaria o manicômio com o que veio
substituí-lo. **O agrupamento em três é decisão editorial deste projeto**, não
classificação oficial do Ministério da Saúde.

### O CBO é por prefixo exato, nunca por texto

A família `2515` tem onze ocupações de psicólogo. Casar por texto capturaria três engodos:

```
232160  PROFESSOR DE PSICOLOGIA NO ENSINO MÉDIO
234760  PROFESSOR DE PSICOLOGIA DO ENSINO SUPERIOR
203525  PESQUISADOR EM PSICOLOGIA
```

Docência e pesquisa não são assistência. É o mesmo erro que casar rótulo CINE por
substring cometeria com `Psicopedagogia`, que tem **6.083** registros no Censo contra
1.372 de `Psicologia`.

### O que não foi possível medir

**Não há contagem de psicólogos no SUAS.** O CadSUAS publica total de profissionais por
unidade, sem abertura por ocupação — não existe equivalente do CBO do CNES. Derivar o
número da equipe mínima da NOB-RH/SUAS seria estimativa disfarçada de medição. O indicador
não existe aqui e não foi substituído por aproximação.

**O CRAS não vira índice de cobertura**, por outro motivo: existe em 5.559 dos 5.571
municípios. Uma fração que vale praticamente 1 em toda UF não ordena nada. Ele é publicado
como contagem e densidade, onde a variação é real.

**O microdado do Censo SUAS não foi usado.** Em setembro de 2026 o catálogo de microdados
da SAGI responde com aviso de indisponibilidade por restrição de período eleitoral, e o
conjunto CadSUAS no Portal Brasileiro de Dados Abertos exige chave de API (401). A API MI
Social publica o mesmo cadastro agregado por município, é pública, e é dela que se lê — com
a diferença declarada na proveniência.

**O ICAP está quase saturado.** 5.523 dos 5.571 municípios têm psicólogo vinculado ao SUS.
O índice continua medindo diferença real — 87,5% no Amapá contra 100% em São Paulo, ou
seja, um em cada oito municípios amapaenses sem nenhum psicólogo — mas separa pouco. Quem
quiser comparar a densidade das redes deve olhar **psicólogos por 100 mil habitantes**, que
varia de 18,0 (AM) a 52,6 (AL).

## Rodar localmente

```bash
pip install -r requirements.txt
```

### Gerar o site

```bash
python site/build.py
```

O site sai em `site/dist/`.

### Portões de qualidade (GO)

```bash
python etl/indices.py --autoteste
python site/estatistica.py
python site/catalogo.py
```

Conferem, respectivamente: as fórmulas dos índices contra um estado sintético calculado à
mão; Spearman, valor de p e regressão múltipla contra casos de resultado conhecido; e a
coerência interna do catálogo de indicadores.

### Testes

```bash
python tests/test_catalogo.py
python tests/test_validacao.py
python tests/test_check_fontes.py
```

Rodam como script ou sob `pytest`, se você o tiver instalado.

## Atualizar os dados

```bash
python etl/pipeline.py --check-only          # só verifica se as fontes mudaram
python etl/pipeline.py --ano 2024            # extrai, calcula, valida
python etl/pipeline.py --so-riqueza          # só a guarda de riqueza
python etl/serie.py --anos 2021 2022 2023 2024
```

A extração do CNES leva perto de uma hora, porque o FTP do DATASUS derruba a maior parte
das conexões que usam `REST`. Ela guarda as fatias já filtradas em
`etl/dados/cnes_<competência>/`, então reprocessar a agregação depois é instantâneo. Use
`--pular-cnes` quando estiver mexendo em outra parte.

O pipeline encadeia extração -> índices -> enriquecimento -> **conferência de riqueza** ->
validação, e só grava se tudo passar. A conferência de riqueza compara o número de campos
por UF com o que está em `git show HEAD` e aborta se o novo resultado for mais pobre —
guarda que existe porque, no projeto de Farmácia, republicar por um caminho parcial
derrubou 33 dos 51 campos com todos os testes verdes: nenhum teste checava *presença* de
campo.

## Publicação

O deploy é **automático**. Todo push na `main` que passe pelos portões vai ao ar no GitHub
Pages. Os portões são a única barreira, e por isso não são poucos: portão GO das fórmulas,
portão da estatística, catálogo, três suítes de teste e a guarda de riqueza. `needs:
validar` garante que reprovação nenhuma chegue à publicação.

**Consequência que vale ter em mente:** um commit de dados na `main` publica os dados. Para
experimentar sem publicar, use um branch e abra um pull request — a validação roda igual e
nada vai ao ar.

Em **Actions → CI → Run workflow** ainda há três ações manuais:

| Ação | O que faz |
|---|---|
| `publicar` | valida e publica no GitHub Pages |
| `so-validar` | roda portões, testes e build; não publica |
| `verificar-fontes` | só checa se INEP, CNES ou CadSUAS publicaram edição nova |

A verificação de fontes também roda sozinha toda segunda-feira e abre issue quando encontra
edição nova — ou quando a verificação fica **indeterminada**, que é diferente de não ter
novidade.

## Princípio inegociável

Nenhum indicador é estimado, interpolado ou preenchido por analogia. Sem fonte oficial para
um recorte, o valor é `null` e aparece como **"sem dados"** — nunca zero, nunca média
plausível. Todo número carrega proveniência: fonte, ano e data de extração.

E o recíproco, que neste curso pesa igual: **zero medido é medida**, e aparece como zero.
Vinte e cinco estados sem nenhuma vaga a distância foram apurados e valem zero. Trocar isso
por "sem dados" seria mentir por omissão sobre o traço que distingue a formação em
Psicologia no Brasil.

## Autoria e direitos

**Edson Sidião de Souza Júnior** — sidiao@i9educar.com ·
[Lattes](http://lattes.cnpq.br/9464330669014306)
Farmacêutico, Mestre e Doutor em Medicina Tropical (UFG), avaliador *ad hoc* INEP/MEC há
mais de quinze anos.

O autor **não é psicólogo**. A competência que ele traz é avaliação e regulação do ensino
superior, que independe do curso; a que ele não traz é a de quem exerce a profissão.
Correções de método, de interpretação e de recorte vindas de psicólogos, docentes,
conselhos e entidades da área são bem-vindas e serão creditadas.

© 2026, todos os direitos reservados sobre a obra autoral (Leis 9.610/1998 e 9.609/1998).
Os **dados primários** são públicos e pertencem ao INEP, ao Ministério da Saúde, ao
Ministério do Desenvolvimento Social e ao IBGE; os **indicadores calculados** são liberados
para reúso com citação.

Termos completos, forma de citação e registro de anterioridade em
[`DIREITOS.md`](DIREITOS.md). Ver também [`SECURITY.md`](SECURITY.md) e a página de aviso
legal do site.
