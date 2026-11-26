"""Select usable facility locations without changing establishment counts."""


def located_points(data, source):
    """Filter spatial calculations only; retain original coordinates, CRS and attributes."""
    if data.crs is None:
        raise ValueError(f'{source}: missing CRS')
    geometry = data.geometry
    valid = ~geometry.is_empty & geometry.is_valid & geometry.geom_type.eq('Point')
    positions = valid.to_numpy().nonzero()[0]
    coordinates = geometry.iloc[positions]
    if data.crs.to_epsg() not in (4326, 4674):
        coordinates = coordinates.to_crs(4326)
    in_bounds = coordinates.x.between(-180, 180) & coordinates.y.between(-90, 90)
    positions = positions[in_bounds.to_numpy()]
    excluded = len(data) - len(positions)
    if excluded:
        print(f'{source}: {excluded:,} of {len(data):,} records have missing or invalid locations; '
              'excluded from spatial calculations.', flush=True)
    if len(data) and not len(positions):
        raise ValueError(f'{source}: no usable facility locations')
    # Positional selection also works when a previous spatial join repeated index labels.
    return data.iloc[positions].copy()
