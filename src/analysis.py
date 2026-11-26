import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import geobr, os
from PIL import Image
import pandas as pd
import seaborn as sns
from joblib import Parallel, delayed
from mpl_toolkits.axes_grid1.inset_locator import mark_inset

def plot_mapa_por_ano(panel_data_idx, brazil_states, brazil, 
                      minx, miny, maxx, maxy, 
                      var, ano,
                      rj_min_t, rj_max_t, rj_min_z, rj_max_z, 
                      label_t, label_rj_t, label_z, label_rj_z, 
                      output_path):
    if var == 'ipse_t':
        suffix = "_t"
        rjmin = rj_min_t
        rjmax = rj_max_t
        label_tot = label_t
        label_rj_tot = label_rj_t
    else:
        suffix = "_z"
        rjmin = rj_min_z
        rjmax = rj_max_z
        label_tot = label_z
        label_rj_tot = label_rj_z

    plt.rcParams["font.family"] = "serif"
    fig, ax = plt.subplots(figsize=(10,10))

    # pca plot
    panel_data_idx[panel_data_idx.var_year==ano].plot(
        ax=ax,
        column=var,
        scheme='user_defined', 
        legend=True, 
        cmap='viridis',
        legend_kwds={'interval':True},
        classification_kwds={'bins':label_tot},
        zorder=5)

    brazil_states.plot(ax=ax, color='white', edgecolor='k', lw=0.4, zorder=4)

    # minimap for RJ
    rj = panel_data_idx[(panel_data_idx.code_muni==3304557) & (panel_data_idx.var_year==ano)].copy()
    inset_ax = ax.inset_axes([0.05, 0.05, 0.3, 0.3], xlim=[minx, maxx], ylim=[miny, maxy])
    cax = inset_ax.inset_axes([0, 1.05, 1, 0.05], transform=inset_ax.transAxes)
    brazil[brazil.abbrev_state=="RJ"].plot(ax=inset_ax, color='white', lw=.5, edgecolor='black')
    rj.plot(ax=inset_ax, column=var, legend=True, cmap='viridis', cax=cax, vmin=rjmin, vmax=rjmax,
            legend_kwds={'shrink':0.7, "orientation": "horizontal", "ticklocation": "top", 'ticks':label_rj_tot})
    brazil[brazil.code_muni==3304557].boundary.plot(ax=inset_ax, color='black', lw=.4)

    inset_ax.set_xlim(minx - 0.03, maxx + 0.03)
    inset_ax.set_ylim(miny - 0.03, maxy + 0.03)
    inset_ax.set_xticks([])
    inset_ax.set_yticks([])
    #ax.indicate_inset_zoom(inset_ax, edgecolor="black", lw=1.4, zorder=6)
    mark_inset(ax, inset_ax, loc1=2, loc2=4, fc="none", ec="black", lw=1.4, alpha=.5, zorder=6)
    
    # legend
    leg1 = ax.get_legend()
    for ea in leg1.legend_handles:
        ea.set_marker('s')
        ea.set_markeredgecolor('k')
        ea.set_markeredgewidth(0.5)
    leg1.set_title('IPSE')
    leg1.set_bbox_to_anchor((1, 0))
    leg1.set_loc('lower right')

    ax.set_facecolor('gainsboro')
    inset_ax.set_facecolor('gainsboro')
    ax.grid(True, zorder=4, color='snow')
    ax.set_axisbelow(True)
    ax.set_title(f"Ano: 20{str(ano).zfill(2)}", loc='left', pad=10, fontdict={'fontsize': 12, 'fontweight': 'bold'})

    # export
    os.makedirs(os.path.join(output_path,'year_pca'), exist_ok=True)
    fig.savefig(os.path.join(output_path,'year_pca',f'{ano}{suffix}.png'), dpi=350, bbox_inches='tight')
    plt.close(fig)


def analysis(clean_path:str, output_path:str, res:int=8):
    
    # read data
    brazil = geobr.read_municipality(year=2022)
    brazil_states = geobr.read_state(year=2020)
    panel_data_idx = gpd.read_parquet(os.path.join(clean_path,'accessibility',f'access_panel_idx_{res}.parquet'))
    
    # remove duplicated cells keeping the one with largest population
    panel_data_idx = panel_data_idx.sort_values(by=['pop'], ascending=False).drop_duplicates(subset=['cell','var_year'], keep='first')
        
    # ******************
    # *** Categories ***
    # ******************
    panel_data_idx = panel_data_idx.dropna(subset=['ipse_z','ipse_t'])
    panel_data_idx.loc[:,'quantile_flag_t'] = pd.qcut(panel_data_idx['ipse_t'], q=5, labels=['Muito Ruim', 'Ruim', 'Médio', 'Bom', 'Muito Bom'])
    panel_data_idx.loc[:,'quantile_flag_z'] = pd.qcut(panel_data_idx['ipse_z'], q=5, labels=['Muito Ruim', 'Ruim', 'Médio', 'Bom', 'Muito Bom'])

    # *********************************************
    # *** Assessing for methodology differences ***
    # *********************************************
    
    print('     Assessing methodology differences...', end='', flush=True)
    fig,ax = plt.subplots(1,2,figsize=(15,6))
    ax[0].scatter(panel_data_idx[['ipse_z','ipse_t']].ipse_z,panel_data_idx[['ipse_z','ipse_t']].ipse_t, s=.1)
    ax[0].plot([0, 1], [0, 1], color="red", linestyle="--", label="Linha de 45°")
    for i in range(len(panel_data_idx['ipse_z'].quantile([.2, .4, .6, .8]))):
        if i ==0:
            ax[0].axvline(x=panel_data_idx['ipse_z'].quantile([.2, .4, .6, .8]).values[i], color='black', linestyle='--', label='Quantis')
        else:
            ax[0].axvline(x=panel_data_idx['ipse_z'].quantile([.2, .4, .6, .8]).values[i], color='black', linestyle='--')
        ax[0].axhline(y=panel_data_idx['ipse_t'].quantile([.2, .4, .6, .8]).values[i], color='black', linestyle='--')

    corr_data = panel_data_idx[['quantile_flag_z','quantile_flag_t']].copy()
    corr_matrix = pd.DataFrame(np.zeros((len(corr_data.quantile_flag_z.unique()), len(corr_data.quantile_flag_z.unique()))), index=['Muito Bom','Bom','Médio','Ruim','Muito Ruim'], columns=['Muito Ruim', 'Ruim', 'Médio', 'Bom', 'Muito Bom'])
    for j in corr_data.quantile_flag_z.unique():
        for i in corr_data.quantile_flag_t.unique():
            corr_matrix.loc[corr_matrix.index==i,j] = (corr_data[corr_data.quantile_flag_z==j].quantile_flag_t==i).mean()

    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', fmt=".2f", linewidths=0.5, ax=ax[1])

    ax[0].legend(loc='center right') 
    ax[0].set_title("Gráfico de Dispersão das Metodologias de Normalização")
    ax[0].set_xlabel("PCA Padronizado")
    ax[0].set_ylabel("PCA MinMax")
    ax[1].set_title("Matriz de Concordância")
    ax[1].set_xlabel("PCA Padronizado")
    ax[1].set_ylabel("PCA MinMax")
    
    os.makedirs(output_path, exist_ok=True)
    fig.savefig(os.path.join(output_path,f'methodology_differences.png'), dpi=300, bbox_inches='tight')
    
    # ******************************
    # *** Plotting model results ***
    # ******************************
    print('     Plotting model results...', end='', flush=True)
    # preparing labels
    panel_data_idx = panel_data_idx.to_crs('epsg:4674')
    label_t = panel_data_idx.ipse_t.quantile([.1,.2,.3,.4,.5,.6,.7,.8,.9,1]).values
    label_rj_t = np.around(panel_data_idx[panel_data_idx.code_muni==3304557].ipse_t.quantile([0.01,.25,.75]).values, decimals=3)

    label_z = panel_data_idx.ipse_z.quantile([.1,.2,.3,.4,.5,.6,.7,.8,.9,1]).values
    label_rj_z = np.around(panel_data_idx[panel_data_idx.code_muni==3304557].ipse_z.quantile([0.01,.25,.75]).values, decimals=3)

    # Calculate the bounding box for the inset plot
    rj_bounds = panel_data_idx[panel_data_idx.code_muni==3304557]

    minx, miny, maxx, maxy = rj_bounds.total_bounds

    # Calculate global min and max values for the pca column
    rj_min_t = rj_bounds.ipse_t.min()
    rj_max_t = rj_bounds.ipse_t.max()
    rj_min_z = rj_bounds.ipse_z.min()
    rj_max_z = rj_bounds.ipse_z.max()

    tasks = []
    for var in ['ipse_t','ipse_z']:
        for ano in range(12,20):
            tasks.append((var, ano))
            
    Parallel(n_jobs=min(55,os.cpu_count()*.75), timeout=99999)(
        delayed(plot_mapa_por_ano)(
            panel_data_idx, brazil_states, brazil, 
            minx, miny, maxx, maxy, 
            var, ano,
            rj_min_t, rj_max_t, rj_min_z, rj_max_z, 
            label_t, label_rj_t, label_z, label_rj_z, 
            output_path
        )
        for var, ano in tasks
    )

    # ******************
    # *** Making GIF ***
    # ******************
    print('     Making GIFs...', end='', flush=True)
    # User editable values
    method = Image.FASTOCTREE
    colors = 256

    for suffix in ["_t","_z"]:
        imgs = []
        for i in range(12,20):
            filename = os.path.join(output_path,'year_pca',f'{i}{suffix}.png')
            try:
                im = Image.open(filename)
                pImage = im.quantize(colors=colors, method=method, dither=0)
                imgs.append(pImage)
            except:
                print(f'ERROR: Unable to open {filename}')

        imgs[0].save(
            os.path.join(output_path,f"pca{suffix}.gif"),
            format="GIF",
            append_images=imgs[1:],
            save_all="true",
            duration=800,
            loop=0
        )