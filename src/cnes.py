import pandas as pd
import geopandas as gpd
from tqdm import tqdm
import os, zipfile

def cnes_py(raw_path, clean_path):
    # reading CNES geodata
    cnes = pd.read_parquet(os.path.join(clean_path,'CNES','cnes_estabelecimentos-fromr.parquet'))
    cnes = cnes.dropna()
    cnes['CO_CNES'] = cnes['CO_CNES'].astype(int)
    cnes.loc[:,'CO_UNIDADE'] = cnes.CO_UNIDADE.astype(str)
    cnes.loc[:,'CO_UNIDADE'] = cnes.CO_UNIDADE.str.replace(".0","")

    # adding tp_unidade
    cnes_dict = pd.read_csv(os.path.join(raw_path,"CNES","cnes_estabelecimentos.csv"), sep=';',encoding='latin1',low_memory=False)
    cnes_dict = cnes_dict[['CO_CNES','CO_UNIDADE','TP_UNIDADE','NU_LATITUDE','NU_LONGITUDE']]
    cnes_dict.loc[:,'CO_UNIDADE'] = cnes_dict.CO_UNIDADE.astype(str)
    cnes_dict.loc[:,'CO_UNIDADE'] = cnes_dict.CO_UNIDADE.str.replace(".0","")

    cnes = cnes.merge(cnes_dict, on=['CO_CNES','CO_UNIDADE'])

    # filtering
    cnes = cnes[(cnes.TP_UNIDADE<=21) | (cnes.TP_UNIDADE == 71) | (cnes.TP_UNIDADE == 73)] # https://jundiai.sp.gov.br/saude/wp-content/uploads/sites/17/2014/09/Tabela-de-Tipos-e-Subtipos-de-Estabelecimento-SCNES.pdf
    cnes.loc[cnes.CO_CNES==3753387,'NU_LONGITUDE'] = -cnes.loc[cnes.CO_CNES==3753387,'NU_LONGITUDE'] # fixing a mistake in the data
    print(print(cnes.precisao.value_counts()/cnes.shape[0])) # => vou usar latlon da base do MS; muita divergência com a base do IPEA

    # georef
    cnes = gpd.GeoDataFrame(cnes, geometry=gpd.points_from_xy(cnes.NU_LONGITUDE, cnes.NU_LATITUDE), crs='EPSG:4674')
    cnes.loc[cnes.NU_LATITUDE.isna() | cnes.NU_LONGITUDE.isna(),'geometry'] = gpd.points_from_xy(cnes.loc[cnes.NU_LATITUDE.isna() | cnes.NU_LONGITUDE.isna(),'lon'], cnes.loc[cnes.NU_LATITUDE.isna() | cnes.NU_LONGITUDE.isna(),'lat']) # fixing invalid geometries
    
    # hospitals
    for year in tqdm(range(8,23)):
        year = str(year).zfill(2)
        cnes[f'year_{year}'] = 0
        aux = pd.DataFrame()
        with zipfile.ZipFile(os.path.join(raw_path,'CNES','CNES.zip'), 'r') as z: 
            for state in ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 
                    'MT', 'MS', 'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 
                    'RS', 'RO', 'RR', 'SC', 'SP', 'SE', 'TO']:
                with z.open(f'ETLCNES.ST_{state}__{year}_05_t.csv') as file: # tomo Maio como mês de referencia (para todo ano)
                    df = pd.read_csv(file, sep = ',', encoding='latin1', low_memory=False)
                    df['QT_sum'] = df[df.columns[df.columns.str.contains('QT')]].sum(axis=1)
                    cnes.loc[cnes.CO_CNES.isin(df.CNES), f'year_{year}'] = 1
                    aux = pd.concat([aux, df[['CNES','QT_sum']]], ignore_index=True)
            cnes = cnes.merge(aux, right_on='CNES', left_on='CO_CNES', how='left').drop(columns=['CNES']).rename(columns={'QT_sum':'QT_'+year})

    # exporting
    cnes = cnes.drop(columns=['lat','lon']).rename(columns={'NU_LATITUDE':'lat','NU_LONGITUDE':'lon'})
    cnes.to_parquet(os.path.join(clean_path,'CNES','cnes_panel.parquet'))