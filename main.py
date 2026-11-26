
############
# preamble #
############

import os, sys, tempfile 
from typing import cast
from src.asb_mds import asb_py, asb_r
from src.cnes import cnes_py
from src.schools import compile_schools, process_schools
from src.adm_regions import get_adm_regions, LEVELS
from src.prep_index import prep_index

tmp_path = r"D:/ARQUIVOS_TEMPORARIOS/pedro.maia" 
if os.path.exists(tmp_path):
    os.environ["TMPDIR"] = tmp_path
    os.environ["TEMP"] = tmp_path
    os.environ["TMP"] = tmp_path
    os.environ["JOBLIB_TEMP_FOLDER"] = tmp_path
    tempfile.tempdir = tmp_path

class suppress_stderr(object):
    def __enter__(self):
        self.stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self.stderr
        
with suppress_stderr():
    from rpy2.robjects.functions import SignatureTranslatedFunction
    from rpy2.robjects import r, globalenv       
     
#####################
# determining paths #
#####################

raw_data = os.path.join(os.getcwd(),'data','raw')
clean_data = os.path.join(os.getcwd(),'data','clean')

##################
# prep functions #
##################

def mds_prep(raw_data:str, clean_data:str):
    # preprocessing data
    asb_py(raw_data, clean_data)
    # geocoding CRAS and CREAS data in R (geocodebr)
    with suppress_stderr():
        source_func = cast(SignatureTranslatedFunction, r['source'])
        source_func(os.path.join(os.getcwd(),'src','geocoding_mds.R'))
        process_data = globalenv['process_data']
        process_data(os.path.join(clean_data, 'ASB'))
    # process these data
    asb_r(clean_data)

def cnes_prep(raw_data:str, clean_data:str):
    with suppress_stderr():
        # geocoding CNES data in R (geocodebr)
        source_func = cast(SignatureTranslatedFunction, r['source'])
        source_func(os.path.join(os.getcwd(),'src','geocoding_ubs.R'))
        process_data = globalenv['process_data']
        process_data(raw_data, clean_data)
    # process these data
    cnes_py(raw_data,clean_data)
    
def school_prep(raw_data:str, clean_data:str):
    # generate unique schools for georef
    compile_schools(raw_data, export=True) 
    with suppress_stderr():
        # geocoding schools data in R (geocodebr)
        source_func = cast(SignatureTranslatedFunction, r['source'])
        source_func(os.path.join(os.getcwd(),'src','geocoding_schools.R'))
        process_data = globalenv['process_data']
        process_data(raw_data, clean_data)
    # processing georef data
    process_schools(raw_data,clean_data)

######################
# executing the code #
######################
    
def main(level:str, preprocess:bool=False):
    # The amenity inputs are shared by all geographic levels.
    if preprocess:
        # georef data
        print('')
        print('\nPreprocessing the data...', end='', flush=True)
        if not os.path.exists(os.path.join(clean_data,'ASB','asb-clean.parquet')):
            mds_prep(raw_data,clean_data)
        if not os.path.exists(os.path.join(clean_data,'CNES','cnes_panel.parquet')):
            cnes_prep(raw_data,clean_data)    
        if not os.path.exists(os.path.join(clean_data,'schools','schools-shape.parquet')):
            school_prep(raw_data,clean_data) 
        print('\nPreprocessing the data... Done!     ')
    
    # Administrative polygons and their 2022 population
    print('')
    print(f'\nPreparing {level} polygons...', end='', flush=True)
    if not os.path.exists(os.path.join(clean_data,'adm_regions',f'{level}.parquet')):
        get_adm_regions(raw_data,clean_data,level)
    print(f'Preparing {level} polygons... Done!     ')
        
    # pca analysis
    print('')
    print('\nPrepping data for PCA analysis ...', end='', flush=True)
    if not os.path.exists(os.path.join(clean_data,'accessibility',f'access_panel_idx_{level}.parquet')):
        prep_index(raw_data,clean_data, level)
    print('\nPrepping data for PCA analysis ... Done!     ')
    
if __name__ == "__main__":
    for i, level in enumerate(LEVELS):
        print(f'\n\nRunning the code for {level} ...', end='', flush=True)
        main(level, preprocess=(i == 0))
