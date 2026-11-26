# Plataforma Vizinhança
Este repositório contém pacote de replicação da [Plataforma Vizinhança](https://vizinhancas.caleidos.dev.br/mapa/). A geocodificação de endereços usa o pacote `geocodebr` para R, desenvolvido por Pereira e Herszenhut ([2025](#referências)).

Veja também o [Atlas da Mobilidade Social](https://atlas.imdsbrasil.org/), baseado em Britto et al. ([2026](#referências)). 

## Instalação e execução
1. **Clone este repositório para sua máquina local**.
     Você pode fazer isso de duas maneiras:
     1. Baixando diretamente o repositório
     Caso prefira o download direto, siga os passos:
          1. Clique no botão verde no canto superior direito da [página do GitHub](https://github.com/imds-br/imds_neighborhoods) e selecione “Download ZIP”
          2. Extraia o conteúdo em uma pasta da sua preferência
     2. Clonando com Git (recomendado)
     Se preferir usar o Git, siga os passos:
          1. Instale o [Git](https://git-scm.com/downloads) em sua máquina
          2. No terminal, execute os comandos abaixo:
          ```bash
          git clone --branch master https://github.com/imds-br/imds_neighborhoods.git
          cd imds_neighborhoods
          ```
2. **Construa a pasta `data`**.
     Simplesmente siga o passo a passo indicado na seção **Requerimento de Dados** abaixo, mantendo-se atento à estrutura indicada para este diretório
3. **Prepare o ambiente virtual do python**.
     Siga os passos em ordem:
     1. Instale o [python](https://www.python.org/downloads/) (versão 3.12 ou superior)
     2. Instale o [uv](https://docs.astral.sh/uv/getting-started/installation/)
     3. Na raiz do repositório, instale as dependências: 
     ```bash
     uv sync
     ``` 
4. **Setup do R**.
     Siga os passos em ordem:
     1. Instale o [R](https://cran.r-project.org/bin/windows/base/) e, opcionalmente, o [RStudio](https://posit.co/products/open-source/rstudio/?sid=1)
     2. Instale o [RTools](https://cran.r-project.org/bin/windows/Rtools/)
     3. Abra o R e instale as dependencias necessárias como indicado abaixo:
     ```r
     install.packages(c("geocodebr", "enderecobr", "janitor", "dplyr", "arrow"))
     ```
5. **Execute o programa**.
     Para executar o programa, na raiz do projeto:
     ```bash
     uv run main.py
     ```

## Dados

Organize os dados na raiz do repositório. As pastas `data/raw/h3` e `data/clean` recebem arquivos intermediários. A RAIS georreferenciada é um insumo e deve ser colocada em `data/clean/RAIS` antes da execução.

```text
data/
├── raw/
│   ├── ASB/
│   ├── CNES/
│   ├── censo_escolar/
│   ├── grade/
│   └── h3/
└── clean/
    ├── ASB/
    ├── CNES/
    ├── RAIS/
    ├── accessibility/
    ├── h3/
    └── schools/
```

| Fonte | Arquivos esperados |
| --- | --- |
| Censo SUAS de 2022 | CSVs de dados gerais de CRAS e Centros de Convivência em `data/raw/ASB/`. Os nomes exatos estão no script de preparação. [Censo SUAS](https://aplicacoes.mds.gov.br/sagi/snas/vigilancia/index2.php) · [Preparação do SUAS](src/asb_mds.py) |
| Cadastro Nacional de Estabelecimentos de Saúde (CNES) | `data/raw/CNES/cnes_estabelecimentos.csv` e `data/raw/CNES/CNES.zip`, com os CSVs de maio por UF de 2008 a 2022. [Série histórica](https://pcdas.icict.fiocruz.br/conjunto-de-dados/cadastro-nacional-de-estabelecimentos-de-saude/) · [Cadastro de estabelecimentos](https://dados.gov.br/dados/conjuntos-dados/cnes-cadastro-nacional-de-estabelecimentos-de-saude) |
| Censo Escolar | Um arquivo `microdados_censo_escolar_<ano>.zip` por ano de 2008 a 2022 em `data/raw/censo_escolar/`. [Microdados do Censo Escolar](https://www.gov.br/inep/pt-br/acesso-a-informacao/dados-abertos/microdados/censo-escolar) |
| RAIS georreferenciada | Um arquivo `rais_firm_charact_geocoded_<ano>.parquet` por ano de 2012 a 2019 em `data/clean/RAIS/`. Cada arquivo deve conter `lon`, `lat` e uma coluna de contagem de trabalhadores (`total_trabalhadores` ou `njobs`), com valores numéricos, finitos e sem ausências. O cálculo considera apenas estabelecimentos com mais de zero trabalhadores. |
| Grade Estatística do Censo 2022 | Grade de 1 km do IBGE em `data/raw/grade/BR1KM.parquet`, em formato GeoParquet, com as colunas `nome_1KM`, `geometry` e `TOTAL`. [Grade Estatística](https://geoftp.ibge.gov.br/recortes_para_fins_estatisticos/grade_estatistica/censo_2022/grade_1km/) |

## Processamento e metodologia

1. [`main.py`](main.py) prepara os dados do SUAS, do CNES e do Censo Escolar. Em seguida, [`get_h3_cells`](src/h3_cells.py) delimita as células H3 e usa a Grade Estatística do IBGE para identificar as células habitadas.
2. [`prep_index`](src/prep_index.py) calcula as distâncias para cada célula e ano. O resultado inclui as medidas de acesso e o índice composto, gravados em `data/clean/accessibility/access_panel_idx_<resolução>.parquet`.
3. O índice usa o primeiro componente principal de quatro medidas de acesso em 2012–2019: escolas, serviços de saúde, equipamentos de assistência social e postos de trabalho. O código calcula duas versões do índice, com padronização (`ipse_z`) e normalização pelo mínimo e pelo máximo (`ipse_t`), e transforma os escores em valores de 0 a 1 com base nos quantis.
4. [`analysis`](src/analysis.py) gera as figuras de diagnóstico na resolução 8 e grava os mapas anuais em `output/year_pca/`.

### Medida de acessibilidade

O fluxo de execução principal chama `accessibility_chunked`, que aplica em paralelo o mesmo cálculo de [`accessibility`](src/accessibility.py). A função reprojeta as células e os pontos de referência para EPSG:5880. Em cada célula, usa uma grade interna com espaçamento de 1.000 metros ou, quando nenhum ponto da grade cai dentro da célula, usa o centroide. Para cada ponto amostrado, calcula a distância em linha reta até o equipamento ou local de trabalho mais próximo. A média dessas distâncias, em quilômetros, forma a coluna `accessibility`. Valores menores indicam maior proximidade.

## Especificações Técnicas
Este código foi executado em uma máquina com as seguintes especificações (relevantes):
- Intel® Xeon® Processor E5-2699 v3
- 1TB de memória RAM
- SSD KC3000 NVMe M.2 PCIe 4.0 (2048 GB)

## Referências
Britto, D., Fonseca, A., Pinotti, P., Sampaio, B., & Warwar, L. (2026). *"[Intergenerational Mobility in the Land of Inequality](https://direct.mit.edu/rest/article-abstract/doi/10.1162/REST.a.1775/136649/Intergenerational-Mobility-in-the-Land-of?redirectedFrom=fulltext)"*. The Review of Economics and Statistics.

Pereira, R. H. M., & Herszenhut, D. (2025). *geocodebr*: Geolocalização de Endereços Brasileiros (Versão v0.2.1) [Manual de software]. [https://github.com/ipeaGIT/geocodebr](https://github.com/ipeaGIT/geocodebr)
