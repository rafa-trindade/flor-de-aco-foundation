![header](https://github.com/rafa-trindade/flor-de-aco/blob/main/docs/images/fem-banner.png?raw=true)

[![License: MIT](https://img.shields.io/badge/License-MIT-c8607a?labelColor=1a0d12)](LICENSE)
[![Kaggle](https://img.shields.io/badge/Dataset-Kaggle-e8a0b0?labelColor=7a2d45&logo=kaggle&logoColor=e8a0b0)](https://www.kaggle.com/datasets/rafatrindade/feminicidio-br)
[![GitHub Stars](https://img.shields.io/github/stars/rafa-trindade/flor-de-aco?style=flat&labelColor=1a0d12&color=7a2d45)](https://github.com/rafa-trindade/flor-de-aco-fundation)

## Sobre o Projeto

**Flor de Aço** nasceu da necessidade de transformar dados dispersos sobre violência de gênero em um recurso estruturado, comparável e pronto para análise - porque entender a escala do problema é o primeiro passo para enfrentá-lo.

Inicialmente idealizado por **[Gabrielle Urcioli](https://www.linkedin.com/in/gabrielle-urcioli/)** e **[Rafael Trindade](https://www.linkedin.com/in/rafatrindade/)**, o projeto reúne uma série histórica de dados sobre feminicídio - cuidadosamente curados, padronizados e documentados - e oferece uma estrutura pronta para que pesquisadores, cientistas de dados e profissionais possam conduzir seus próprios estudos de forma organizada e reproduzível.

O dataset final estará disponível no [Kaggle](https://www.kaggle.com/datasets/rafatrindade/feminicidio-br) e cobre diferentes manifestações da violência contra mulheres: desde registros policiais até óbitos por causas externas, com informações sobre perfis das vítimas, contextos, padrões territoriais e dinâmicas dos registros.

O objetivo de longo prazo é consolidar os estudos produzidos em [github.com/rafa-trindade/flor-de-aco](https://github.com/rafa-trindade/flor-de-aco) em um painel público e interativo - um instrumento de monitoramento, conscientização e enfrentamento da violência contra mulheres no Brasil.

---

## 📊 Fontes de Dados e Escopo

### **1. Violência Doméstica Autorreferida (Fonte: Pesquisa DataSenado)**

A **Pesquisa Violência Doméstica e Familiar contra a Mulher**, conduzida pelo **Instituto de Pesquisa DataSenado** (Senado Federal), é um levantamento nacional por telefone realizado em rodadas bienais desde 2005, com o objetivo de dimensionar a violência doméstica sob a ótica das próprias entrevistadas.

**Escopo e Processamento:** Foram consolidadas as **10 rodadas disponíveis (2005, 2007, 2009, 2011, 2013, 2015, 2017, 2019, 2021 e 2023)**. Cada rodada tem seu próprio questionário e seu próprio dicionário de dados oficial (a pergunta e as opções de resposta variam de uma edição para outra), então o processamento é feito ano a ano: o script varre a pasta de microdados brutos e a pasta de dicionários, casa cada CSV com o dicionário da mesma rodada e usa esse dicionário para (a) trocar o código de cada variável pela descrição da pergunta e (b) trocar o código de cada resposta pela descrição da categoria correspondente. Isso preserva a possibilidade de comparar/agregar as rodadas mesmo quando o instrumento de coleta muda de ano para ano.

**Bases disponibilizadas** (pasta `datasen/`):

- `datasen/pnvd_violencia_dom_{ano}.csv` - Base **tratada**: colunas nomeadas pela descrição da pergunta e respostas decodificadas pela descrição da categoria (ex.: coluna `P08` vira `em_que_estado_voce_mora`, e o valor `11` vira `Rondônia`). Uma edição por ano de pesquisa, 2005–2023.
- `datasen/raw/pnvd_{ano}.csv` - Base **bruta**, como distribuída pelo DataSenado (colunas e respostas em código), preservada para quem preferir aplicar seu próprio critério de recodificação.
- `datasen/dict/pnvd_dict_{ano}.xlsx` - Dicionário de dados oficial de cada rodada, usado como fonte de verdade para o de-para de colunas e categorias.

> INSTITUTO DE PESQUISA DATASENADO. *Microdados da Pesquisa Violência Doméstica e Familiar*, 2005 – 2023. Brasília, DF. 2007. Disponível em: <https://www.senado.leg.br/institucional/datasenado/paineis_dados/#/?pesquisa=violencia_domestica_familiar>.

---

### **2. Óbitos por Agressão (Fonte: SIM - DATASUS)**

O **Sistema de Informações sobre Mortalidade (SIM)**, gerenciado pelo **DATASUS/Ministério da Saúde**, consolida as Declarações de Óbito de todo o país e é a base oficial para estatísticas de mortalidade no Brasil.

**Escopo e Processamento:** São baixados via FTP público do DATASUS os arquivos de Declaração de Óbito por Causas Externas (`.dbc`), convertidos para Parquet em lotes e, em seguida, filtrados e consolidados via DuckDB. São mantidos apenas os registros **femininos** (`SEXO = 2`) classificados nos códigos da **CID-10 que indicam agressão (X85–Y09) e intervenção legal (Y35)** - recorte que permite analisar mortes violentas com potencial relação a dinâmicas de violência de gênero. Os campos de código (sexo, raça/cor, estado civil, local de ocorrência, tipo do óbito, gestação/puerpério e a causa básica) são decodificados para texto legível durante o processamento.

**Base disponibilizada** (pasta `datasus_sim/`):

- `datasus_sim/feminicidio_serie_historica.csv` - Série consolidada de óbitos femininos por causas externas com potencial enquadramento como feminicídio, já com os campos-código traduzidos (sexo, raça/cor, estado civil, causa básica descrita, tipo de óbito, gestação/puerpério, local de ocorrência, datas e municípios de residência/óbito).

*Observação: bases preliminares (ainda sujeitas a revisão pelo SIM) e a versão bruta pré-filtro fazem parte do roadmap do projeto, mas ainda não estão publicadas nesta versão do dataset.*

---

### **3. Violência Declarada (Fonte: Pesquisa Nacional de Saúde - IBGE)**

A **Pesquisa Nacional de Saúde (PNS)** é um inquérito domiciliar do **IBGE**, realizado em parceria com o Ministério da Saúde, que coleta informações sobre saúde, condições de vida e experiências de violência da população brasileira.

**Escopo e Processamento:** Foram utilizados os microdados de posição fixa (arquivo `.txt`) das duas edições disponíveis (**2013 e 2019**). Cada campo é extraído por posição de coluna (conforme o dicionário oficial de cada edição, que muda de layout de um ano para o outro) e decodificado para texto. Em seguida, a base é filtrada para manter apenas **mulheres que relataram ter sofrido violência** (física, psicológica ou sexual) nos 12 meses anteriores à entrevista. A base captura a violência sob a perspectiva da vítima - tipo de agressão, autor, local, frequência e busca por atendimento -, informações muitas vezes ausentes em registros policiais e de saúde.

**Bases disponibilizadas** (pasta `ibge/`):

- `ibge/pns_violencia_dom_2013.csv` - Microdados filtrados da PNS 2013 (mulheres vítimas de violência), com campos decodificados.
- `ibge/pns_violencia_dom_2019.csv` - Microdados filtrados da PNS 2019 (mulheres vítimas de violência), com campos decodificados. O layout de colunas de 2019 é mais detalhado que o de 2013 (violência psicológica, física e sexual tratadas em blocos de perguntas separados).
- `ibge/raw/PNS_2013.txt`, `ibge/raw/PNS_2019.txt` - Microdados brutos de posição fixa, como obtidos diretamente do IBGE (sem filtro, sem decodificação), para quem quiser reprocessar com outro recorte.

*Observação: por serem arquivos volumosos e sujeitos aos termos de uso de download do IBGE, os `.txt` brutos são obtidos manualmente e não via automação - diferente do fluxo do SIM, que é sincronizado por FTP.*

---

### **4. Registros de Ocorrências (Fonte: SINESP)** *(em desenvolvimento)*

O **Sistema Nacional de Informações de Segurança Pública (SINESP)** centraliza os registros criminais enviados pelas Secretarias Estaduais de Segurança Pública.

**Escopo e Processamento previstos:** boletins de ocorrência e registros de vítimas, com foco em crimes relacionados à violência contra mulheres, padronização de campos, identificação de tipologias e compatibilização territorial para análise comparativa entre estados.

---

### **5. Atendimentos Especializados (Fonte: DEAMs)** *(em desenvolvimento)*

As **Delegacias Especiais de Atendimento à Mulher (DEAMs)** concentram denúncias de violência de gênero e realizam investigação qualificada.

**Escopo e Processamento previstos:** registros de atendimentos e ocorrências realizados nas unidades especializadas em nível municipal, permitindo análises detalhadas das denúncias formalizadas diretamente nas portas de entrada dedicadas à proteção de mulheres.

---

### **6. Bases de Dados Auxiliares**

Para permitir análises mais ricas e cruzamentos de informações, o projeto conta com uma base auxiliar de referência geográfica, construída a partir de **dados abertos do Ministério da Saúde**.

**Escopo e Processamento:** o arquivo de municípios (`macroregiao_de_saude.zip`, Dados Abertos da Saúde) é combinado, via join no código do município (`cod_municipio`/`MUNCOD`, com zero à esquerda padronizado), com um arquivo complementar de geolocalização dos municípios.

**Base disponibilizada** (pasta `macroregiao/`):

- `macroregiao/geo_macroregiao.csv` - Lista oficial de municípios brasileiros associada às suas respectivas macrorregiões de saúde, regiões de saúde e coordenadas geográficas. Permite análise territorial, integração com as demais bases do projeto e agregação espacial.

---

## 🗓️ Cobertura Histórica

O repositório combina diferentes janelas temporais, de acordo com a fonte:

- **DataSenado (violência autorreferida):** 2005 a 2023, em rodadas bienais.
- **SIM/DATASUS (óbitos por agressão):** série consolidada desde 1996, com atualização contínua conforme novos dados são fechados pelo Ministério da Saúde.
- **PNS/IBGE (violência declarada):** edições pontuais de 2013 e 2019 (periodicidade do próprio inquérito do IBGE).

Essa amplitude temporal possibilita identificação de tendências de longo prazo, avaliação do impacto de políticas públicas e compreensão da evolução da violência de gênero ao longo de diferentes governos, ciclos econômicos e contextos sociais.

---

## 🔄 Atualização e Confiabilidade

Nem todas as fontes têm a mesma dinâmica de atualização:

- **SIM/DATASUS:** sincronização automatizada via FTP público do DATASUS, com reprocessamento das declarações de óbito por causas externas conforme novos arquivos são publicados.
- **DataSenado e PNS/IBGE:** bases estáticas - cada rodada/edição é um retrato fechado no tempo, incorporada ao repositório quando o instituto responsável publica os microdados oficiais. Não há "atualização" desses dados entre uma rodada e outra, apenas a incorporação de rodadas novas quando lançadas.
- **Macrorregiões (auxiliar):** atualizada quando o Ministério da Saúde publica revisão da malha de municípios/macrorregiões.

Em todos os casos, a padronização de nomes de coluna, tratamento de categorias e estrutura de pastas é mantida consistente entre atualizações.

---

## 📁 Estrutura de Pastas do Dataset

```
datasen/            -> PNVD tratado (colunas e categorias decodificadas), por ano
datasen/raw/        -> PNVD bruto, como distribuído pelo DataSenado
datasen/dict/       -> dicionários de dados oficiais do DataSenado, por ano
datasus_sim/        -> série histórica de óbitos por agressão (SIM/DATASUS)
ibge/                -> PNS filtrada (mulheres vítimas de violência), por edição
ibge/raw/            -> PNS bruta, microdados de posição fixa
macroregiao/         -> base auxiliar de geolocalização/macrorregiões de saúde
```

---

## 📄 Licença e Créditos

Este dataset consolidado é disponibilizado sob licença **CC0 1.0** (domínio público). Isso se refere ao trabalho de curadoria, padronização e harmonização realizado neste repositório - os dados originais permanecem de titularidade e responsabilidade das instituições abaixo, que devem ser citadas ao utilizar cada fonte individualmente:

- **DataSenado (Pesquisa Violência Doméstica e Familiar):**
  > INSTITUTO DE PESQUISA DATASENADO. *Microdados da Pesquisa Violência Doméstica e Familiar*, 2005 – 2023. Brasília, DF. 2007. Disponível em: <https://www.senado.leg.br/institucional/datasenado/paineis_dados/#/?pesquisa=violencia_domestica_familiar>. 

- **SIM/DATASUS (óbitos por causas externas):**
  > BRASIL. Ministério da Saúde. DATASUS. *Sistema de Informações sobre Mortalidade (SIM)*. Brasília, DF: Ministério da Saúde. Disponível em: <https://datasus.saude.gov.br/mortalidade-desde-1996-pela-cid-10>. 

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