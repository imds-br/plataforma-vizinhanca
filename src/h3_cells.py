import geobr, h3, os, zipfile
from shapely import Polygon
import geopandas as gpd
import pandas as pd
import numpy as np
from joblib import Parallel, delayed
from itertools import chain

MUNICIPALITY_YEAR = 2020

def get_pop(h3_cell:gpd.GeoDataFrame, raw_path:str):
    # read population data (dropping index to allow for interchangebly using loc/iloc)
    h3 = h3_cell.reset_index(drop=True).copy()
    h3 = h3.to_crs('epsg:5880')
    br_pop = gpd.read_parquet(os.path.join(raw_path,'grade','BR1KM.parquet'), columns=['nome_1KM', 'geometry', 'TOTAL']).reset_index(drop=True)
    br_pop = br_pop.to_crs('epsg:5880')
    br_pop['area_grade'] = br_pop.geometry.area

    # identify the h3 cells that intersect with the population data (see https://github.com/geopandas/geopandas/discussions/3063)
    h3_ix, pop_ix = br_pop.sindex.query(h3.geometry, predicate=None)
    pairs = pd.DataFrame({
        'h3_ix': h3_ix,
        'pop_ix': pop_ix
    })
    
    # generate a df with information on the intersected data
    pairs['cell'] = h3.loc[pairs['h3_ix'], 'cell'].to_numpy()
    pairs['TOTAL'] = br_pop.loc[pairs['pop_ix'], 'TOTAL'].to_numpy()
    pairs['area_grade'] = br_pop.loc[pairs['pop_ix'], 'area_grade'].to_numpy()

    # construct a new geometry column with the intersection of the h3 cells and the population data
    intersections = (
        h3.geometry.iloc[pairs['h3_ix']].reset_index(drop=True)
        .intersection(
            br_pop.geometry.iloc[pairs['pop_ix']].reset_index(drop=True)
        )
    )
    
    # compute are of each intersection and filter out the pairs with no intersection
    pairs['area_over'] = intersections.area
    pairs = pairs[pairs['area_over'] > 0]

    # compute the share of each grade in each cell and the weighted population
    pairs['share_grade'] = pairs['area_over'] / pairs['area_grade']
    pairs['weighted_pop'] = pairs['share_grade'] * pairs['TOTAL']

    # compute the total population in each cell, weighted by the share of each grade in that cell
    result = (
        pairs.groupby('cell', as_index=False)['weighted_pop']
        .sum()
        .assign(pop=lambda df: np.round(df['weighted_pop']).astype(int))
        [['cell', 'pop']]
    )
    
    # merge the population data with the h3 cells and return the result
    result = result.loc[result['pop'] > 0]
    if result.empty:
        raise ValueError('No H3 cells have positive allocated population')
    return h3.merge(result, on='cell', how='inner').to_crs('epsg:4674')

def poly_to_h3_with_geom(polygon, res=8):
    h3_shape = h3.geo_to_h3shape(polygon.__geo_interface__)
    cells = h3.h3shape_to_cells_experimental(
        h3_shape,
        res,
        contain='overlap'
    )
    return [(cell, Polygon([t[::-1] for t in h3.cell_to_boundary(cell)])) for cell in cells]
    

def get_h3_cells(raw_path:str, clean_path:str, res:int=8):
    # read shape
    municipalities = geobr.read_municipality(year=MUNICIPALITY_YEAR)
    geoms = municipalities.geometry.values   
    
    # read h3 cells
    par_threads = min(60,os.cpu_count())
    cell_geom_pairs = Parallel(n_jobs=par_threads, backend="loky")(delayed(poly_to_h3_with_geom)(geom, res=res) for geom in geoms)
    cell_geom_pairs = list(chain.from_iterable(cell_geom_pairs))
    h3_cells = gpd.GeoDataFrame(cell_geom_pairs, columns=['cell', 'geometry'], crs='epsg:4674')
    del cell_geom_pairs

    # clear duplicates
    h3_cells = h3_cells.drop_duplicates(subset='cell', keep='first')
    
    # exporting
    h3_cells.to_parquet(os.path.join(raw_path,'h3',f'h3_cells_{res}.parquet'))

    # getting population data + filter for populated areas
    h3_clean = get_pop(h3_cells, raw_path)
    h3_clean.to_parquet(os.path.join(clean_path,'h3',f'h3_clean_{res}.parquet'))