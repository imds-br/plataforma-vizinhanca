import geopandas as gpd
import shapely as shp
import numpy as np
from joblib import Parallel, delayed
import os, warnings
from scipy.spatial import cKDTree

def generate_grid(polygon:shp.Polygon, spacing_m=100) -> np.ndarray:
    """
    Generate a grid of points within a polygon at a specified spacing.
    Parameters:

    - polygon: shapely.Polygon
      The input polygon geometry.
    - spacing_m: float
      Spacing in meters between points in the grid.

    Returns:
    - ndarray of shape (N, 2)
      Coordinates of grid points inside the polygon.
      If no grid point falls inside the polygon, returns the centroid.
    """
    minx, miny, maxx, maxy = polygon.bounds # get polygon bounds
    x = np.arange(minx, maxx, spacing_m) # generate 'spacing_m' spaced x-axis coordenates
    y = np.arange(miny, maxy, spacing_m) # generate 'spacing_m' spaced y-axis coordenates
    # Create the full mesh grid of points
    xx, yy = np.meshgrid(x, y)
    coords = np.column_stack((xx.ravel(), yy.ravel()))
    # Vectorized point construction and point-in-polygon test
    points = shp.points(coords)
    # Filter points only within the polygon
    mask = shp.contains(polygon, points)
    coords = coords[mask]    # Fallback to the centroid if no points are valid
    if coords.shape[0] == 0:
        return np.array([[polygon.centroid.x, polygon.centroid.y]])
    return coords

def get_network(reference_shapes:gpd.GeoDataFrame):
    """
    Converts geometries to a KDTree for distance calculations.
    
    Parameters:
    - reference_shapes: GeoDataFrame
      The input GeoDataFrame with geometries.

    Returns:
    - KDTree
    """
    coords = np.column_stack((
        reference_shapes.geometry.x.to_numpy(),
        reference_shapes.geometry.y.to_numpy()
    ))
    return cKDTree(coords)


def minimum_distance(tree,grid) -> float:
    """
    Calculates the average minimum distance from each point in the MultiPoint `grid_shape`
    to the nearest point in the `reference_shape`.
    
    Parameters:
    - tree: KDTree
      The KDTree of infrastructure points for distance calculations.
    - grid_shape: shapely.geometry.MultiPoint
      The set of points (grid) to measure distance from.

    Returns:
    - average_min_distance: float
      Average minimum distance from each grid point to the nearest reference shape.
    """ 
    distances, _ = tree.query(grid)
    return distances.mean() / 1000.0


def accessibility(gdf:gpd.GeoDataFrame, reference_shapes:gpd.GeoDataFrame, spacing_m:int) -> gpd.GeoDataFrame:
    """
    Calculate accessibility for each geospatial unit based on the distance to infrastructure points.

    Parameters:
    - gdf: GeoDataFrame
      Base geospatial data with polygon geometries representing the geospatial units of analysis.
    - reference_shapes: GeoDataFrame
      Points or multipoints representing infrastructure locations or access points for distance analysis.
    - spacing_m: float
      Defines the spacing (in meters) for generating a uniform spatial grid within each geometry.

    Returns:
    - GeoDataFrame
      The original GeoDataFrame with an added column 'accessibility' representing 
      the average minimum distance (in kilometers) from the grid points within each polygon 
      to the nearest reference shape.
      
    Description:
    This function projects the input data into a common coordinate reference system (EPSG:5880),
    generates a uniform spatial grid within each polygon using the specified spacing, and computes
    the average minimum distance from each point on this grid to the infrastructure reference shapes.
    This distance is used to derive accessibility metrics for spatial analysis.
    """
    result = gdf.to_crs('EPSG:5880').copy()
    tree = get_network(reference_shapes.to_crs("EPSG:5880"))
    # Use vectorized operations for generating grids and computing distances
    result["accessibility"] = result.geometry.apply(lambda g: minimum_distance(tree, generate_grid(g, spacing_m)))    
    return result

def process_polygon(geom, tree, spacing_m):
    return minimum_distance(tree, generate_grid(geom, spacing_m))

def accessibility_chunked(gdf:gpd.GeoDataFrame, reference_shapes:gpd.GeoDataFrame, spacing_m:int, n_jobs:int|None=None) -> gpd.GeoDataFrame:
    # Number of cores
    if n_jobs is None:
        cpu_count = os.cpu_count() or 1
        n_jobs = max(1, round(cpu_count * 0.7))
        
    # Pre-project data and prepare reference shapes
    result = gdf.to_crs('EPSG:5880').copy()
    tree = get_network(reference_shapes.to_crs("EPSG:5880"))
    with warnings.catch_warnings(action="ignore"):
      # Process geoms in parallel
      result["accessibility"] = Parallel(n_jobs=n_jobs, backend="threading", pre_dispatch="n_jobs")(
          delayed(process_polygon)(geom, tree, spacing_m)
          for geom in result.geometry
      )
    # Combine results
    return result
