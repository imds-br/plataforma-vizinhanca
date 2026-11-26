import pandas as pd
import geopandas as gpd
from src import accessibility as mine
import tqdm, os
from sklearn import preprocessing
from sklearn.decomposition import PCA

def sjoin_largest_overlap(left_gdf, right_gdf, right_cols, id_col="cell", area_crs=None, keep_unmatched=True):
    """
    Match each left geometry to the right geometry with which it has the
    largest positive-area intersection.

    Parameters
    ----------
    left_gdf : geopandas.GeoDataFrame
        Geometries to be matched. Must contain `id_col` and geometry.
    right_gdf : geopandas.GeoDataFrame
        Polygon geometries against which the left geometries are matched.
    right_cols : sequence of str
        Columns from `right_gdf` to include in the result.
    id_col : str, default "cell"
        Unique identifier in `left_gdf`.
    area_crs : CRS-like, optional
        Projected CRS used to calculate intersection areas. Required when
        the input CRS is geographic.
    keep_unmatched : bool, default True
        If True, retain left-side IDs with no positive-area intersection,
        filling `right_cols` with missing values.

    Returns
    -------
    pandas.DataFrame
        One row per unique left-side ID.
    """
    right_cols = list(right_cols)

    if id_col not in left_gdf.columns:
        raise KeyError(f"{id_col!r} is not present in left_gdf.")

    missing_right_cols = [ col for col in right_cols if col not in right_gdf.columns ]
    
    if missing_right_cols:
        raise KeyError( f"Columns missing from right_gdf: {missing_right_cols}" )

    if "geometry" in right_cols:
        raise ValueError("'geometry' should not be included in right_cols.")

    if id_col in right_cols:
        raise ValueError(f"{id_col!r} cannot also be included in right_cols.")

    if left_gdf.crs is None or right_gdf.crs is None:
        raise ValueError("Both GeoDataFrames must have a defined CRS.")

    if left_gdf.crs != right_gdf.crs:
        raise ValueError("left_gdf and right_gdf must use the same CRS.")

    if left_gdf[id_col].isna().any():
        raise ValueError(f"{id_col!r} contains missing values.")

    if left_gdf[id_col].duplicated().any():
        raise ValueError(f"{id_col!r} must uniquely identify rows in left_gdf.")

    left_geometry_col = left_gdf.geometry.name
    right_geometry_col = right_gdf.geometry.name

    left = left_gdf[[id_col, left_geometry_col]].copy()
    right = right_gdf[right_cols + [right_geometry_col]].copy()

    if left.geometry.name != "geometry":
        left = left.rename_geometry("geometry")

    if right.geometry.name != "geometry":
        right = right.rename_geometry("geometry")

    # overlay already has make_valid=True, but doing this explicitly makes
    # geometry repair visible and lets us remove empty results.
    left.geometry = left.geometry.make_valid()
    right.geometry = right.geometry.make_valid()

    left = left.loc[left.geometry.notna() & ~left.geometry.is_empty].copy()
    right = right.loc[right.geometry.notna() & ~right.geometry.is_empty].copy()

    if area_crs is not None:
        left = left.to_crs(area_crs)
        right = right.to_crs(area_crs)
    elif left.crs.is_geographic:
        raise ValueError(
            "Area cannot be reliably compared in a geographic CRS. "
            "Provide a projected `area_crs`, for example EPSG:5880."
        )

    intersections = gpd.overlay(left,right,how="intersection",keep_geom_type=False,make_valid=False)

    if intersections.empty:
        best_match = pd.DataFrame(columns=[id_col] + right_cols)
    else:
        intersections["__overlap_area__"] = intersections.geometry.area

        # Remove point/line contacts and any collapsed intersections.
        intersections = intersections.loc[intersections["__overlap_area__"] > 0]

        if intersections.empty:
            best_match = pd.DataFrame(columns=[id_col] + right_cols)
        else:
            idx_max = (
                intersections
                .groupby(id_col, sort=False)["__overlap_area__"]
                .idxmax()
            )

            best_match = (
                intersections
                .loc[idx_max, [id_col] + right_cols]
                .reset_index(drop=True)
            )

    if keep_unmatched:
        return (
            left_gdf[[id_col]]
            .merge(best_match, on=id_col, how="left", validate="one_to_one")
        )

    return best_match

def prep_index(raw_path:str, clean_path:str, level:str):
    # base imports
    print(f'Importing {level} polygons...')
    units = gpd.read_parquet(os.path.join(clean_path,'adm_regions',f'{level}.parquet'))
    unit_geometries = units[['unit_id', 'geometry']]
    
    print('Importing infrastructure data...')
    schools = gpd.read_parquet(os.path.join(clean_path,'schools','schools-shape.parquet'))
    cnes = gpd.read_parquet(os.path.join(clean_path,'CNES','cnes_panel.parquet'))
    asb = gpd.read_parquet(os.path.join(clean_path,'ASB','asb-clean.parquet'))
    
    for year in tqdm.tqdm(range(2008,2023),desc='Years'):
        schools_base = schools[schools[f'y_{year}']>0].copy()
        cnes_base = cnes[cnes[f'year_{str(year-2000).zfill(2)}']==1].copy()
        asb_base = asb[asb[f'y_{year-2000}']==1].copy()
        varlist = [schools_base,cnes_base,asb_base]
        if (year>=2012) & (year<=2019):
            rais = pd.read_parquet(os.path.join(clean_path,'RAIS',f'rais_firm_charact_geocoded_{year}.parquet'))
            rais = gpd.GeoDataFrame(rais, geometry = gpd.points_from_xy(rais.lon, rais.lat), crs='EPSG:4326')
            rais = rais.to_crs('epsg:4674')
            varlist.append(rais)
                    
        accessibility_br = []            
        for var in varlist:
            gdf_br = mine.accessibility_chunked(unit_geometries,var[var.geometry.is_valid & ~var.geometry.is_empty],1000)
            accessibility_br.append(gdf_br)
        if year == 2008: # first year copy as base df
            ydata = accessibility_br[0].rename(columns={'accessibility':f'schools_{year-2000}'}).copy()
        else:
            ydata = ydata.merge(accessibility_br[0][['unit_id','accessibility']],on='unit_id').rename(columns={'accessibility':f'schools_{year-2000}'})
        ydata = ydata.merge(accessibility_br[1][['unit_id','accessibility']],on='unit_id').rename(columns={'accessibility':f'cnes_{year-2000}'})
        ydata = ydata.merge(accessibility_br[2][['unit_id','accessibility']],on='unit_id').rename(columns={'accessibility':f'asb_{year-2000}'})
        if (year>=2012) & (year<=2019):
            ydata = ydata.merge(accessibility_br[3][['unit_id','accessibility']],on='unit_id').rename(columns={'accessibility':f'jobs_{year-2000}'})
        del accessibility_br
        
    # reshaping data
    drop_cols = ['geometry']
    panel_data = ydata.drop(columns=drop_cols).melt('unit_id', var_name='var_ny', value_name='Val').copy()
    panel_data['var_name']=panel_data.var_ny.str.split('_').str[0]
    panel_data['var_year']=panel_data.var_ny.str.split('_').str[1]
    panel_data = panel_data[~panel_data.var_year.isin(['s','23'])]
    panel_data = panel_data.pivot(columns='var_name', values='Val', index=['unit_id','var_year']).reset_index().copy()

    # adding geo info back
    panel_data = panel_data.merge(ydata[['unit_id'] + drop_cols], on='unit_id',how='left')
    panel_data = gpd.GeoDataFrame(panel_data)
    del ydata

    #add pop back to the data
    panel_data = panel_data.merge(units[['unit_id', 'pop']], on='unit_id', how='left')

    # export for regressions        
    panel_data['var_year'] = panel_data['var_year'].astype(float)

    ############
    # Indexing #
    ############
    
    # filter panel_data_idx for index estimation
    panel_data_idx = panel_data[(panel_data.var_year>=12) & (panel_data.var_year<=19)].copy()
    
    scaler_dim1 = preprocessing.StandardScaler()
    scaler_dim2 = preprocessing.MinMaxScaler()
    scaler_idx = preprocessing.QuantileTransformer(random_state=0)

    for scaler, scaler_header in zip([scaler_dim1,scaler_dim2], ['_z','_t']):
        
        # normalizing variables
        panel_data_idx.loc[:,'asb'+scaler_header] = scaler.fit_transform(panel_data_idx['asb'].values.reshape(-1,1))
        panel_data_idx.loc[:,'schools'+scaler_header] = scaler.fit_transform(panel_data_idx['schools'].values.reshape(-1,1))
        panel_data_idx.loc[:,'cnes'+scaler_header] = scaler.fit_transform(panel_data_idx['cnes'].values.reshape(-1,1))
        panel_data_idx.loc[:,'firms'+scaler_header] = scaler.fit_transform(panel_data_idx['jobs'].values.reshape(-1,1))
        
        # estimating PCA w/ normalized variables 
        pca = PCA(n_components=1)
        pca.fit(panel_data_idx[['asb'+scaler_header,'schools'+scaler_header,'cnes'+scaler_header,'firms'+scaler_header]])
        print(f"The standardized PCA expained variance is: {pca.explained_variance_ratio_}")
        print(f"The weights are: {pca.components_}")  # Eigenvector
        panel_data_idx.loc[:,'ipse'+scaler_header] = pca.fit_transform(panel_data_idx[['asb'+scaler_header,'schools'+scaler_header,'cnes'+scaler_header,'firms'+scaler_header]]).copy() # PCA result before scaling
        panel_data_idx.loc[:,'ipse'+scaler_header] = scaler_idx.fit_transform(-panel_data_idx['ipse'+scaler_header].values.reshape(-1,1)).copy() # 0-1 scale through quantiles
    
    # export final data w/ index calculated and other variables for analysis
    panel_data_idx = panel_data.merge(panel_data_idx[['unit_id','var_year','ipse_z','ipse_t']], on=['unit_id','var_year'], how='left')
    del panel_data
    
    # scaling variables for FIB (variáveis como índice)
    for var in ['cnes','asb','schools','jobs']:
        panel_data_idx.loc[:,var+'_idx'] = scaler_idx.fit_transform(-panel_data_idx[var].values.reshape(-1,1)).copy()
        
    # retain the geobr identifiers and names for each administrative unit
    unit_attributes = units.drop(columns=['geometry', 'pop'])
    panel_data_idx = panel_data_idx.merge(unit_attributes, on='unit_id', how='left')
    panel_data_idx['level'] = level
    
    # exporting
    os.makedirs(os.path.join(clean_path, 'accessibility'), exist_ok=True)
    gpd.GeoDataFrame(panel_data_idx).to_parquet(os.path.join(clean_path,'accessibility',f'access_panel_idx_{level}.parquet'), index=False)
