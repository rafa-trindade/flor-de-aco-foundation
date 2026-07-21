![header](https://github.com/rafa-trindade/flor-de-aco/blob/main/docs/images/fem-banner.png?raw=true)

[![License: MIT](https://img.shields.io/badge/License-MIT-c8607a?labelColor=1a0d12)](LICENSE)
[![Kaggle](https://img.shields.io/badge/Dataset-Kaggle-e8a0b0?labelColor=7a2d45&logo=kaggle&logoColor=e8a0b0)](https://www.kaggle.com/datasets/rafatrindade/feminicidio-br)
[![GitHub Stars](https://img.shields.io/github/stars/rafa-trindade/flor-de-aco?style=flat&labelColor=1a0d12&color=7a2d45)](https://github.com/rafa-trindade/flor-de-aco-fundation)

## Sobre o Projeto

**Flor de Aço** nasceu da necessidade de transformar dados dispersos sobre violência de gênero em um recurso estruturado, comparável e pronto para análise - porque entender a escala do problema é o primeiro passo para enfrentá-lo.

Inicialmente idealizado por **[Gabrielle Urcioli](https://www.linkedin.com/in/gabrielle-urcioli/)** e **[Rafael Trindade](https://www.linkedin.com/in/rafatrindade/)**, o projeto reúne, padroniza e documenta microdados públicos de diferentes órgãos, oferecendo uma estrutura pronta para que pesquisadores, cientistas de dados, jornalistas e profissionais conduzam seus próprios estudos de forma organizada e reproduzível.

### Escopo

O projeto cobre a violência contra a mulher em diferentes momentos: da violência relatada em inquéritos domiciliares - que muitas vezes nunca chega a virar denúncia - até o desfecho fatal, passando pelos atendimentos em serviços de saúde e pela tramitação no Judiciário.

O feminicídio está contemplado, mas como desfecho de um percurso mais amplo. No recorte judicial mais abrangente do dataset, ele corresponde a cerca de 1% dos registros; os demais são as violências que o antecedem, e cuja documentação permite estudar a escalada e os pontos de intervenção.

| Momento da trajetória | Fonte |
|---|---|
| Violência autorreferida, com ou sem denúncia | DataSenado, PNS/IBGE |
| Atendimento em serviço de saúde | SINAN/DATASUS |
| Medida protetiva concedida | DataJud/CNJ |
| Descumprimento de medida protetiva | DataJud/CNJ |
| Violência de gênero tipificada (lesão, psicológica, perseguição) | DataJud/CNJ |
| Óbito por agressão | SIM/DATASUS |

O dataset consolidado está disponível no [Kaggle](https://www.kaggle.com/datasets/rafatrindade/feminicidio-br). O objetivo de longo prazo é consolidar os estudos produzidos em [github.com/rafa-trindade/flor-de-aco](https://github.com/rafa-trindade/flor-de-aco) em um painel público e interativo - um instrumento de monitoramento, conscientização e enfrentamento da violência contra mulheres no Brasil.

---

## 📊 Fontes de Dados

### **1. Violência Doméstica Autorreferida (Fonte: Pesquisa DataSenado)**

A **Pesquisa Violência Doméstica e Familiar contra a Mulher**, conduzida pelo **Instituto de Pesquisa DataSenado** (Senado Federal), é um levantamento nacional por telefone realizado em rodadas bienais desde 2005, com o objetivo de dimensionar a violência doméstica sob a ótica das próprias entrevistadas.

**Escopo e Processamento:** Foram consolidadas as **10 rodadas disponíveis (2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021 e 2023)**. Cada rodada tem seu próprio questionário e seu próprio dicionário de dados oficial (a pergunta e as opções de resposta variam de uma edição para outra), então o processamento é feito ano a ano: o script varre a pasta de microdados brutos e a pasta de dicionários, casa cada CSV com o dicionário da mesma rodada e usa esse dicionário para (a) trocar o código de cada variável pela descrição da pergunta e (b) trocar o código de cada resposta pela descrição da categoria correspondente. Isso preserva a possibilidade de comparar/agregar as rodadas mesmo quando o instrumento de coleta muda de ano para ano.

**Bases disponibilizadas** (pasta `datasen/`):

- `datasen/pn_violencia_domestica_{ano}.parquet` - Uma base por rodada (2005–2023), com colunas nomeadas pela descrição da pergunta e respostas decodificadas pela descrição da categoria (ex.: a coluna `P08` vira `em_que_estado_voce_mora`, e o valor `11` vira `Rondônia`).

> INSTITUTO DE PESQUISA DATASENADO. *Microdados da Pesquisa Violência Doméstica e Familiar*, 2005 – 2023. Brasília, DF. 2007. Disponível em: <https://www.senado.leg.br/institucional/datasenado/paineis_dados/#/?pesquisa=violencia_domestica_familiar>.

---

### **2. Óbitos por Agressão (Fonte: SIM - DATASUS)**

O **Sistema de Informações sobre Mortalidade (SIM)**, gerenciado pelo **DATASUS/Ministério da Saúde**, consolida as Declarações de Óbito de todo o país e é a base oficial para estatísticas de mortalidade no Brasil.

**Escopo e Processamento:** São baixados via FTP público do DATASUS os arquivos de Declaração de Óbito por Causas Externas (`.dbc`), convertidos para Parquet em lotes e, em seguida, filtrados e consolidados via DuckDB. São mantidos apenas os registros **femininos** (`SEXO = 2`) classificados nos códigos da **CID-10 que indicam agressão (X85–Y09)** - recorte que permite analisar mortes violentas com potencial relação a dinâmicas de violência de gênero. O código **Y35 (intervenção legal) fica de fora**: a própria CID-10 o lista como exclusão do grupo X85–Y09, e morte por ação policial é outro fenômeno. Os campos de código (sexo, raça/cor, estado civil, local de ocorrência, tipo do óbito, gestação/puerpério e a causa básica) são decodificados para texto legível durante o processamento.

**Base disponibilizada** (pasta `datasus_sim/`):

- `datasus_sim/proxy_sim_feminicidio.parquet` - Série consolidada de óbitos femininos por causas externas com potencial enquadramento como feminicídio, com os campos-código traduzidos (sexo, raça/cor, estado civil, causa básica descrita, tipo de óbito, gestação/puerpério, local de ocorrência, datas e municípios de residência/óbito).

O prefixo "proxy" no nome do arquivo indica que se trata de uma aproximação: a Declaração de Óbito não possui campo de feminicídio nem de relação entre vítima e agressor. O recorte por CID-10 abrange óbitos de mulheres por agressão, o que inclui casos que não configuram feminicídio e exclui feminicídios classificados sob outra causa básica.

O 4º dígito do código CID-10 no grupo X85–Y09 indica o **local de ocorrência** - ou, nos grupos Y06 e Y07, o **agressor** - e não o método de agressão. As colunas `METODO_AGRESSAO`, `LOCAL_CID` e `AGRESSOR_CID` decompõem essa informação. Sem essa distinção, o código `X850` (agressão por drogas em residência) poderia ser lido como morte por arma de fogo.

---

### **3. Violência Declarada (Fonte: Pesquisa Nacional de Saúde - IBGE)**

A **Pesquisa Nacional de Saúde (PNS)** é um inquérito domiciliar do **IBGE**, realizado em parceria com o Ministério da Saúde, que coleta informações sobre saúde, condições de vida e experiências de violência da população brasileira.

**Escopo e Processamento:** Foram utilizados os microdados de posição fixa (arquivo `.txt`) das duas edições disponíveis (**2013 e 2019**). Cada campo é extraído por posição de coluna (conforme o dicionário oficial de cada edição, que muda de layout de um ano para o outro) e decodificado para texto. Em seguida, a base é filtrada para manter apenas **mulheres que relataram ter sofrido violência** (física, psicológica ou sexual) nos 12 meses anteriores à entrevista. A base captura a violência sob a perspectiva da vítima - tipo de agressão, autor, local, frequência e busca por atendimento -, informações muitas vezes ausentes em registros policiais e de saúde.

**Bases disponibilizadas** (pasta `ibge/`):

- `ibge/pns_violencia_domestica_2013.parquet` - PNS 2013, violência por pessoa **conhecida** (cônjuge, parente, vizinho) - bloco O037 do questionário.
- `ibge/pns_proxy_violencia_desconhecido_2013.parquet` - PNS 2013, violência por pessoa **desconhecida** (assaltante, policial, agressor eventual) - bloco O025. Publicada separadamente porque é outro fenômeno: somá-la à anterior produziria um número de "violência doméstica" que inclui assalto na rua.
- `ibge/pns_violencia_domestica_2019.parquet` - PNS 2019. O layout de 2019 é mais detalhado que o de 2013, com violência psicológica, física e sexual em blocos de perguntas separados.

*Observação: os microdados de posição fixa do IBGE são volumosos e sujeitos aos termos de download do instituto, então são obtidos manualmente - diferente do fluxo do SIM e do SINAN, sincronizados por FTP.*

*Atenção ao comparar as duas edições: o domínio de sexo muda entre elas. 2013 usa "Masculino"/"Feminino"; 2019 usa "Homem"/"Mulher". Um filtro herdado de uma edição para a outra produz base vazia sem erro.*

---

### **4. Notificações de Violência Interpessoal (Fonte: SINAN - DATASUS)**

O **Sistema de Informação de Agravos de Notificação (SINAN)** recebe as notificações compulsórias de violência interpessoal e autoprovocada feitas por serviços de saúde de todo o país (ficha VIOL).

Diferentemente do SIM, que cobre apenas óbitos, a ficha VIOL registra violência não fatal e inclui a relação entre vítima e agressor - campo ausente na Declaração de Óbito. É a fonte que permite distinguir violência por parceiro íntimo de violência intrafamiliar.

**Escopo e Processamento:** os arquivos `VIOLBR{AA}.dbc` são baixados do FTP público do DATASUS (bases finais e preliminares), convertidos para Parquet e consolidados via DuckDB. O recorte mantém **vítimas do sexo feminino** (`CS_SEXO = 'F'`), excluindo lesão autoprovocada (`LES_AUTOP = 1`) e registros marcados como duplicidade pelo próprio SINAN. Não há filtro de idade: notificações envolvendo meninas representam parcela expressiva da base, com pico da série aos 13 anos.

Os domínios seguem o *Dicionário de Dados SINAN NET 5.0/Patch 5.1*. Duas divergências entre o dicionário publicado e o layout real do DBF são tratadas no processamento: a numeração das categorias de escolaridade e os campos declarados com um dígito que na prática usam dois.

**Base disponibilizada** (pasta `datasus_sinan/`):

- `datasus_sinan/sinan_violencia_mulher.parquet` - Notificações de violência contra mulheres, com perfil da vítima, tipo de violência, meio de agressão, vínculo com o agressor e encaminhamentos da rede.

**Colunas de leitura menos óbvia:**

- `VINCULOS_AGRESSOR` - lista de vínculos, não valor único. O campo 61 da ficha admite múltiplas marcações: uma mesma notificação pode registrar cônjuge e pai simultaneamente. A ficha não define vínculo principal.
- `AGRESSOR_PARCEIRO_INTIMO` e `AGRESSOR_FAMILIAR` - indicadores derivados do vínculo, para os recortes mais frequentes.
- `INDICIO_VIOLENCIA_GENERO` - assume `SIM`, `NAO` ou nulo. Como o recorte de entrada é apenas o sexo da vítima, a base reúne violência de gênero e violência infantil geral, que atinge meninos e meninas de forma semelhante. O valor `NAO` indica que os campos relevantes estavam preenchidos e nenhum critério de gênero foi atendido; o nulo indica que não há informação suficiente para classificar.

> BRASIL. Ministério da Saúde. DATASUS. *Sistema de Informação de Agravos de Notificação (SINAN) - Violência Interpessoal/Autoprovocada*. Disponível em: <https://datasus.saude.gov.br/>.

---

### **5. Processos Judiciais (Fonte: DataJud - CNJ)**

A **Base Nacional de Dados do Poder Judiciário (DataJud)**, instituída pela Resolução CNJ nº 331/2020, reúne os metadados processuais de todos os tribunais do país e é consultada pela API pública do CNJ.

A base mede a judicialização da violência: quantos casos chegam ao Judiciário, em que fase estão, e quantas medidas protetivas são concedidas e descumpridas. É o único ponto da cadeia em que a proteção judicial aparece.

A API expõe apenas metadados processuais - classe, assunto, órgão julgador e datas. Não há informação sobre vítima ou agressor (idade, raça, vínculo); para perfil, as fontes são o SINAN e o SIM.

**Escopo e Processamento:** extração pela API pública do DataJud nos 27 tribunais de justiça estaduais, filtrando por códigos de assunto da Tabela Processual Unificada (TPU). Os códigos foram verificados por consulta direta à API em vez de transcritos da tabela publicada, o que permitiu identificar duplicatas de grafia (o mesmo assunto com dois códigos) e nós hierárquicos que raramente são marcados na capa do processo.

São publicados três recortes, do mais estrito ao mais amplo:

| Recorte | Assuntos | Volume |
|---|---|---|
| `feminicidio` | Feminicídio (12091) | ~45 mil movimentações |
| `violencia_genero` | + lesão por condição de mulher, violência psicológica, perseguição, descumprimento de protetiva | ~480 mil |
| `contexto_domestico` | + marcadores transversais de violência doméstica | ~3 milhões |

**Bases disponibilizadas** (pasta `datajud/`):

- `datajud/datajud_feminicidio.parquet`
- `datajud/datajud_violencia_genero.parquet`
- `datajud/datajud_contexto_domestico.parquet`

**Colunas de leitura menos óbvia:**

- `DESFECHO` - assume `TENTATIVA`, `CONSUMADO` ou nulo. `TENTATIVA` decorre de marcador explícito no processo; `CONSUMADO` apenas de indício positivo, como a presença de assunto que pressupõe a morte (ocultação de cadáver). A ausência do marcador de tentativa não permite concluir pela consumação, já que o tribunal pode não tê-lo registrado - por isso a maioria dos casos fica nula, e a contagem de `CONSUMADO` representa um piso, não o total.
- `EH_MEDIDA_PROTETIVA` e `TEM_DESCUMPRIMENTO_PROTETIVA` - a primeira deriva da classe processual, indicando que o processo é o próprio pedido de proteção; a segunda deriva do assunto, indicando violação de medida já concedida. São fenômenos distintos e não coincidentes: existem protetivas sem marcador de descumprimento e ações penais por descumprimento que não pertencem à classe de protetiva.
- `ASSUNTOS` - ordenados por relevância de leitura (forma, tipo penal, qualificadora de gênero, contexto) em vez de alfabeticamente, de modo que a sequência "Crime Tentado, Homicídio Qualificado, Feminicídio" identifique a tentativa na primeira posição.
- `ASSUNTOS_IMPLAUSIVEL` - sinaliza registros cujo campo de assuntos contém a tabela de domínio inteira, com centenas de códigos. São poucos casos, mantidos na base e apenas marcados.

> CONSELHO NACIONAL DE JUSTIÇA. *Base Nacional de Dados do Poder Judiciário - DataJud*. API Pública. Disponível em: <https://datajud-wiki.cnj.jus.br/api-publica/acesso>.

---

### **6. Bases de Dados Auxiliares**

Para permitir análises mais ricas e cruzamentos de informações, o projeto conta com uma base auxiliar de referência geográfica, construída a partir de **dados abertos do Ministério da Saúde**.

**Escopo e Processamento:** o arquivo de municípios (`macroregiao_de_saude.zip`, Dados Abertos da Saúde) é combinado, via join no código do município (`cod_municipio`/`MUNCOD`, com zero à esquerda padronizado), com um arquivo complementar de geolocalização dos municípios.

**Base disponibilizada** (pasta `macroregiao/`):

- `macroregiao/geo_macroregiao.parquet` - Lista oficial de municípios brasileiros associada às suas respectivas macrorregiões de saúde, regiões de saúde e coordenadas geográficas. Permite análise territorial, integração com as demais bases do projeto e agregação espacial.

---

### **7. Fontes Avaliadas e Não Incorporadas**

Duas fontes foram avaliadas e não integram esta versão do dataset:

- **Ligue 180 (MDHC)** - os microdados semestrais de denúncias (2014 a 2024) constituiriam a única fonte de denúncia espontânea do projeto, sem intermediação de serviços de saúde ou polícia. A página de dados abertos do ministério passou a exigir autenticação e encontra-se indisponível. A fonte permanece no roadmap.
- **SINESP (MJSP)** - o portal de dados abertos apresentava indisponibilidade e o indicador de feminicídio não constava da base pública. Dados de segurança pública com esse recorte são publicados pelo Fórum Brasileiro de Segurança Pública, em formato agregado.

---

## 🗓️ Cobertura Histórica

O repositório combina diferentes janelas temporais, de acordo com a fonte:

- **DataSenado (violência autorreferida):** 2005 a 2023, em rodadas bienais.
- **SIM/DATASUS (óbitos por agressão):** série consolidada desde 1996, com atualização contínua conforme novos dados são fechados pelo Ministério da Saúde.
- **SINAN/DATASUS (notificações de violência):** desde 2009, com bases finais e preliminares.
- **DataJud/CNJ (processos judiciais):** embora o Datajud tenha sido instituído em 2020, os tribunais migraram acervo anterior, com processos ajuizados desde os anos 1990 e volume expressivo a partir de 2015.
- **PNS/IBGE (violência declarada):** edições pontuais de 2013 e 2019 (periodicidade do próprio inquérito do IBGE).

Essa amplitude temporal possibilita identificação de tendências de longo prazo, avaliação do impacto de políticas públicas e compreensão da evolução da violência de gênero ao longo de diferentes governos, ciclos econômicos e contextos sociais.

---

## 🔄 Atualização e Confiabilidade

Nem todas as fontes têm a mesma dinâmica de atualização:

- **SIM e SINAN/DATASUS:** sincronização automatizada via FTP público do DATASUS, com reprocessamento conforme novos arquivos são publicados. As bases preliminares são revisadas pelo Ministério da Saúde e podem mudar entre competências.
- **DataJud/CNJ:** extração pela API pública, com checkpoint que permite retomar coletas interrompidas. A carga completa leva horas, dado o tempo de resposta da API e o volume envolvido; as atualizações posteriores operam em modo incremental. Cada extração é conferida contra a contagem informada pela própria API por tribunal, e divergências impedem que o tribunal seja marcado como concluído.
- **DataSenado e PNS/IBGE:** bases estáticas - cada rodada/edição é um retrato fechado no tempo, incorporada ao repositório quando o instituto responsável publica os microdados oficiais. Não há "atualização" desses dados entre uma rodada e outra, apenas a incorporação de rodadas novas quando lançadas.
- **Macrorregiões (auxiliar):** atualizada quando o Ministério da Saúde publica revisão da malha de municípios/macrorregiões.

Em todos os casos, a padronização de nomes de coluna, tratamento de categorias e estrutura de pastas é mantida consistente entre atualizações.

---

## ⚠️ Limitações Conhecidas

Cada fonte registra um momento distinto da trajetória, com critérios e coberturas próprios. Os totais não são comparáveis entre bases: um mesmo caso pode constar em várias delas, em apenas uma ou em nenhuma.

| Fonte | O que registra | Momento da cadeia |
|---|---|---|
| SIM | Óbito por agressão | Desfecho fatal |
| SINAN | Notificação em serviço de saúde | Violência não fatal atendida |
| DataJud | Processo judicial | Judicialização |
| PNS / DataSenado | Violência autorreferida em inquérito | O que a vítima relata, tenha ou não denunciado |

### Comparação entre tribunais no DataJud

O volume de processos por tribunal reflete a completude do envio ao CNJ e a prática de classificação de cada corte, não a incidência de violência no estado. São Paulo ilustra bem a diferença: segundo o Fórum Brasileiro de Segurança Pública, o estado lidera em feminicídios registrados pela polícia, mas ocupa a quarta posição no DataJud, atrás de unidades com população significativamente menor.

Comparações entre unidades da federação exigem normalização por fonte externa. Séries temporais dentro de um mesmo tribunal são consistentes.

### Valores nulos em colunas classificatórias

Algumas colunas admitem três estados (`SIM`, `NAO` e nulo) em vez de um booleano. O nulo indica ausência de informação suficiente para classificar, e não resposta negativa. Aplica-se a `DESFECHO`, no DataJud, e a `INDICIO_VIOLENCIA_GENERO`, no SINAN.

### Tentativa e consumação

No Código Penal, a tentativa não constitui crime autônomo: é o mesmo tipo penal com a redução prevista no art. 14, II. A combinação "Crime Tentado, Homicídio Qualificado, Feminicídio" descreve, portanto, uma tentativa - o "Homicídio Qualificado" identifica o artigo imputado, sem afirmar a ocorrência da morte.

| Combinação de assuntos | Desfecho |
|---|---|
| Feminicídio, Homicídio Qualificado | consumado |
| Crime Tentado, Feminicídio, Homicídio Qualificado | tentativa |
| Feminicídio, Homicídio Qualificado, Violência Doméstica | consumado |
| Crime Tentado, Feminicídio, Homicídio Qualificado, Violência Doméstica | tentativa |

A base também registra combinações de "Feminicídio" com "Homicídio Simples", tecnicamente inconsistentes, já que o feminicídio é qualificadora e implicaria homicídio qualificado. Correspondem provavelmente a classificações iniciais não atualizadas no curso do processo.

### Granularidade do DataJud

As tabelas do DataJud têm uma linha por movimentação processual, identificada em `ID_DATAJUD`, e não por processo. Um mesmo `NUMERO_PROCESSO` aparece em múltiplas linhas quando tramita em classes ou órgãos julgadores distintos - por exemplo, uma apelação e um agravo em gabinetes diferentes. Para contagem de processos, utilize `COUNT(DISTINCT NUMERO_PROCESSO)`.

### Município ausente

Cerca de 11% dos registros do DataJud não informam `COD_MUNICIPIO_IBGE`, com a ausência concentrada em alguns tribunais. A coluna `UF`, derivada da sigla do tribunal, viabiliza o recorte estadual nesses casos.

---

## 📁 Estrutura do Dataset

Todas as bases são publicadas em **Parquet**, uma pasta por fonte:

```
datasen/
  pn_violencia_domestica_{ano}.parquet      -> uma base por rodada (2005-2023)

datasus_sim/
  proxy_sim_feminicidio.parquet             -> óbitos femininos por agressão (CID-10 X85-Y09)

datasus_sinan/
  sinan_violencia_mulher.parquet            -> notificações de violência não fatal

datajud/
  datajud_feminicidio.parquet               -> recorte estrito: assunto Feminicídio
  datajud_violencia_genero.parquet          -> + lesão, psicológica, perseguição, protetiva
  datajud_contexto_domestico.parquet        -> + marcadores transversais de violência doméstica

ibge/
  pns_violencia_domestica_2013.parquet      -> violência por pessoa conhecida (bloco O037)
  pns_proxy_violencia_desconhecido_2013.parquet  -> por pessoa desconhecida (bloco O025)
  pns_violencia_domestica_2019.parquet      -> edição 2019

macroregiao/
  geo_macroregiao.parquet                   -> municípios, macrorregiões de saúde e coordenadas
```

O formato Parquet foi adotado pelo volume das bases, que chegam a milhões de linhas: a compressão colunar reduz substancialmente o tamanho dos arquivos e permite consulta direta por DuckDB, Dremio, pandas ou Spark, sem carregar o conjunto inteiro em memória.

O repositório publica apenas as bases processadas. Os microdados originais - arquivos `.dbc` do DATASUS, `.txt` de posição fixa do IBGE, `.csv` do DataSenado e as respostas em JSON da API do DataJud - são obtidos das fontes oficiais pelos scripts de extração e não são redistribuídos, já que cada instituição mantém seus próprios canais de download e termos de uso.

---

## 📄 Licença e Créditos

Este dataset consolidado é disponibilizado sob licença **CC0 1.0** (domínio público). Isso se refere ao trabalho de curadoria, padronização e harmonização realizado neste repositório - os dados originais permanecem de titularidade e responsabilidade das instituições abaixo, que devem ser citadas ao utilizar cada fonte individualmente:

- **DataSenado (Pesquisa Violência Doméstica e Familiar):**
  > INSTITUTO DE PESQUISA DATASENADO. *Microdados da Pesquisa Violência Doméstica e Familiar*, 2005 – 2023. Brasília, DF. 2007. Disponível em: <https://www.senado.leg.br/institucional/datasenado/paineis_dados/#/?pesquisa=violencia_domestica_familiar>. 

- **SIM/DATASUS (óbitos por causas externas):**
  > BRASIL. Ministério da Saúde. DATASUS. *Sistema de Informações sobre Mortalidade (SIM)*. Brasília, DF: Ministério da Saúde. Disponível em: <https://datasus.saude.gov.br/mortalidade-desde-1996-pela-cid-10>. 

- **SINAN/DATASUS (notificações de violência interpessoal):**
  > BRASIL. Ministério da Saúde. DATASUS. *Sistema de Informação de Agravos de Notificação (SINAN)*. Brasília, DF: Ministério da Saúde. Disponível em: <https://datasus.saude.gov.br/>.

- **DataJud/CNJ (metadados processuais):**
  > CONSELHO NACIONAL DE JUSTIÇA. *Base Nacional de Dados do Poder Judiciário - DataJud*. Brasília, DF: CNJ. Disponível em: <https://datajud-wiki.cnj.jus.br/api-publica/acesso>.

- **IBGE (Pesquisa Nacional de Saúde):**
  > INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA (IBGE). *Pesquisa Nacional de Saúde (PNS)*. Rio de Janeiro: IBGE. Disponível em: <https://www.ibge.gov.br/estatisticas/sociais/saude/9160-pesquisa-nacional-de-saude.html>. 

- **Ministério da Saúde (base auxiliar de macrorregiões):**
  > BRASIL. Ministério da Saúde. *Dados Abertos - Macrorregião de Saúde*. Disponível em: <https://dados.gov.br>. 

Se você utilizar este dataset em pesquisas, reportagens ou análises, considere citar tanto a fonte original relevante (acima) quanto este repositório de curadoria.

---

#### **Idealização e iniciativa:** 
- [Gabrielle Urcioli](https://www.linkedin.com/in/gabrielle-urcioli)

- [Rafael Trindade](https://www.linkedin.com/in/rafatrindade/)

##### **Apoio:** [PoD Academy](https://www.linkedin.com/school/academy-pod/)