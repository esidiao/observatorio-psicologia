# Política de segurança e integridade dos dados

Este repositório não processa dados pessoais, não expõe serviço em execução e
não recebe entrada de usuário. A superfície de risco aqui é diferente da de uma
aplicação: o que pode dar errado é **um número errado ser publicado como se
fosse certo**.

Neste projeto o deploy é **automático** — todo push na `main` que passe pelos
portões vai ao ar. Isso desloca o peso inteiro da integridade para os portões,
e é por isso que eles são muitos. Um branch com pull request roda a mesma
validação e não publica nada; é o caminho para experimentar.

## Reportar um problema

| Tipo | Como reportar |
|---|---|
| Divergência entre um número do site e a fonte primária | Abra uma issue com o indicador, a UF ou o município, o valor publicado e o valor da fonte |
| Vulnerabilidade no código do pipeline ou do gerador | Abra uma issue; se envolver credencial, escreva antes para sidiao@i9educar.com |
| Erro de interpretação ou de método | Abra uma issue descrevendo o raciocínio; método é discutível em público |
| Discordância do recorte da rede psicossocial | Abra uma issue. Agrupar as onze classificações do serviço 115 em três subgrupos é decisão editorial deste projeto, não classificação oficial — e decisão editorial se discute |

Divergência de dado tem prioridade sobre qualquer outra coisa neste projeto.

## Como a integridade é protegida

- **Portão GO.** As fórmulas dos índices e da estatística são conferidas contra
  valores calculados à mão antes de qualquer publicação.
- **Âncoras de regressão.** Os totais conhecidos do Censo, do CPC, do CNES e do
  CadSUAS são testados a cada execução; mudança inesperada reprova o build.
- **Zero e ausência são testados nas duas direções.** Um teste garante que
  ausência nunca vire `0`; outro garante que o zero medido — as 25 UFs sem
  nenhuma vaga a distância — nunca vire "sem dados". Neste curso, apagar
  qualquer uma das duas apagaria o achado central.
- **Catálogo fechado.** Todo indicador publicado tem entrada de glossário e
  regra de formatação, geradas da mesma estrutura.
- **Guarda de junção.** No CNES, a fração de registros cujo estabelecimento não
  existe no cadastro é vigiada e aborta acima de 2%. Estabelecimento
  *desabilitado* é contado à parte: é exclusão deliberada, e somá-lo à falha
  reprovaria execuções corretas.
- **Guarda de riqueza.** O conjunto novo é comparado com o publicado; perda de
  campos aborta a publicação.
- **Proveniência.** Cada número carrega fonte, ano e data de extração, e o ano
  vem do arquivo lido, nunca do calendário.
- **Registro de anterioridade.** `data/registro_autoral.json` guarda o resumo
  SHA-256 de cada arquivo autoral.

## Dependências

O projeto usa `jinja2`, `openpyxl`, `pandas` e `requests`, e traz versionadas as
bibliotecas de front-end (Leaflet, Chart.js) e as fontes. Nenhum recurso é
carregado de CDN em tempo de execução: o site funciona offline e não expõe o
leitor a terceiros.

O acesso às fontes oficiais usa o **truststore do sistema** para validar TLS —
necessário porque o servidor do INEP não envia o certificado intermediário e a
cadeia só fecha por AIA. A verificação **nunca** é desligada: um observatório
que se apoia em proveniência não pode baixar dado oficial por canal não
autenticado.

## O que este projeto não faz

Não coleta métricas de uso, não usa cookies, não carrega rastreadores e não
envia dado nenhum do leitor para lugar algum. O único armazenamento no
navegador é o cache do service worker, com os próprios arquivos do site.
