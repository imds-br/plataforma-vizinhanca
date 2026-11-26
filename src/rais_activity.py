"""Use one employment-based activity definition for RAIS counts and distances."""
import numpy as np
import pandas as pd


def employment_column(columns, source='RAIS'):
    for column in ('total_trabalhadores', 'njobs'):
        if column in columns:
            return column
    raise ValueError(f'{source}: missing employment column (total_trabalhadores or njobs)')


def active_establishments(data, source='RAIS'):
    column = employment_column(data.columns, source)
    workers = pd.to_numeric(data[column], errors='raise')
    values = workers.to_numpy(dtype=float, na_value=np.nan)
    if not np.isfinite(values).all():
        raise ValueError(f'{source}: missing or non-finite worker counts')
    return data.loc[workers > 0].copy()
