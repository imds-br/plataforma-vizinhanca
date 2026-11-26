# Georreferenciamento dos endereços o pacote geocodebr do IPEA
# Mais informações em https://github.com/ipeaGIT/geocodebr/

#rm(list = ls())
#gc()

#install.packages("remotes")
#remotes::install_github("ipeaGIT/geocodebr")
#install.packages("janitor")
process_data <- function(raw_path,clean_path){
  library(arrow)
  library(geocodebr)
  library(dplyr)
  library(janitor)

  # carregando uma amostra de dados

  parquet_path <- file.path(raw_path, "censo_escolar","unique_schools.parquet")
  input_df <- read_parquet(parquet_path)
  input_df <- input_df %>%
    filter(!is.na(DS_ENDERECO) & !is.na(NU_ENDERECO) & !is.na(CO_CEP) & !is.na(NO_BAIRRO) & !is.na(name_muni) & !is.na(SG_UF))
  input_df$NU_ENDERECO <- ifelse(grepl("^[0-9]+$", input_df$NU_ENDERECO), 
                                as.numeric(input_df$NU_ENDERECO), 
                                NA)

  # Primeiro passo: indicar o nome das colunas com cada campo dos enderecos
  campos <- geocodebr::definir_campos(
    logradouro = "DS_ENDERECO",
    numero = "NU_ENDERECO",
    cep = "CO_CEP",
    localidade = "NO_BAIRRO",
    municipio = "name_muni",
    estado = "SG_UF"
  )

  # Segundo passo: geolocalizar

  # Se for fazer de apenas um data frame, pode realizar assim:
  df_sample <- input_df %>% head(226)  # Take a small sample

  df <- geocodebr::geocode(
    enderecos = input_df,
    campos_endereco = campos,
    resultado_completo = TRUE,
    resolver_empates = TRUE,
    resultado_sf = FALSE,
    verboso = FALSE,
    cache = TRUE,
    n_cores = 20
  )

  # Depois aplicá-la:

  write_parquet(df,file.path(clean_path,'schools','escolas_fromr.parquet'))
  return("Geocoding complete and files saved.")
}

