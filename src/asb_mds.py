import geopandas as gpd
import pandas as pd
import numpy as np
import shapely as shp
import geobr
import os
from typing import cast

def fix_lon(column):
    # 1. clean notation
    clean_col = column.str.replace(' ','').str.replace('.', '')
    # 2. separate tens and units + join them accordingly
    tens = clean_col.str[:3]
    units = clean_col.str[3:]
    parsed = (tens + '.' +units)
    # 3. place nonsense value for failed attempts
    return parsed.mask(parsed.eq('.')).astype(float)

def fix_lat(brasil, df):
    # 0. prep variables
    column = df.latitude.copy()
    sure_small = brasil[(brasil.min_lat>-10)].abbrev_state.values
    mb_states = brasil[(brasil.max_lat>-10) & (brasil.max_lat<0) & ~(brasil.min_lat>-10)].rename(columns={'abbrev_state':'UF'})
    # 1. clean notation
    clean_col = column.str.replace(' ','').str.replace('.', '')
    # 2. identify positive and negative latitudes
    has_coordinate = column.notna() & ~column.str.contains(' ', na=False)
    negatives = has_coordinate & column.str.contains('-', na=False)
    positives = has_coordinate & ~negatives
    tens = clean_col.copy()    
    units = clean_col.copy()
    # 3. separate tens and units of easy places
    tens[positives] = clean_col[positives].str[:1]
    units[positives] = clean_col[positives].str[1:]
    tens[negatives & df.UF.isin(sure_small)] = clean_col[negatives & df.UF.isin(sure_small)].str[:2]
    units[negatives & df.UF.isin(sure_small)] = clean_col[negatives & df.UF.isin(sure_small)].str[2:]
    tens[negatives & ~df.UF.isin(sure_small) & ~df.UF.isin(mb_states.UF.values)] = clean_col[negatives & ~df.UF.isin(sure_small) & ~df.UF.isin(mb_states.UF.values)].str[:3]
    units[negatives & ~df.UF.isin(sure_small) & ~df.UF.isin(mb_states.UF.values)] = clean_col[negatives & ~df.UF.isin(sure_small) & ~df.UF.isin(mb_states.UF.values)].str[3:]
    # 4. distinguish one- and two-digit latitudes in states spanning -10 degrees
    mixed = negatives & df.UF.isin(mb_states.UF)
    mixed_coordinates = clean_col[mixed]
    short_tens = mixed_coordinates.str[:2]
    short_units = mixed_coordinates.str[2:]
    max_lat = df.loc[mixed, 'UF'].map(mb_states.set_index('UF').max_lat).astype(float)
    needs_two_digits = (short_tens + '.' + short_units).astype(float) > max_lat
    tens[mixed] = short_tens.mask(needs_two_digits, mixed_coordinates.str[:3])
    units[mixed] = short_units.mask(needs_two_digits, mixed_coordinates.str[3:])
    # 5. place nonsense value for failed attempts
    parsed = tens + '.' + units
    return parsed.where(has_coordinate).astype(float)

def asb_py(raw_path:str, clean_path:str):
    # get brazilian boundaries
    state_data = geobr.read_state(year=2020)
    states = cast(gpd.GeoDataFrame, state_data)
    bounds = states.geometry.bounds
    brasil = states.assign(min_lat=bounds['miny'], max_lat=bounds['maxy'])

    # import data
    cras = pd.read_csv(os.path.join(raw_path,'ASB','Censo_SUAS_2022_CRAS_Dados_Gerais_Divulgação.csv'), usecols=['IBGE','NU_IDENTIFICADOR','q01','q02','q03','q04','q06','q08','q010','q015','latitude','longitude'] , encoding='latin1', sep=';',low_memory=False, dtype={'latitude': object, 'longitude': object})
    cras.columns = ['IBGE','NU_IDENTIFICADOR','nome','prefix','endereco','numero','bairro','CEP','UF','data','latitude','longitude']
    cc = pd.read_csv(os.path.join(raw_path,'ASB','Censo_SUAS_ 2022_ Centros_de_Convivência_dados_gerais.csv'), usecols=['IBGE','NU_IDENTIFICADOR','q01','q02','q03','q04','q06','q07','q09','q014','Latitude','Longitude'], encoding='latin1', sep=';',low_memory=False, dtype={'Latitude': object, 'Longitude': object})
    cc.columns = ['NU_IDENTIFICADOR','IBGE','nome','prefix','endereco','numero','bairro','CEP','UF','data','latitude','longitude']

    # fix lat and lon
    cras['latitude'] = fix_lat(brasil, cras)
    cras['longitude'] = fix_lon(cras.longitude)
    cc['latitude'] = fix_lat(brasil, cc)
    cc['longitude'] = fix_lon(cc.longitude)
    
    # merging datasets
    cras['tipo'] = 'cras'
    cc['tipo'] = 'centro de convivência'
    df = pd.concat([cras,cc], ignore_index=True)
    coordinates = df[['longitude', 'latitude']]
    df['dups'] = coordinates.notna().all(axis=1) & coordinates.duplicated(keep=False)
    df['endereco'] = df['prefix'] + ' ' + df['endereco']
    df.drop(columns=['prefix'], inplace=True)

    # export
    asb_path = os.path.join(clean_path, 'ASB')
    os.makedirs(asb_path, exist_ok=True)
    df.to_parquet(os.path.join(asb_path, 'asb-raw.parquet'), index=False)
    
def asb_r(clean_path:str):
    # read and work the data
    asb = pd.read_parquet(os.path.join(clean_path,'ASB','asb-fromr.parquet'))
    asb = asb[asb.data!=' ']
    asb['desvio_metros']/=1000
    asb.sort_values(by=['desvio_metros'],ascending=False, inplace=True)
    asb.reset_index(drop=True,inplace=True)

    asb['geo_suas'] = asb.apply(lambda x: gpd.GeoDataFrame(geometry=[shp.geometry.Point(x.longitude,x.latitude)],crs='epsg:4674').to_crs('epsg:5880').geometry.values[0], axis=1)
    asb['geo_r'] = asb.apply(lambda x: gpd.GeoDataFrame(geometry=[shp.geometry.Point(x.lon,x.lat)],crs='epsg:4674').to_crs('epsg:5880').geometry.values[0], axis=1)
    asb['mds_r_dist'] = asb.apply(lambda x: shp.distance(x.geo_suas,x.geo_r), axis=1)/1000
    asb.drop(columns=['geo_suas','geo_r'],inplace=True)

    # fixing the MDS duplicated geometries that the geocodebr has a high precision
    asb.loc[(asb.dups==True) & (asb.desvio_metros<=1.2),'latitude'] = asb.loc[(asb.dups==True) & (asb.desvio_metros<=1.2),'lat']
    asb.loc[(asb.dups==True) & (asb.desvio_metros<=1.2),'longitude'] = asb.loc[(asb.dups==True) & (asb.desvio_metros<=1.2),'lon']
    # attributing NA to the remaining duplicated geometries
    print(asb.loc[(asb.dups==True) & (asb.desvio_metros>1.2)].shape[0])
    asb.loc[(asb.dups==True) & (asb.desvio_metros>1.2),'latitude'] = np.nan
    asb.loc[(asb.dups==True) & (asb.desvio_metros>1.2),'longitude'] = np.nan
    # fixing the strongly diverging geometries that the geocodebr has a high precision
    asb.loc[(asb.mds_r_dist>30) & (asb.desvio_metros<=1.2), 'latitude'] = asb.loc[(asb.mds_r_dist>30) & (asb.desvio_metros<=1.2), 'lat']
    asb.loc[(asb.mds_r_dist>30) & (asb.desvio_metros<=1.2), 'longitude'] = asb.loc[(asb.mds_r_dist>30) & (asb.desvio_metros<=1.2), 'lon']

    # making it geo
    asb = gpd.GeoDataFrame(asb, geometry = gpd.points_from_xy(asb.longitude,asb.latitude), crs='epsg:4674')
    # fixing invalid or empty geometries
    asb.loc[(~asb.geometry.is_valid) & (asb.desvio_metros<=1.2),'latitude'] = asb.loc[(~asb.geometry.is_valid) & (asb.desvio_metros<=1.2),'lat']
    asb.loc[(~asb.geometry.is_valid) & (asb.desvio_metros<=1.2),'longitude'] = asb.loc[(~asb.geometry.is_valid) & (asb.desvio_metros<=1.2),'lon']
    asb.geometry = gpd.points_from_xy(
        asb.longitude, asb.latitude, crs="EPSG:4674"
    )

    # formatting data
    asb = asb[['NU_IDENTIFICADOR','data','geometry']]
    asb['year'] = asb['data'].str[-4:].astype(int)
    for i in range(2008,2023):
        asb.loc[:,f'y_{i-2000}'] = 0
        asb.loc[asb['year']<=i,f'y_{i-2000}'] = 1
    asb.drop(columns=['data','year'], inplace=True)

    # exporting
    asb.to_parquet(os.path.join(clean_path,'ASB','asb-clean.parquet'))
