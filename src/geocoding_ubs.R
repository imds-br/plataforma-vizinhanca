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

  raw_path <- as.character(raw_path)[1]

  # carregando uma amostra de dados

  csv_path <- file.path(raw_path, "CNES","cnes_estabelecimentos.csv")
  input_df <- read.csv(csv_path, sep=';')
  input_df <- input_df %>% select(c(CO_CNES,CO_UNIDADE,TP_UNIDADE,CO_UF,CO_IBGE,
                                    CO_CEP,NO_LOGRADOURO, NU_ENDERECO, 
                                    NO_BAIRRO))%>% 
    filter(TP_UNIDADE <= 21 | TP_UNIDADE == 71 | TP_UNIDADE == 73) %>%  # https://jundiai.sp.gov.br/saude/wp-content/uploads/sites/17/2014/09/Tabela-de-Tipos-e-Subtipos-de-Estabelecimento-SCNES.pdf
    mutate(NU_ENDERECO = ifelse(NU_ENDERECO=="S/N","",NU_ENDERECO)) %>% 
    mutate(NU_ENDERECO = as.integer(NU_ENDERECO))

    
  # Primeiro passo: indicar o nome das colunas com cada campo dos enderecos
  campos <- geocodebr::definir_campos(
    logradouro = "NO_LOGRADOURO",
    numero = "NU_ENDERECO",
    cep = "CO_CEP",
    localidade = "NO_BAIRRO",
    municipio = "CO_IBGE",
    estado = "CO_UF"
  )

  # Segundo passo: geolocalizar

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

  df <- df %>% select(c(CO_CNES,CO_UNIDADE,lat,lon,precisao))


  # Depois aplicá-la:

  write_parquet(df,file.path(clean_path,"CNES","cnes_estabelecimentos-fromr.parquet"))
  return("Geocoding complete and files saved.")
}