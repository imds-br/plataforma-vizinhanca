# Georreferenciamento dos endereços o pacote geocodebr do IPEA
# Mais informações em https://github.com/ipeaGIT/geocodebr/

process_data <- function(path) {
  library(geocodebr)
  library(enderecobr)
  library(dplyr)
  library(arrow)

  # Passo 0: carregando dados
  input_df <- read_parquet(file.path(path,'asb-raw.parquet'))

  # Primeiro passo: padronizar campos
  campos  <- correspondencia_campos(
    logradouro = "endereco",
    numero = "numero",
    cep = "CEP",
    bairro  = "bairro",
    municipio = "IBGE",
    estado = "UF"
  )
  df <- padronizar_enderecos(input_df, campos_do_endereco = campos)

  # Segundo passo: geolocalizar
  campos <- geocodebr::definir_campos(
    logradouro = "logradouro_padr",
    numero = "numero_padr",
    cep = "cep_padr",
    localidade = "bairro_padr",
    municipio = "municipio_padr",
    estado = "estado_padr"
  )

  df <- geocodebr::geocode(
    enderecos = df,
    campos_endereco = campos,
    resultado_completo = TRUE,
    resolver_empates = TRUE,
    resultado_sf = FALSE,
    verboso = FALSE,
    cache = TRUE,
    n_cores = 20
  )

  # Passo final: aplicar e exportar
  input_df$lat <- df$lat
  input_df$lon <- df$lon
  input_df$precisao <- df$precisao
  input_df$desvio_metros <- df$desvio_metros
  write_parquet(input_df, file.path(path, "asb-fromr.parquet"))

  # Return
  "Geocoding complete and files saved."
}
