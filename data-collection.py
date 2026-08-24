import sys
from datetime import datetime
import requests
import h5py
import torch
import numpy as np
from tqdm import tqdm
from vortran_laser.stradus import StradusLaser, StradusState
from bcnn import TranslatorDataGen, KernelGen, Conv2dEODLA
from dmdcontrol.utils import CONFIG, WORKSPACE
RUN = CONFIG.get("Run", {})

## error alert hook
def global_error_handler(exc_type, exc_value, exc_traceback):
    laser.disable()
    h5py.File.close(data_file)
    requests.post("https://ntfy.sh/eodla", data=f"Uncaught exception: {exc_type.__name__}: {exc_value}".encode(encoding='utf-8'))

# Register the function as the global exception handler
sys.excepthook = global_error_handler

## h5py parameters
filename = 'calib_data'
dataset_size = 71500

## laser power
power = 60
laser = StradusLaser('/dev/ttyUSB0')
laser.enable()
if laser.power_setpoint != power:
    laser.power_setpoint = power
tqdm.write(f'Laser power setpoint: {laser.power_setpoint} mW')

if not laser.interlock_is_closed:
    tqdm.write(f'Note: {laser.wavelength}[nm] Laser is not armed via external key.')

if laser.state == StradusState.FAULT:
    tqdm.write(f'Laser in a fault state. Error codes are: {laser.faults}')

## conv and dmd device parameters
conv_params = {
    'batch_size': 110,
    'in_channels': 1,
    'out_channels': 1,
    'kernel_size': 9,
    'padding': 4,
    'bias': None,
    'stride': 1,
    'dilation': 1,
    'groups': 1,
    'eodla': True,
}

## datasets
translator_dataset = TranslatorDataGen(
    train=True, 
    download=True, 
    dataset_size=dataset_size, 
    image_size=16, 
    kernel_size=conv_params['kernel_size'], 
    in_channels=conv_params['in_channels'],
    )
translator_loader = torch.utils.data.DataLoader(
    translator_dataset, 
    batch_size=conv_params['batch_size'], 
    shuffle=False, 
    num_workers=1,
    drop_last=True,
    )
kernels = KernelGen(
    kernel_size=conv_params['kernel_size'],
    train=True,
)

if __name__ == '__main__':
    ## run dir ##
    run_dir = WORKSPACE / f"{RUN.get("output_root", "data-collection-logs")}_{datetime.now():%Y%m%d-%H%M%S}"
    run_dir.mkdir(parents=True, exist_ok=False)

    ## h5py ##
    # either load in file or create it if it doesn't exist
    data_file = h5py.File(str(run_dir / ('data.h5')), 'x')

    # create dataset for 16x16 convolution data
    data_file.create_dataset(
        'output',
        shape=(
            dataset_size // conv_params['batch_size'],
            conv_params['batch_size'],
            conv_params['out_channels'],
            60,
            60,
        ),
        dtype=np.float32,
    )
        
    # create dataset for 9x9 kernel
    data_file.create_dataset(
        'kernel',
        shape=(
            dataset_size // conv_params['batch_size'],
            conv_params['out_channels'],
            conv_params['in_channels'],
            conv_params['kernel_size'],
            conv_params['kernel_size'],
        ),
        dtype=np.float32,
    )
        
    # create dataset for 16x16 input
    data_file.create_dataset(
        'input',
        shape=(
            dataset_size // conv_params['batch_size'],
            conv_params['batch_size'],
            conv_params['in_channels'],
            16,
            16,
        ),
        dtype=np.float32,
    )
    
    # create dataset for labels
    data_file.create_dataset(
        'label',
        shape=(
            dataset_size // conv_params['batch_size'],
            conv_params['batch_size'],
            3,
        ),
        dtype=np.float32,
    )
    
    ## DMD convolution ##
    for idx, (fm, label) in tqdm(enumerate(translator_loader), total=len(translator_loader)):  
        # convolve
        kernel = kernels.get_kernel(idx)
        output = Conv2dEODLA.apply(
            input=fm,
            weight=kernel,
            bias=conv_params['bias'],
            stride=conv_params['stride'],
            padding=[4, 4],
            dilation=conv_params['dilation'],
            groups=conv_params['groups'],
            eodla=conv_params['eodla'],
            out_channels=conv_params['out_channels'],
            run_dir=run_dir,
        )

        # save to h5py file
        data_file['output'][idx] = output.cpu().numpy()
        data_file['kernel'][idx] = kernel.cpu().numpy().astype(np.float32)
        data_file['input'][idx] = fm.cpu().numpy().astype(np.float32)
        data_file['label'][idx] = label.cpu().numpy().astype(np.float32)

    laser.disable()

    requests.post("https://ntfy.sh/eodla", data="Done!".encode(encoding='utf-8'))