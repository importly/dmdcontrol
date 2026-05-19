from pathlib import Path
from typing import Iterator, cast

import usb.core
import numpy as np
import PIL.Image
from PIL import ImageOps
import pycrafter6500

WORKSPACE = Path(__file__).parent

def dmd_define():
    ## This function returns the dmd object with addresses
    # The user needs to verify each DMD 
    # dmd_type: str. "fm" and "k"
    address_list = find_addresses()

    pattern_list0 = [WORKSPACE / 'dmd_images' / '1.tif']
    pattern_list1 = [WORKSPACE / 'dmd_images' / '2.tif']
    
    dlp_temp0 = pycrafter6500.dmd(address_select=True, address = address_list[0])   #Load test pattern for user to see
    dlp_temp1 = pycrafter6500.dmd(address_select=True, address = address_list[1])
    dmd_pattern_load(dlp=dlp_temp0, pattern_file_list=pattern_list0, dark_time_val=0)
    dmd_pattern_load(dlp=dlp_temp1, pattern_file_list=pattern_list1, dark_time_val=0)

    print("The DMD that displays number 1 is the FM DMD")
    print("The DMD that displays number 2 is the K DMD")
    dlp_temp0.startsequence()
    dlp_temp1.startsequence()

    user_input = input("Press 'y' if this is corrent, press 'n if this is wrong': ")

    dlp_temp0.stopsequence()
    dlp_temp1.stopsequence()
    dlp_temp0.changemode(3)
    dlp_temp1.changemode(3)

    if user_input == "y":
        dmd_pattern_load(dlp=dlp_temp0, pattern_file_list=pattern_list0, dark_time_val=0)
        dmd_pattern_load(dlp=dlp_temp1, pattern_file_list=pattern_list1, dark_time_val=0)
        dlp_temp0.startsequence()
        dlp_temp1.startsequence()
        input("This is the current dmd order. Press any key to continue: ")
        dlp_temp0.stopsequence()
        dlp_temp1.stopsequence()

        return dlp_temp0, dlp_temp1
    
    elif user_input == "n":
        
        dmd_pattern_load(dlp=dlp_temp1, pattern_file_list=pattern_list0, dark_time_val=0)
        dmd_pattern_load(dlp=dlp_temp0, pattern_file_list=pattern_list1, dark_time_val=0)
        dlp_temp0.startsequence()
        dlp_temp1.startsequence()
        input("This is the current dmd order. Press any key to continue: ")
        dlp_temp0.stopsequence()
        dlp_temp1.stopsequence()

        return dlp_temp1, dlp_temp0  
    else: return None  




def find_addresses():           #Since addresses don't stay constant, we need to provide addresses of each DMD every time we run them
    devices = cast(Iterator[usb.core.Device], usb.core.find(find_all=True))
    address_list=[]
    for device in devices:
        if device.idVendor == 0x0451 and device.idProduct == 0xc900:    #Add to list of addresses if the device is a DMD controller
            address_list.append(device.address)

    return address_list




def dmd_pattern_load(dlp, pattern_file_list, exposure_val = 1e6, dark_time_val = 1e6, trigger_in_val = False, trigger_out_val = True, repeat = 0, open_from_file = True):
    ## This function loads a sequence into the dmd
    # dlp: dmd object
    # pattern_file_list: list containing file names
    # exposure_vals: exposure time in microseconds
    # dark_time_vals: dark time in microseconds
    # trigger_in_val: bool
    # trigger_out_val: bool
    # return None
    images = []
    if open_from_file == True:
        for image_filename in pattern_file_list:
            images.append((np.asarray(PIL.Image.open(image_filename)))//129)
    else:
        for image in pattern_file_list:
            images.append(np.asarray(image)//129)

    dlp.stopsequence()
    dlp.changemode(3)       #Pattern on the fly mode

    exposure = [int(exposure_val)]*len(pattern_file_list)
    dark_time = [int(dark_time_val)]*len(pattern_file_list)
    trigger_in = [trigger_in_val]*len(pattern_file_list)
    trigger_out = [trigger_out_val]*len(pattern_file_list)
    dlp.defsequence(images, exposure, trigger_in, dark_time, trigger_out, repeat)



class DMD_Image:
    def __init__(self, image: np.ndarray) -> None:
        self.crop_pixels = 20
        self.full_img = image
        self.positive_img = self.pos_img_no_inv(self.full_img)
        self.negative_img = self.neg_img_no_inv(self.full_img) 
        self.dmd_positive_img = np.asarray(ImageOps.pad(ImageOps.expand(PIL.Image.fromarray(self.positive_img),self.crop_pixels), (1920,1080), color="black"), dtype=np.uint8)
        self.dmd_negative_img = np.asarray(ImageOps.pad(ImageOps.expand(PIL.Image.fromarray(self.negative_img),self.crop_pixels), (1920,1080), color="black"), dtype=np.uint8)

    def change_image(self, image):
        self.new_img=image
        self.positive_img = self.pos_img_no_inv(self.new_img)
        self.negative_img = self.neg_img_no_inv(self.new_img)
        self.dmd_positive_img = np.asarray(ImageOps.pad(ImageOps.expand(PIL.Image.fromarray(self.positive_img),self.crop_pixels), (1920,1080), color="black"), dtype=np.uint8)
        self.dmd_negative_img = np.asarray(ImageOps.pad(ImageOps.expand(PIL.Image.fromarray(self.negative_img),self.crop_pixels), (1920,1080), color="black"), dtype=np.uint8)

    def pos_img_no_inv(self, a):            #This code is copied from Hannah's code for the display
        '''
        Makes the positive image of the kernel (pos nums => 1, neg nums => 0)
        '''
        if np.max(a)==0:
            return a
        new_matrix = np.zeros_like(a)
        try:
            new_matrix = a / abs(np.max(a))
        except FloatingPointError:
            pass
        new_matrix += 1
        new_matrix /= 2
        return new_matrix.astype(np.uint8)
    
    def neg_img_no_inv(self, a):
        '''
        Makes the negative image of the kernel (pos nums => 0, neg nums => 1)
        '''
        if np.max(a)==0:
            return np.zeros((32,32))+1
        new_matrix = np.zeros_like(a)
        try:
            new_matrix = a / abs(np.max(a))
        except FloatingPointError:
            pass
        new_matrix *= -1
        new_matrix += 1
        new_matrix /= 2
        tmp = new_matrix.astype(np.uint8)
        return tmp
    
        


def main():         #For testing only
    images=[]
    for i in range(10):
        images.append((np.asarray(PIL.Image.open(f"{i+1}.tif")))//129)

    dlp=pycrafter6500.dmd(address_select=True, address = 2)

    dlp.stopsequence()

    dlp.changemode(3)

    exposure=[500000]*30
    dark_time=[500000]*30
    trigger_in=[False]*30
    trigger_out=[1]*30

    dlp.defsequence(images,exposure,trigger_in,dark_time,trigger_out,12)    #repeatnum: number of items in sequence: 0 for infinite

    dlp.startsequence()

if __name__ == "__main__":
    main()