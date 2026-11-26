"""Load administrative polygons and assign 2022 statistical-grid population."""

import os

import geobr
import geopandas as gpd
import numpy as np
import pandas as pd

LEVELS = {
    'neighborhood': geobr.read_neighborhood,
    'municipality': geobr.read_municipality,
    'immediate_region': geobr.read_immediate_region,
    'intermediate_region': geobr.read_intermediate_region,
    'state': geobr.read_state,
    'macroregion': geobr.read_region,
}

CODE_COLUMNS = {
    'neighborhood': ('code_neighborhood', 'code_muni'),
    'municipality': ('code_muni',),
    'immediate_region': ('code_immediate',),
    'intermediate_region': ('code_intermediate',),
    'state': ('code_state',),
    'macroregion': ('code_region',),
}


def get_pop(polygons: gpd.GeoDataFrame, raw_path: str, id_col: str = 'cell'):
    # Keep the same area-overlap allocation used for the original H3 cells.
    units = polygons.reset_index(drop=True).to_crs('EPSG:5880').copy()
    grid = gpd.read_parquet(
        os.path.join(raw_path, 'grade', 'BR1KM.parquet'),
        columns=['nome_1KM', 'geometry', 'TOTAL'],
    ).reset_index(drop=True).to_crs('EPSG:5880')
    grid['area_grade'] = grid.geometry.area

    unit_ix, grid_ix = grid.sindex.query(units.geometry, predicate=None)
    pairs = pd.DataFrame({'unit_ix': unit_ix, 'grid_ix': grid_ix})
    pairs[id_col] = units.loc[pairs['unit_ix'], id_col].to_numpy()
    pairs['TOTAL'] = grid.loc[pairs['grid_ix'], 'TOTAL'].to_numpy()
    pairs['area_grade'] = grid.loc[pairs['grid_ix'], 'area_grade'].to_numpy()
    intersections = (
        units.geometry.iloc[pairs['unit_ix']].reset_index(drop=True)
        .intersection(grid.geometry.iloc[pairs['grid_ix']].reset_index(drop=True))
    )
    pairs['area_over'] = intersections.area
    pairs = pairs[pairs['area_over'] > 0]
    pairs['share_grade'] = pairs['area_over'] / pairs['area_grade']
    pairs['weighted_pop'] = pairs['share_grade'] * pairs['TOTAL']

    result = (
        pairs.groupby(id_col, as_index=False)['weighted_pop']
        .sum()
        .assign(pop=lambda frame: np.round(frame['weighted_pop']).astype(int))
        [[id_col, 'pop']]
    )
    return units.merge(result, on=id_col, how='inner').to_crs('EPSG:4674')


def get_adm_regions(raw_path: str, clean_path: str, level: str):
    """Save geobr polygons and their population for one geographic level."""
    if level not in LEVELS:
        raise ValueError(f'Unknown geographic level: {level}')

    units = LEVELS[level](year=2022, simplified=False)
    if units is None or units.empty:
        raise ValueError(f'geobr returned no {level} geometries')
    if units.crs is None:
        raise ValueError(f'geobr returned {level} geometries without a CRS')

    units = units.loc[units.geometry.notna() & ~units.geometry.is_empty].copy()
    units = units.reset_index(drop=True).to_crs('EPSG:4674')
    if units.empty:
        raise ValueError(f'No valid {level} geometries')

    # Preserve all geobr attributes, while exposing one ID to the existing panel code.
    codes = [column for column in CODE_COLUMNS[level] if column in units.columns]
    if level != 'neighborhood' and not codes:
        raise KeyError(f'Expected a {level} code column in {list(units.columns)}')
    if level == 'neighborhood' and 'code_neighborhood' in codes and 'code_muni' in codes:
        units['unit_id'] = units['code_muni'].astype('Int64').astype(str) + '_' + units['code_neighborhood'].astype('Int64').astype(str)
    elif level == 'neighborhood' and 'code_neighborhood' in codes:
        units['unit_id'] = units['code_neighborhood'].astype(str)
    elif level == 'neighborhood' and 'code_muni' in codes:
        units['unit_id'] = units['code_muni'].astype(str) + '_' + units.groupby('code_muni').cumcount().astype(str)
    elif codes:
        units['unit_id'] = units[codes[0]].astype(str)
    else:
        # Some geobr releases omit a neighborhood code. The source order is
        # reproducible for a fixed geobr snapshot; names and codes stay attached.
        units['unit_id'] = units.index.astype(str)

    if level == 'neighborhood':
        # geobr 2022 repeats some complete neighborhood geometries under
        # different district/subdistrict attributes. Those attributes are
        # not unique at the neighborhood level, so do not retain one at random.
        units = units.drop(columns=[
            'code_district', 'name_district',
            'code_subdistrict', 'name_subdistrict',
        ], errors='ignore')
        units = units.drop_duplicates(subset=['unit_id', 'geometry'])
        repeated = units.loc[units['unit_id'].duplicated(keep=False)]
        if not repeated.empty:
            # Preserve all pieces if a future geobr release has distinct
            # polygons for the same neighborhood code.
            combined = repeated.dissolve(by='unit_id', as_index=False, aggfunc='first')
            single = units.loc[~units['unit_id'].duplicated(keep=False)]
            units = gpd.GeoDataFrame(
                pd.concat([single, combined], ignore_index=True),
                geometry='geometry', crs=units.crs,
            )

    if units['unit_id'].duplicated().any():
        raise ValueError(f'{level} unit_id is not unique; inspect geobr code columns')

    raw_file = os.path.join(raw_path, 'adm_regions', f'{level}.parquet')
    clean_file = os.path.join(clean_path, 'adm_regions', f'{level}.parquet')
    os.makedirs(os.path.dirname(raw_file), exist_ok=True)
    os.makedirs(os.path.dirname(clean_file), exist_ok=True)
    units.to_parquet(raw_file, index=False)
    populated = get_pop(units, raw_path, id_col='unit_id')
    populated.to_parquet(clean_file, index=False)
