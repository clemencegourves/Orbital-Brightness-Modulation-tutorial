import os
import numpy as np
import apollinaire as apn
import matplotlib.pyplot as plt

from scipy import signal
from astropy.io import fits
###########################
def find_lightcurves(kic, files):
    matches = [f for f in files if f'kplr{kic:09d}' in os.path.basename(f)]
    return matches[0]
#==============================================================#
def preprocess (t, s, cut=2) :#cut = fréquence de coupure des singaux
    '''
    Preprocess a time series by substracting
    median and applying a FIR filter.
    Function by S.N. Breton
    '''
    # Setting median to 0.
    s = s - np.mean (s)
    # The low-frequency trend need to be filtered out.
    # Applying a FIR.
    s = apply_fir (t, s, cut=cut)
    # Setting median to 0.
    s = s - np.mean (s)
    return s
#==============================================================#
def apply_fir (t, s, cut=55, numtaps=10001) :
    '''
    Apply high-pass finite impulse response
    filter.
    Function by S.N. Breton
    '''
    dt = np.median (np.diff (t))
    numtaps = np.minimum (closest_odd(s.size//3), numtaps) 
    fs = 1 / (dt*86400)  
    f_cut = 1 / (cut*86400)
    bands=[0, f_cut, f_cut, fs/2] 
    desired=[0,0,1,1], 
    b = signal.firls (numtaps, bands, desired, fs=fs)
    s = signal.filtfilt (b, [1.0], s)
    return s
#==============================================================#
def closest_odd (a) :
    '''
    Function by S.N. Breton
    '''
    if a%2==1:
        return a
    else :
        return a-1
#==============================================================#  
def retrieve_KIC_info(df, kic):
    data = np.array(fits.open(df.loc[kic, "filenames"])[0].data) #unpack data
    t, v = data[:,0], data[:,1] # time and flux
    Prot = df.loc[kic, "Prot"] #rotational period of the star from Santos et al. 2019, 2021
    return t, v, Prot
#==============================================================#  
def compute_PSD(t, v):
    vpsd =  preprocess(t,v,cut=2) #cut at two days
    smoothed_y = apn.peakbagging.smooth(vpsd,10,win_type='triang',statistic='mean')
    dt = np.median (t[1:] - t[:-1]) * 86400

    freq, psd = apn.psd.series_to_psd(v, dt=dt, correct_dc=True) #Fourier transform
    freq = freq*1e6 #microHz
    psd  = psd *1e-6 #ppm^2/microHz
    return psd, freq
#==============================================================#  
def find_threshold(freq, range_bin, p_det=None):
    '''
    According to Appourchaux et al. 2000
    Find the specific threshold at which the signal become significant
    freq and range_bin must be in muHz
    '''
    T = 1/((freq[1]-freq[0])*1e-6) #convert to sec
    D_det = range_bin*1e-6 #convert to Hz
    s_det = np.log(T)+np.log(D_det)-np.log(p_det) #ppm2/Hz
    return s_det #ppm²/Hz
#==============================================================#
def threshold_func(s_det, freq, psd):
    '''
    Find the chi2 threshold (~0.7mediane).
    find the frequency and psd for which psd/mean>threshold.
    s_det mut be in ppm²/Hz, freq in muHz and psd in ppm²/Hz

    '''
    s_mean = 1/(1-1/3)*np.median(psd) # ppm2/Hz
    fseuil = freq[(psd/s_mean>s_det)]
    pseuil = psd[(psd/s_mean>s_det)]
    return fseuil, pseuil #en Hz et ppm²/Hz
#==============================================================#
def convert_freq_to_Porb(freq):
    '''
    For a frequency in muHz
    '''
    return 1/(86400*(freq*1e-6))
#==============================================================#
# def plot_LC(t, v,):
#     fig,ax = plt.subplots()
#     ax.scatter(t-t[0], v, color='k', s=0.1) #time set to 0, Kepler data = 4 years
#     ax.set_ylabel('Flux (ppm)')
#     ax.set_xlabel('Time (day)')
#     ax.set_xlim([0,np.max(t-t[0])])
#     return fig
#==============================================================#
def plot_PSD(kic, freq, psd, Prot):
    fig, ax = plt.subplots(figsize=(5.5,3))
    periods = convert_freq_to_Porb(freq)
    ax.plot(periods,psd, color = "black") #plot in period, easier to visualise
    ax.set_xlabel(r'Period [days]')
    ax.set_ylabel(r'PSD [ppm$^2/\mu$ Hz]')
    ax.set_xscale('log') 
    ax.set_yscale('log')
    ax.minorticks_on()
    ax.tick_params(axis='both', which = 'minor',direction='in', top=True, right = True)
    ax.set_xlim(np.min(periods[~np.isinf(periods)]),np.max(periods[~np.isinf(periods)]))
    ax.set_title(f'KIC {kic}', loc='right')
    fig.tight_layout()
    return fig,ax
#==============================================================#
def plot_phase_fold(t1, v1, Porb):
    phase = t1%Porb
    indices = np.argsort(phase)
    v = preprocess(t1,v1,cut=2)[indices]
    phase = phase[indices]
    smoothed_y = apn.peakbagging.smooth(v,10,win_type='triang',statistic='mean')
    # Figure #
    fig,ax=plt.subplots()
    ax.scatter(phase/Porb,v, s=0.1, c='k')#flux according to orbital phase
    ax.scatter(phase/Porb,smoothed_y, c='r',s=0.001)
    ax.set_xlim(0,1)
    ax.set_xlabel('Orbital Phase')
    ax.set_ylabel('Flux [ppm]')
    return fig, ax
#==============================================================#
def find_compagnon_peak(freq, psd, Prot, n_max=10):
    s_det = find_threshold(freq, 284-5, p_det=1e-100)  # delta = Nyquist freq - 5 µHz
    fthresh, psdthresh = threshold_func(s_det, freq, psd)

    # The rotation signal spreads over a broad hump around Prot (~noise + harmonics) so we only look at periods P < Prot / n_max
    n = fthresh / (1e6 / (86400 * Prot))      # n = Prot / P
    candidates = np.where((n > n_max) & (psdthresh > 0), psdthresh, np.nan)

    if np.all(np.isnan(candidates)):
        return np.nan, np.nan

    idx_max = np.nanargmax(candidates)
    return fthresh[idx_max], psdthresh[idx_max]