"""
site/catalogo.py
Catálogo único dos indicadores: fonte de verdade para formatação, cor,
glossário, agrupamento em seções e exportação.

POR QUE UM CATÁLOGO SÓ
-----------------------
No observatório de Farmácia o glossário mora num arquivo JS e os metadados de
formatação moram em outro. Nada garante que uma entrada exista nos dois, e
quando não existe o valor cai num fallback de três casas decimais: uma contagem
de 19 municípios aparece como `19,000` — dezenove mil, em pt-BR, na página de
uma UF.

Aqui as duas coisas são a MESMA estrutura, em Python, e o build gera o JS a
partir dela. Não é possível registrar um indicador no glossário e esquecer da
formatação, porque são o mesmo registro. `tests/test_catalogo.py` fecha a outra
ponta: todo campo publicado em data/nacional.json e em data/municipios/*.json
precisa estar aqui.

A CATEGORIA TAMBÉM É ESTRUTURA, NÃO ENFEITE
--------------------------------------------
`Ensino a distância` é uma categoria como as outras, e é ela que o site usa
para recolher os indicadores de EaD numa seção própria. A alternativa seria uma
lista de chaves repetida no template, que envelheceria calada assim que alguém
acrescentasse um indicador de EaD e esquecesse de atualizá-la. Aqui a seção sai
do mesmo registro que a formatação e o verbete.

CAMPOS
------
  key        nome do campo no JSON publicado
  sigla      rótulo curto (tabelas, eixos)
  nome       nome por extenso (glossário, tooltips)
  cat        categoria — agrupa no glossário E define a seção na página
  oque       explicação em linguagem corrente, sem jargão
  escala     texto da unidade ("0 a 1", "vagas/ano", "municípios")
  dir        'maior' | 'menor' | 'contextual'  — direção normativa
  fonte      origem do dado
  dec        casas decimais na formatação pt-BR
  min, max   limites para a escala de cor; None = sem escala de cor
  mult       fator aplicado antes de formatar (ex.: fração -> percentual)
  aliases    termos que a busca do glossário também aceita
"""

DIRECOES = {"maior", "menor", "contextual"}

# Escalas que são CONTAGEM. Uma contagem com casa decimal vira outro número em
# pt-BR: `19` com três casas é renderizado `19,000`, que um leitor brasileiro lê
# como dezenove mil. `validar()` reprova a combinação.
CONTAGENS = {"municípios", "cursos", "instituições", "alunos", "vagas/ano",
             "habitantes", "registros", "profissionais", "mantenedoras",
             "estabelecimentos", "unidades"}


def _i(key, sigla, nome, cat, oque, escala, direcao, fonte,
       dec=0, min=None, max=None, mult=None, aliases=()):
    return {
        "key": key, "sigla": sigla, "nome": nome, "cat": cat, "oque": oque,
        "escala": escala, "dir": direcao, "fonte": fonte, "dec": dec,
        "min": min, "max": max, "mult": mult, "aliases": list(aliases),
    }


INDICADORES = [

    # ---------------------------------------------------------------- índices
    _i("ICT", "ICT", "Índice de Concentração Territorial", "Território",
       "Mede o quanto a oferta de vagas se concentra em poucos municípios. "
       "Metade do índice olha a fatia de vagas na capital; a outra metade, a "
       "fração de municípios sem nenhuma oferta. Perto de 1, a formação está "
       "concentrada e o interior fica descoberto.",
       "0 a 1", "menor", "Censo INEP", dec=3, min=0, max=1, aliases=["ict"]),

    _i("E", "E", "Equidade Territorial", "Território",
       "Complemento do ICT (E = 1 − ICT). Quanto maior, mais distribuída pelo "
       "território está a oferta.",
       "0 a 1", "maior", "Calculado", dec=3, min=0, max=1,
       aliases=["equidade"]),

    _i("IAF", "IAF", "Índice de Adequação Formativa", "Qualidade",
       "Combina num só número de 0 a 100 três coisas: a qualidade dos cursos "
       "avaliados (CPC), a fatia das vagas que está em curso avaliado, e a "
       "equidade territorial. Fica em branco quando falta qualquer uma das "
       "três — um IAF calculado sobre dois terços dos componentes não é "
       "comparável com um calculado sobre três.",
       "0 a 100", "maior", "CPC INEP + Censo INEP", dec=1, min=0, max=100,
       aliases=["iaf", "adequação formativa"]),

    _i("ICAP", "ICAP", "Cobertura assistencial — força de trabalho",
       "Cobertura — saúde",
       "Fração dos municípios do estado com ao menos um psicólogo vinculado ao "
       "SUS. Responde à pergunta de onde existe profissional em atividade "
       "capaz de absorver quem se forma. Conta pela família CBO 2515, por "
       "prefixo: casar por texto capturaria professores e pesquisadores de "
       "Psicologia, que não fazem assistência. Leia junto com a densidade: a "
       "presença é quase universal — 5.523 dos 5.571 municípios —, então este "
       "índice separa pouco os estados, e é a quantidade de psicólogos por 100 "
       "mil habitantes que mostra onde a rede é de fato densa.",
       "0 a 1", "maior", "CNES/DATASUS", dec=3, min=0, max=1,
       aliases=["icap", "cobertura", "psicólogos por município"]),

    _i("ICRP", "ICRP", "Cobertura da Rede Psicossocial", "Cobertura — saúde",
       "Fração dos municípios do estado com estabelecimento que oferta AO SUS "
       "atenção psicossocial no CNES (serviço 115, em qualquer das onze "
       "classificações). É a rede pública de saúde mental — CAPS, residências "
       "terapêuticas, unidades de acolhimento e leitos —, e por isso só o que "
       "atende pelo SUS entra: clínica privada que declara o mesmo serviço "
       "aparece no total declarado, à parte.",
       "0 a 1", "maior", "CNES/DATASUS", dec=3, min=0, max=1,
       aliases=["icrp", "rede psicossocial", "raps", "caps", "saúde mental"]),

    _i("ICAS", "ICAS", "Cobertura Socioassistencial Especializada",
       "Cobertura — assistência social",
       "Fração dos municípios do estado com ao menos um CREAS. É o CREAS, e "
       "não o CRAS, que vira índice: o CRAS existe em quase todos os "
       "municípios do país, e uma fração que vale praticamente 1 em toda UF "
       "não ordena nada. NÃO mede psicólogos no SUAS — o cadastro publica "
       "total de profissionais sem abertura por ocupação.",
       "0 a 1", "maior", "CadSUAS/MDS", dec=3, min=0, max=1,
       aliases=["icas", "creas", "suas", "assistência social"]),

    # ------------------------------------------------------------ capacidade
    _i("vagas_total", "Vagas totais", "Capacidade total (presencial + EaD)",
       "Capacidade",
       "Todas as vagas anuais de Psicologia: presenciais mais EaD. Como a EaD "
       "responde por 0,2% do total, este número é, na prática, a capacidade "
       "presencial.",
       "vagas/ano", "contextual", "Censo INEP", dec=0,
       aliases=["vagas totais", "capacidade"]),

    _i("vagas_presencial", "Vagas presenciais", "Vagas em cursos presenciais",
       "Capacidade",
       "Vagas anuais em cursos presenciais em funcionamento. É onde está "
       "praticamente toda a formação em Psicologia no país.",
       "vagas/ano", "contextual", "Censo INEP", dec=0,
       aliases=["vagas presenciais"]),

    _i("vagas_capital", "Vagas na capital", "Vagas presenciais na capital",
       "Capacidade",
       "Vagas presenciais oferecidas na capital do estado. É metade do cálculo "
       "do ICT.",
       "vagas/ano", "contextual", "Censo INEP", dec=0),

    _i("vagas_por_100k", "Vagas / 100 mil hab.", "Densidade de vagas",
       "Capacidade",
       "Vagas totais por 100 mil habitantes. Normaliza a capacidade pela "
       "população e revela excesso ou escassez que o número absoluto esconde.",
       "vagas/100 mil", "contextual", "Censo INEP + IBGE", dec=1,
       aliases=["100 mil", "densidade"]),

    _i("populacao", "População", "População residente estimada", "Capacidade",
       "Estimativa populacional do IBGE para o estado, usada como base dos "
       "indicadores per capita.",
       "habitantes", "contextual", "IBGE", dec=0, aliases=["população"]),

    _i("n_cursos_presencial", "Cursos presenciais", "Cursos presenciais",
       "Capacidade", "Número de cursos presenciais em funcionamento.",
       "cursos", "contextual", "Censo INEP", dec=0),

    _i("n_ies", "IES", "Instituições de ensino superior", "Capacidade",
       "Instituições distintas que ofertam o curso no estado, somando "
       "presencial e EaD.",
       "instituições", "contextual", "Censo INEP", dec=0,
       aliases=["instituições"]),

    _i("n_mantenedoras", "Mantenedoras", "Mantenedoras distintas", "Capacidade",
       "Grupos mantenedores distintos. Uma mantenedora pode operar várias "
       "instituições.",
       "mantenedoras", "contextual", "Censo INEP", dec=0),

    # ------------------------------------------------------ ensino a distância
    # Recolhidos numa seção própria porque quase todos valem zero. Zero aqui é
    # MEDIDA — 25 das 27 UFs não têm nenhuma vaga a distância —, e a seção
    # existe para dizer isso de uma vez, em vez de espalhar vinte e cinco
    # zeros pelas tabelas principais como se fossem lacunas.
    _i("vagas_ead", "Vagas EaD", "Vagas a distância", "Ensino a distância",
       "Vagas anuais em cursos a distância, registradas na sede da "
       "mantenedora. São 549 no país inteiro, contra 276.250 presenciais. "
       "Zero num estado significa que ele foi medido e não tem nenhuma vaga "
       "EaD — é medida, não lacuna.",
       "vagas/ano", "contextual", "Censo INEP", dec=0, aliases=["vagas ead"]),

    _i("pct_ead", "% EaD", "Participação da EaD na capacidade",
       "Ensino a distância",
       "Percentual das vagas que são a distância. Em Psicologia é 0,2% no "
       "país. Para comparar: em Administração passa de 67%, e em "
       "Fonoaudiologia fica em 43%.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100,
       aliases=["% ead", "participação da ead"]),

    _i("n_cursos_ead", "Cursos EaD", "Cursos a distância (sede)",
       "Ensino a distância",
       "Número de cursos EaD com sede no estado.",
       "cursos", "contextual", "Censo INEP", dec=0),

    _i("ead_polos_registros", "Polos EaD", "Polos EaD (registros)",
       "Ensino a distância",
       "Registros de polo de apoio presencial de cursos EaD no estado. São 114 "
       "no país. Quatro estados — Acre, Amapá, Rondônia e Roraima — não têm "
       "nenhum.",
       "registros", "contextual", "Censo INEP", dec=0, aliases=["polos"]),

    _i("ead_polos_municipios", "Municípios com polo",
       "Municípios com polo EaD", "Ensino a distância",
       "Municípios distintos que abrigam ao menos um polo EaD: 105 no país.",
       "municípios", "contextual", "Censo INEP", dec=0),

    _i("municipios_so_ead", "Municípios só EaD",
       "Municípios atendidos apenas por EaD", "Ensino a distância",
       "Municípios que têm polo EaD e nenhum curso presencial. Mede até onde a "
       "EaD chega em território que a oferta presencial não alcança — que, "
       "neste curso, é quase lugar nenhum.",
       "municípios", "contextual", "Censo INEP", dec=0),

    _i("matriculas_ead", "Matrículas EaD", "Matrículas em polos EaD",
       "Ensino a distância",
       "Alunos matriculados registrados em polos EaD do estado. As linhas de "
       "polo carregam as matrículas; as vagas ficam na linha de sede.",
       "alunos", "contextual", "Censo INEP", dec=0),

    # --------------------------------------------------------- concentração
    _i("HHI", "HHI (IES)", "Concentração por instituição", "Concentração",
       "Índice Herfindahl-Hirschman das fatias de vagas por instituição. Perto "
       "de 1, quase toda a capacidade está numa instituição só.",
       "0 a 1", "menor", "Censo INEP", dec=4, min=0, max=1, aliases=["hhi"]),

    _i("HHI_mantenedora", "HHI (mantenedora)", "Concentração por mantenedora",
       "Concentração",
       "O mesmo índice, agrupando por grupo mantenedor em vez de instituição. "
       "Em Psicologia os dois valores ficam próximos, e isso é achado, não "
       "erro de conta: a distância entre eles mede o peso dos grandes grupos "
       "de EaD, e aqui a EaD é 0,2% da capacidade.",
       "0 a 1", "menor", "Censo INEP", dec=4, min=0, max=1,
       aliases=["hhi mantenedora", "concentração"]),

    _i("CR2", "CR2", "Participação das 2 maiores", "Concentração",
       "Fatia das vagas concentrada nas duas maiores instituições.",
       "0 a 100%", "menor", "Censo INEP", dec=1, min=0, max=1, mult=100,
       aliases=["cr2"]),

    _i("CR10", "CR10", "Participação das 10 maiores", "Concentração",
       "Fatia das vagas concentrada nas dez maiores instituições.",
       "0 a 100%", "menor", "Censo INEP", dec=1, min=0, max=1, mult=100,
       aliases=["cr10"]),

    # ------------------------------------------------------------ território
    _i("municipios_total", "Municípios do estado", "Municípios do estado",
       "Território",
       "Total de municípios do estado, conforme a base de localidades do IBGE. "
       "São 5.571 no país desde 2025, não 5.570.",
       "municípios", "contextual", "IBGE", dec=0),

    _i("municipios_oferta", "Municípios com curso",
       "Municípios com oferta presencial", "Território",
       "Municípios onde existe ao menos um curso presencial: 498 no país.",
       "municípios", "maior", "Censo INEP", dec=0,
       aliases=["municípios com oferta"]),

    _i("municipios_deserto", "Municípios sem curso",
       "Municípios sem oferta presencial", "Território",
       "Municípios do estado sem nenhum curso presencial de Psicologia.",
       "municípios", "menor", "Censo INEP", dec=0, aliases=["deserto"]),

    _i("cobertura_municipal", "Cobertura municipal",
       "Fração de municípios com curso", "Território",
       "Municípios com oferta presencial divididos pelo total de municípios do "
       "estado.",
       "0 a 1", "maior", "Censo INEP + IBGE", dec=4, min=0, max=1),

    # ------------------------------------------------------- cobertura: saúde
    _i("municipios_com_psicologo", "Municípios com psicólogo",
       "Municípios com psicólogo no SUS", "Cobertura — saúde",
       "Municípios com ao menos um profissional da família CBO 2515 vinculado "
       "ao SUS no CNES.",
       "municípios", "maior", "CNES/DATASUS", dec=0),

    _i("psicologos_sus", "Psicólogos no SUS", "Psicólogos vinculados ao SUS",
       "Cobertura — saúde",
       "Profissionais distintos, não vínculos: o mesmo psicólogo com três "
       "vínculos conta uma vez. Contar vínculos transformaria precariedade em "
       "abundância.",
       "profissionais", "maior", "CNES/DATASUS", dec=0),

    _i("psicologos_por_100k", "Psicólogos / 100 mil hab.",
       "Densidade de psicólogos no SUS", "Cobertura — saúde",
       "Psicólogos vinculados ao SUS por 100 mil habitantes. É a medida que "
       "separa os estados de verdade: quase todo município tem ao menos um "
       "psicólogo, mas ter um e ter trinta são situações diferentes, e só a "
       "densidade enxerga a diferença.",
       "profissionais/100 mil", "maior", "CNES/DATASUS + IBGE", dec=1),

    _i("municipios_com_raps", "Municípios com atenção psicossocial",
       "Municípios com atenção psicossocial no SUS", "Cobertura — saúde",
       "Municípios com estabelecimento que oferta ao SUS o serviço 115 no "
       "CNES, em qualquer das onze classificações.",
       "municípios", "maior", "CNES/DATASUS", dec=0, aliases=["raps"]),

    _i("municipios_com_raps_total", "Municípios — serviço declarado",
       "Municípios com atenção psicossocial declarada (SUS ou privado)",
       "Cobertura — saúde",
       "O mesmo serviço 115, sem o filtro de atendimento ao SUS: inclui o "
       "estabelecimento privado que o declara no cadastro. Publicado ao lado "
       "do indicador público porque a distância entre os dois diz quanto da "
       "rede psicossocial do município é acessível pelo SUS.",
       "municípios", "contextual", "CNES/DATASUS", dec=0),

    _i("estabelecimentos_raps", "Estabelecimentos psicossociais",
       "Estabelecimentos com atenção psicossocial no SUS", "Cobertura — saúde",
       "Estabelecimentos distintos que ofertam ao SUS o serviço 115. Um mesmo "
       "estabelecimento pode declarar várias classificações e é contado uma "
       "vez.",
       "estabelecimentos", "maior", "CNES/DATASUS", dec=0),

    _i("estabelecimentos_raps_total", "Estabelecimentos — declarado",
       "Estabelecimentos com atenção psicossocial declarada (SUS ou privado)",
       "Cobertura — saúde",
       "Os mesmos estabelecimentos, sem o filtro de atendimento ao SUS.",
       "estabelecimentos", "contextual", "CNES/DATASUS", dec=0),

    _i("municipios_com_raps_comunitaria", "Municípios — rede aberta",
       "Municípios com atenção psicossocial comunitária", "Cobertura — saúde",
       "Municípios com serviço aberto e de base territorial: atendimento "
       "psicossocial (115/002), desinstitucionalização de pessoas com "
       "transtorno mental em conflito com a lei (115/010) e promoção da saúde "
       "mental, protagonismo e cidadania (115/011).",
       "municípios", "maior", "CNES/DATASUS", dec=0,
       aliases=["caps", "rede aberta", "comunitária"]),

    _i("municipios_com_raps_residencial", "Municípios — moradia assistida",
       "Municípios com moradia assistida e acolhimento", "Cobertura — saúde",
       "Municípios com residência terapêutica (115/001, 115/004, 115/005) ou "
       "unidade de acolhimento adulto e infantojuvenil (115/006, 115/007). "
       "É a rede de moradia que substitui o manicômio.",
       "municípios", "maior", "CNES/DATASUS", dec=0,
       aliases=["residência terapêutica", "acolhimento"]),

    _i("municipios_com_raps_internacao", "Municípios — leito e regime fechado",
       "Municípios com leito ou regime fechado", "Cobertura — saúde",
       "Municípios com serviço hospitalar para atenção à saúde mental "
       "(115/003), regime residencial ou internação para transtornos mentais e "
       "dependência química (115/008, 115/009). Publicado separado da rede "
       "aberta de propósito: a política pública trata os dois como opostos, e "
       "somá-los mediria coisas contrárias com o mesmo sinal. O 115/008 "
       "chama-se “regime residencial” e entra aqui, não na moradia "
       "assistida: é o código das comunidades terapêuticas, enquanto a "
       "residência terapêutica e a unidade de acolhimento existem para desfazer "
       "a internação, não para prestá-la.",
       "municípios", "contextual", "CNES/DATASUS", dec=0,
       aliases=["internação", "leito", "regime fechado"]),

    # -------------------------------------------- cobertura: assistência social
    _i("municipios_com_cras", "Municípios com CRAS", "Municípios com CRAS",
       "Cobertura — assistência social",
       "Municípios com ao menos um Centro de Referência de Assistência Social. "
       "São 5.559 dos 5.571 do país: praticamente universal, o que é a razão "
       "de o CRAS não virar índice de cobertura.",
       "municípios", "maior", "CadSUAS/MDS", dec=0, aliases=["cras"]),

    _i("municipios_com_creas", "Municípios com CREAS", "Municípios com CREAS",
       "Cobertura — assistência social",
       "Municípios com ao menos um Centro de Referência Especializado de "
       "Assistência Social. São 2.758 no país — metade dos municípios —, e é "
       "daí que sai o ICAS.",
       "municípios", "maior", "CadSUAS/MDS", dec=0, aliases=["creas"]),

    _i("cras_total", "CRAS", "Unidades de CRAS", "Cobertura — assistência social",
       "Total de unidades de CRAS no estado.",
       "unidades", "maior", "CadSUAS/MDS", dec=0),

    _i("creas_total", "CREAS", "Unidades de CREAS",
       "Cobertura — assistência social",
       "Total de unidades de CREAS no estado.",
       "unidades", "maior", "CadSUAS/MDS", dec=0),

    _i("cras_por_100k", "CRAS / 100 mil hab.", "Densidade de CRAS",
       "Cobertura — assistência social",
       "Unidades de CRAS por 100 mil habitantes. É aqui que a variação entre "
       "estados aparece, já que a presença do equipamento é quase universal.",
       "unidades/100 mil", "maior", "CadSUAS/MDS + IBGE", dec=1),

    _i("creas_por_100k", "CREAS / 100 mil hab.", "Densidade de CREAS",
       "Cobertura — assistência social",
       "Unidades de CREAS por 100 mil habitantes.",
       "unidades/100 mil", "maior", "CadSUAS/MDS + IBGE", dec=1),

    # -------------------------------------------------------------- qualidade
    _i("CPC", "CPC (faixa)", "Conceito Preliminar de Curso — faixa",
       "Qualidade",
       "Média das faixas do CPC dos cursos do estado, ponderada pelo número de "
       "concluintes que participaram do ENADE. É deste valor que sai o "
       "componente de qualidade do IAF.",
       "1 a 5", "maior", "CPC INEP", dec=3, min=1, max=5, aliases=["cpc"]),

    _i("CPC_cont", "CPC contínuo", "Conceito Preliminar de Curso — contínuo",
       "Qualidade",
       "Média ponderada do CPC contínuo. Três casas decimais: com duas, "
       "nenhuma UF reproduz o valor publicado.",
       "0 a 5", "maior", "CPC INEP", dec=3, min=0, max=5),

    _i("ENADE_cont", "ENADE", "Conceito ENADE contínuo", "Qualidade",
       "Média ponderada do conceito ENADE contínuo dos cursos avaliados.",
       "0 a 5", "maior", "ENADE INEP", dec=3, min=0, max=5, aliases=["enade"]),

    _i("IDD", "IDD", "Indicador de Diferença entre Desempenhos", "Qualidade",
       "Mede quanto o curso agrega além do que a nota de ingresso do aluno já "
       "previa. No ciclo 2022 de Psicologia os 746 cursos avaliados têm IDD — "
       "cobertura total, ao contrário de cursos menores, onde a lacuna é comum.",
       "0 a 5", "maior", "CPC INEP", dec=3, min=0, max=5, aliases=["idd"]),

    _i("n_cursos_avaliados", "Cursos avaliados", "Cursos no ciclo do CPC",
       "Qualidade",
       "Cursos do estado avaliados no ciclo do CPC. Psicologia está no ciclo "
       "de 2022, não no de 2023 — aquele é o da saúde e das engenharias.",
       "cursos", "contextual", "CPC INEP", dec=0),

    _i("vagas_avaliadas", "Vagas avaliadas", "Vagas em cursos avaliados",
       "Qualidade",
       "Vagas dos cursos que passaram pelo ciclo do CPC. É o componente de "
       "cobertura da avaliação dentro do IAF.",
       "vagas/ano", "maior", "CPC INEP + Censo INEP", dec=0),

    _i("pct_doc_mestres", "% Mestres", "Docentes com mestrado ou mais",
       "Qualidade",
       "Percentual do corpo docente com titulação de mestre ou superior.",
       "0 a 100%", "maior", "CPC INEP", dec=1, min=0, max=100),

    _i("pct_doc_doutores", "% Doutores", "Docentes com doutorado", "Qualidade",
       "Percentual do corpo docente com doutorado.",
       "0 a 100%", "maior", "CPC INEP", dec=1, min=0, max=100),

    _i("pct_doc_regime_integral", "% Regime integral",
       "Docentes em regime integral ou parcial", "Qualidade",
       "Percentual do corpo docente em regime de trabalho integral ou parcial "
       "— não horista.",
       "0 a 100%", "maior", "CPC INEP", dec=1, min=0, max=100),

    _i("dim_didatico_pedagogica", "Org. didático-pedagógica",
       "Organização didático-pedagógica", "Qualidade",
       "Dimensão avaliada pelos próprios estudantes no questionário do ENADE.",
       "0 a 6", "maior", "CPC INEP", dec=3, min=0, max=6),

    _i("dim_infraestrutura", "Infraestrutura",
       "Infraestrutura e instalações físicas", "Qualidade",
       "Dimensão avaliada pelos próprios estudantes no questionário do ENADE.",
       "0 a 6", "maior", "CPC INEP", dec=3, min=0, max=6),

    _i("dim_oportunidade_formacao", "Oport. de ampliação",
       "Oportunidade de ampliação da formação", "Qualidade",
       "Dimensão avaliada pelos próprios estudantes no questionário do ENADE.",
       "0 a 6", "maior", "CPC INEP", dec=3, min=0, max=6),

    # ------------------------------------------------------------------ fluxo
    _i("matriculas", "Matrículas", "Matrículas totais", "Fluxo",
       "Alunos matriculados, somando presencial e polos EaD.",
       "alunos", "contextual", "Censo INEP", dec=0, aliases=["matrículas"]),

    _i("matriculas_presencial", "Matrículas presenciais",
       "Matrículas em cursos presenciais", "Fluxo",
       "Alunos matriculados em cursos presenciais.",
       "alunos", "contextual", "Censo INEP", dec=0),

    _i("ingressos", "Ingressos", "Ingressantes no ano", "Fluxo",
       "Alunos que ingressaram no curso no ano do Censo.",
       "alunos", "contextual", "Censo INEP", dec=0),

    _i("concluintes", "Concluintes", "Concluintes no ano", "Fluxo",
       "Alunos que concluíram o curso no ano do Censo.",
       "alunos", "contextual", "Censo INEP", dec=0),

    _i("taxa_conclusao", "Taxa de conclusão", "Concluintes sobre matrículas",
       "Fluxo",
       "Concluintes divididos por matriculados no mesmo ano. É um retrato "
       "pontual, não o acompanhamento de uma turma ao longo do tempo.",
       "0 a 100%", "maior", "Censo INEP", dec=1, min=0, max=25,
       aliases=["conclusão"]),

    # ----------------------------------------------------------------- perfil
    _i("pct_mulheres", "% Mulheres", "Mulheres entre os matriculados",
       "Perfil", "Percentual de mulheres entre os alunos matriculados.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100),

    _i("pct_ppi", "% Pretos, pardos e indígenas",
       "Pretos, pardos e indígenas entre os matriculados", "Perfil",
       "Percentual de alunos autodeclarados pretos, pardos ou indígenas. Leia "
       "junto com a cor não declarada: onde esta é alta, o percentual está "
       "subestimado.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100,
       aliases=["ppi"]),

    _i("pct_cor_nao_declarada", "% Cor não declarada",
       "Alunos sem declaração de cor ou raça", "Perfil",
       "Percentual de matriculados sem cor ou raça declarada. É a margem de "
       "incerteza do indicador de PPI, não um grupo à parte.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100),

    _i("pct_noturno", "% Noturno", "Matrículas em curso noturno", "Perfil",
       "Percentual de matriculados em cursos noturnos.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100),

    _i("pct_rede_publica", "% Rede pública", "Matrículas na rede pública",
       "Perfil", "Percentual de matriculados em instituições públicas.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100),

    _i("pct_financiamento", "% Com financiamento",
       "Matrículas com financiamento estudantil", "Perfil",
       "Percentual de matriculados com algum financiamento — FIES, ProUni ou "
       "outros, reembolsáveis ou não.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100,
       aliases=["fies", "prouni"]),

    _i("pct_apoio_social", "% Com apoio social", "Matrículas com apoio social",
       "Perfil",
       "Percentual de matriculados que recebem alguma modalidade de apoio "
       "social — moradia, alimentação, transporte, material.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100),

    _i("pct_reserva_vaga", "% Reserva de vagas",
       "Matrículas por reserva de vagas", "Perfil",
       "Percentual de matriculados que ingressaram por alguma política de "
       "reserva de vagas.",
       "0 a 100%", "contextual", "Censo INEP", dec=1, min=0, max=100,
       aliases=["cotas"]),

    # ------------------------------------------------- só no nível municipal
    # Existem apenas nas páginas de município. Precisam de entrada igual às
    # demais: a formatação vem do catálogo, e sem registro `polos_ead` cairia no
    # fallback de três casas — "2 polos" viraria "2,000".
    _i("cursos_presencial", "Cursos presenciais",
       "Cursos presenciais no município", "Capacidade",
       "Cursos presenciais de Psicologia no município.",
       "cursos", "contextual", "Censo INEP", dec=0),

    _i("polos_ead", "Polos EaD", "Polos de EaD no município",
       "Ensino a distância",
       "Polos de apoio presencial de cursos a distância registrados no "
       "município.",
       "registros", "contextual", "Censo INEP", dec=0),

    _i("raps_comunitaria", "Rede aberta",
       "Estabelecimentos de atenção psicossocial comunitária",
       "Cobertura — saúde",
       "Estabelecimentos do município com serviço psicossocial aberto e de "
       "base territorial (115/002, 115/010, 115/011).",
       "estabelecimentos", "maior", "CNES/DATASUS", dec=0),

    _i("raps_residencial", "Moradia assistida",
       "Estabelecimentos de moradia assistida e acolhimento",
       "Cobertura — saúde",
       "Estabelecimentos do município com residência terapêutica ou unidade de "
       "acolhimento (115/001, 115/004 a 115/007).",
       "estabelecimentos", "maior", "CNES/DATASUS", dec=0),

    _i("raps_internacao", "Leito e regime fechado",
       "Estabelecimentos de leito e regime fechado", "Cobertura — saúde",
       "Estabelecimentos do município com serviço hospitalar de saúde mental, "
       "regime residencial ou internação (115/003, 115/008, 115/009).",
       "estabelecimentos", "contextual", "CNES/DATASUS", dec=0),

    _i("cras", "CRAS", "Unidades de CRAS no município",
       "Cobertura — assistência social",
       "Centros de Referência de Assistência Social no município.",
       "unidades", "maior", "CadSUAS/MDS", dec=0),

    _i("creas", "CREAS", "Unidades de CREAS no município",
       "Cobertura — assistência social",
       "Centros de Referência Especializados de Assistência Social no "
       "município.",
       "unidades", "maior", "CadSUAS/MDS", dec=0),
]

POR_CHAVE = {i["key"]: i for i in INDICADORES}

CATEGORIAS = ["Território", "Capacidade", "Ensino a distância", "Concentração",
              "Cobertura — saúde", "Cobertura — assistência social",
              "Qualidade", "Fluxo", "Perfil"]

# A seção recolhida na página de UF e na home. Sai daqui, e não de uma lista de
# chaves no template, para que um indicador de EaD acrescentado depois entre na
# seção sozinho.
CATEGORIA_EAD = "Ensino a distância"


def da_categoria(categoria):
    return [i for i in INDICADORES if i["cat"] == categoria]


# --------------------------------------------------------------------------- #
# Campos publicados que NÃO são indicadores: identificam ou descrevem, não
# medem. Ficam declarados para que o teste de catálogo saiba distinguir "campo
# sem entrada no catálogo" de "campo que não precisa de entrada".
# --------------------------------------------------------------------------- #
CAMPOS_NAO_INDICADORES = {
    # identificação
    "uf", "regiao", "capital", "nome", "codigo", "slug",
    # sinalizadores de estado, lidos pelos templates para escolher o texto
    "tem_oferta_presencial", "tem_avaliacao", "tem_curso_presencial",
    # detalhamentos auxiliares, não exibidos como medida isolada
    "n_ies_presencial", "n_ies_ead", "n_com_cpc", "n_com_idd",
    "concluintes_participantes", "cursos_sem_vagas_no_censo",
    "servicos_raps", "psicologos_total",
}


def validar():
    """
    Confere a coerência interna do catálogo. Chamado pelo build e pelos testes.

    Devolve a lista de problemas; vazia significa catálogo íntegro.
    """
    problemas = []
    vistos = set()
    for ind in INDICADORES:
        key = ind["key"]
        if key in vistos:
            problemas.append(f"{key}: chave duplicada")
        vistos.add(key)
        if ind["dir"] not in DIRECOES:
            problemas.append(f"{key}: direção {ind['dir']!r} inválida")
        if ind["cat"] not in CATEGORIAS:
            problemas.append(f"{key}: categoria {ind['cat']!r} desconhecida")
        if not ind["oque"].strip():
            problemas.append(f"{key}: sem explicação")
        if (ind["min"] is None) != (ind["max"] is None):
            problemas.append(f"{key}: min e max precisam vir juntos ou nenhum")
        # Contagem com casa decimal é o defeito que este catálogo existe para
        # impedir: 19 municípios formatados com 3 casas viram "19,000".
        if ind["escala"] in CONTAGENS and ind["dec"] != 0:
            problemas.append(
                f"{key}: escala {ind['escala']!r} é contagem e exige dec=0, "
                f"tem dec={ind['dec']}")
    for categoria in CATEGORIAS:
        if not da_categoria(categoria):
            problemas.append(f"categoria {categoria!r} declarada e vazia")
    return problemas


def para_js():
    """Serializa o catálogo para o JS consumido pelo site."""
    import json

    meta = {i["key"]: {"label": i["sigla"], "nome": i["nome"], "dec": i["dec"],
                       "min": i["min"], "max": i["max"],
                       "mult": i["mult"], "dir": i["dir"], "cat": i["cat"]}
            for i in INDICADORES}
    glossario = [{"key": i["key"], "sigla": i["sigla"], "nome": i["nome"],
                  "cat": i["cat"], "oque": i["oque"], "escala": i["escala"],
                  "dir": i["dir"], "fonte": i["fonte"],
                  "aliases": i["aliases"]}
                 for i in INDICADORES]
    return (
        "/* GERADO por site/catalogo.py — não editar à mão.\n"
        "   Metadados de formatação e glossário saem da MESMA estrutura, então\n"
        "   é impossível um indicador existir num e faltar no outro. */\n"
        f"const INDICADOR_META = {json.dumps(meta, ensure_ascii=False, indent=2)};\n\n"
        f"const GLOSSARIO = {json.dumps(glossario, ensure_ascii=False, indent=2)};\n\n"
        f"const CATEGORIAS = {json.dumps(CATEGORIAS, ensure_ascii=False)};\n\n"
        f"const CATEGORIA_EAD = {json.dumps(CATEGORIA_EAD, ensure_ascii=False)};\n"
    )


if __name__ == "__main__":
    import sys

    problemas = validar()
    if problemas:
        print("[CATALOGO] FALHOU:")
        for p in problemas:
            print("  -", p)
        sys.exit(1)
    print(f"[CATALOGO] OK — {len(INDICADORES)} indicadores em "
          f"{len(CATEGORIAS)} categorias.")
    for c in CATEGORIAS:
        print(f"           {len(da_categoria(c)):3d}  {c}")
