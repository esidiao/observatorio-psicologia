# Direitos autorais

© 2026 **Edson Sidião de Souza Júnior** — sidiao@i9educar.com
[Currículo Lattes](http://lattes.cnpq.br/9464330669014306)

Todos os direitos reservados sobre a obra autoral, nos termos da
**Lei 9.610/1998** (direitos autorais) e da **Lei 9.609/1998** (programa de
computador).

## O que é obra do autor

- A formulação dos índices **ICT**, **E**, **IAF**, **ICAP**, **ICRP** e
  **ICAS**, suas definições e a escolha dos componentes.
- O recorte da rede psicossocial em três subgrupos — comunitário, moradia
  assistida e leito/regime fechado — a partir das onze classificações do
  serviço 115 do CNES. O agrupamento é uma decisão editorial deste projeto, não
  uma classificação oficial do Ministério da Saúde.
- O catálogo de indicadores (`site/catalogo.py`) e os verbetes do glossário.
- O código do pipeline (`etl/`), do gerador do site (`site/`) e dos testes.
- Os textos, o desenho editorial, a paleta e a organização das páginas.

Esse conjunto não pode ser copiado, adaptado ou redistribuído sem autorização,
ressalvadas as exceções legais — entre elas a citação com identificação da
fonte.

## O que não é

Os **dados primários** são públicos e pertencem às instituições que os
produzem:

| Dado | Instituição |
|---|---|
| Censo da Educação Superior | INEP |
| Conceito Preliminar de Curso | INEP |
| Cadastro Nacional de Estabelecimentos de Saúde | Ministério da Saúde |
| CadSUAS (unidades de CRAS e CREAS) | Ministério do Desenvolvimento Social |
| Malhas territoriais e estimativas populacionais | IBGE |

Reivindicá-los seria o oposto do que este projeto defende.

Os **indicadores calculados** e as tabelas derivadas — publicados em
`data/nacional.json` e `dados/indicadores.csv` — são liberados para reúso,
inclusive comercial, desde que citados a fonte primária e este observatório.

## Como citar

> SOUZA JÚNIOR, Edson Sidião de. *Observatório Nacional da Formação em
> Psicologia*: indicadores de acesso territorial, qualidade e cobertura
> assistencial. 2026. Disponível em:
> https://esidiao.github.io/observatorio-psicologia/. Acesso em: [data].

Ao citar um indicador de cobertura, vale nomear qual: **ICAP** (força de
trabalho no SUS), **ICRP** (rede psicossocial) e **ICAS** (CREAS) medem coisas
diferentes e não são intercambiáveis. Citar "a cobertura assistencial" sem
qualificar deixa o leitor sem saber qual das três políticas está em jogo.

## Bibliotecas de terceiros

O site embarca **Leaflet** e **Chart.js**, sob suas próprias licenças, e as
fontes **Inter** e **Lora** sob a SIL Open Font License. Nada disso é obra do
autor nem está coberto pela reserva de direitos acima.

## Registro de anterioridade

`data/registro_autoral.json` guarda o resumo SHA-256 de cada arquivo autoral, a
data do registro e o commit que ancora essa data no histórico do repositório.

O resumo é calculado sobre o **conteúdo**, com fim de linha normalizado — não
sobre os bytes como cada sistema operacional os grava. É isso que permite a
outra pessoa, em outra máquina, chegar ao mesmo número. Para conferir:

```bash
python etl/registro_autoral.py --verificar
```

**O que ele é:** declaração datada de conteúdo, verificável por terceiros.
**O que não é:** registro em cartório ou depósito no INPI — e não substitui
nenhum dos dois.
