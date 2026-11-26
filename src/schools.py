import pandas as pd
from tqdm import tqdm
import geopandas as gpd
import os, zipfile, geobr

def compile_schools(raw_path:str, export=False):
    schools = pd.DataFrame()
    for year in tqdm(range(2008,2023)):
        with zipfile.ZipFile(os.path.join(raw_path,'censo_escolar',f'microdados_censo_escolar_{year}.zip'), 'r') as z:
            try:
                with z.open(f'microdados_ed_basica_{year}/dados/microdados_ed_basica_{year}.csv') as file:
                    df = pd.read_csv(file, sep = ';', encoding='latin1', low_memory=False)
            except:
                try:
                    with z.open(f'microdados_ed_basica_{year}/dados/microdados_ed_basica_{year}.CSV') as file:
                        df = pd.read_csv(file, sep = ';', encoding='latin1', low_memory=False)
                except:
                    with z.open(f'Microdados do Censo Escolar da Educaç╞o Básica {year}/dados/microdados_ed_basica_{year}.csv') as file:
                        df = pd.read_csv(file, sep = ';', encoding='latin1', low_memory=False)
        df =  df[df.TP_SITUACAO_FUNCIONAMENTO == 1]
        df = df[['NU_ANO_CENSO','NO_REGIAO','SG_UF','CO_MUNICIPIO',
                 'CO_ENTIDADE','NO_ENTIDADE','TP_CATEGORIA_ESCOLA_PRIVADA',
                 'DS_ENDERECO','NU_ENDERECO','DS_COMPLEMENTO','NO_BAIRRO','CO_CEP','QT_MAT_BAS']]
        df.rename(columns={'QT_MAT_BAS':'QT_MAT'}, inplace=True)
        schools = pd.concat([schools,df])
        del df
    schools.reset_index(drop=True, inplace=True)    
    if export:
        brasil = geobr.read_municipality(year=2022)
        brasil['code_muni'] = brasil.code_muni.astype(int)
        schools = schools[['CO_ENTIDADE','DS_ENDERECO','DS_COMPLEMENTO','NU_ENDERECO','NO_BAIRRO','SG_UF', 'CO_CEP','CO_MUNICIPIO']].drop_duplicates(subset='CO_ENTIDADE').merge(brasil[['code_muni','name_muni']], left_on='CO_MUNICIPIO', right_on='code_muni')
        schools.loc[:,['DS_ENDERECO','NU_ENDERECO','DS_COMPLEMENTO','NO_BAIRRO']] = schools.loc[:,['DS_ENDERECO','NU_ENDERECO','DS_COMPLEMENTO','NO_BAIRRO']].fillna("")
        schools.to_parquet(os.path.join(raw_path,'censo_escolar','unique_schools.parquet'))
    else: 
        return schools
    
def process_schools(raw_path:str,clean_path:str):
    # read data
    schools_r = pd.read_parquet(os.path.join(clean_path,'schools','escolas_fromr.parquet'))
    schools_r = gpd.GeoDataFrame(schools_r,geometry=gpd.points_from_xy(schools_r.lon, schools_r.lat),crs='epsg:4674')
    # merge data
    schools = compile_schools(raw_path)
    schools['NU_ANO_CENSO'] = 'y_'+schools.NU_ANO_CENSO.astype(str)
    schools = schools.merge(schools_r[['CO_ENTIDADE','geometry']], on='CO_ENTIDADE', how='left')
    # pivot df
    schools = schools.pivot(index=['CO_ENTIDADE','geometry'],columns=['NU_ANO_CENSO'],values='QT_MAT').fillna(0).reset_index()
    schools = gpd.GeoDataFrame(schools, geometry='geometry', crs='epsg:4674')
    schools.rename(columns={'CO_ENTIDADE':'id'}, inplace=True)
    # interpolating weird zero-valued years (excluding 2020-2021 pandemic years)
    sc_a = schools.copy()
    sc_a['y_2008'] = False
    sc_a['y_2022'] = False
    for year in range(2009,2022):
        sc_a[f'y_{year}'] = (schools[f'y_{year}']==0) & ((schools[f'y_{year-1}']>0) & (schools[f'y_{year+1}']>0))
    for ano in range(2009,2020):
        schools.loc[sc_a[f'y_{ano}']==True, f'y_{ano}'] = (schools.loc[sc_a[f'y_{ano}']==True, f'y_{ano-1}'] + schools.loc[sc_a[f'y_{ano}']==True, f'y_{ano+1}'])/2
    # exporting
    schools.to_parquet(os.path.join(clean_path,'schools','schools-shape.parquet'))