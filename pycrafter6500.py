import sys
from typing import Iterator, cast

import usb.core
import PIL.Image
import numpy as np
from tqdm import tqdm
from erle import encode


#This file has been modified to support operating multiple DMDs by Trung

##function that converts a number into a bit string of given length

def convlen(a,l):
    b=bin(a)[2:]
    padding=l-len(b)
    b='0'*padding+b

    return b

##function that converts a bit string into a given number of bytes

def bitstobytes(a):
    bytelist=[]
    if len(a)%8!=0:
        padding=8-len(a)%8
        a='0'*padding+a
    for i in range(len(a)//8):
        bytelist.append(int(a[8*i:8*(i+1)],2))

    bytelist.reverse()

    return bytelist

#---------Modified part--------------
def init_alternative(dev_address):
    #This function replaces the __init__ function inside the dmd class
    devices = cast(Iterator[usb.core.Device], usb.core.find(find_all=True))
    for device in devices:
        if device.idVendor == 0x0451 and device.idProduct == 0xc900 and device.address == dev_address:
            return device
    return None



#---------End of modified part--------

##a dmd controller class

class dmd():
    def __init__(self, address_select=False, address=1):
        if address_select==False:
            found = usb.core.find(idVendor=0x0451 ,idProduct=0xc900 )
        else:
            found = init_alternative(dev_address=address)   #modified code

        if found is None:
            sys.exit("DMD device not found on USB bus")
        self.dev = cast(usb.core.Device, found)

        # Source - https://stackoverflow.com/a/67459378
        # Posted by Eno Gerguri
        # Retrieved 2026-02-05, License - CC BY-SA 4.0

        # cfg = self.dev[0]

        # # iterate over interfaces
        # for interface in cfg:
        #     print(f"Interface Number: {interface.bInterfaceNumber}")

        i = 0
        if self.dev.is_kernel_driver_active(i):
            try:
                self.dev.detach_kernel_driver(i)
            except usb.core.USBError as e:
                sys.exit("Could not detatch kernel driver from interface({0}): {1}".format(i, str(e)))

        self.dev.set_configuration()

        self.ans=[]

## standard usb command function

    def command(self,mode,sequencebyte,com1,com2,data=()):
        buffer = []

        flagstring=''
        if mode=='r':
            flagstring+='1'
        else:
            flagstring+='0'
        flagstring+='1000000'
        buffer.append(bitstobytes(flagstring)[0])
        buffer.append(sequencebyte)
        temp=bitstobytes(convlen(len(data)+2,16))
        buffer.append(temp[0])
        buffer.append(temp[1])
        buffer.append(com2)
        buffer.append(com1)

        if len(buffer)+len(data)<65:

            for i in range(len(data)):
                buffer.append(data[i])

            for i in range(64-len(buffer)):
                buffer.append(0x00)


            self.dev.write(1, buffer)

        else:
            for i in range(64-len(buffer)):
                buffer.append(data[i])

            self.dev.write(1, buffer)

            buffer = []

            j=0
            while j<len(data)-58:
                buffer.append(data[j+58])
                j=j+1
                if j%64==0:
                    self.dev.write(1, buffer)

                    buffer = []

            if j%64!=0:

                while j%64!=0:
                    buffer.append(0x00)
                    j=j+1


                self.dev.write(1, buffer)






        self.ans=self.dev.read(0x81,64)

## functions for checking error reports in the dlp answer

    def checkforerrors(self):
        self.command('r',0x22,0x01,0x00,[])
        if self.ans[6]!=0:
            print("error check: ", self.ans[6])

## function printing all of the dlp answer

    def readreply(self):
        for i in self.ans:
            print("read reply: ", hex(i))

## functions for idle mode activation

    def idle_on(self):
        self.command('w',0x00,0x02,0x01,[int('00000001',2)])
        self.checkforerrors()

    def idle_off(self):
        self.command('w',0x00,0x02,0x01,[int('00000000',2)])
        self.checkforerrors()

## functions for power management

    def standby(self):
        self.command('w',0x00,0x02,0x00,[int('00000001',2)])
        self.checkforerrors()

    def wakeup(self):
        self.command('w',0x00,0x02,0x00,[int('00000000',2)])
        self.checkforerrors()

    def reset(self):
        self.command('w',0x00,0x02,0x00,[int('00000010',2)])
        self.checkforerrors()

## test write and read operations, as reported in the dlpc900 programmer's guide

    def testread(self):
        self.command('r',0xff,0x11,0x00,[])
        self.readreply()

    def testwrite(self):
        self.command('w',0x22,0x11,0x00,[0xff,0x01,0xff,0x01,0xff,0x01])
        self.checkforerrors()

## some self explaining functions

    def changemode(self,mode):
        self.command('w',0x00,0x1a,0x1b,[mode])
        self.checkforerrors()

    def startsequence(self):
        self.command('w',0x00,0x1a,0x24,[2])
        self.checkforerrors()

    def pausesequence(self):
        self.command('w',0x00,0x1a,0x24,[1])
        self.checkforerrors()

    def stopsequence(self):
        self.command('w',0x00,0x1a,0x24,[0])
        self.checkforerrors()


    def configurelut(self,imgnum,repeatnum):
        img=convlen(imgnum,11)
        repeat=convlen(repeatnum,32)

        string=repeat+'00000'+img

        bytes=bitstobytes(string)

        self.command('w',0x00,0x1a,0x31,bytes)
        self.checkforerrors()


    def definepattern(self,index,exposure,bitdepth,color,triggerin,darktime,triggerout,patind,bitpos):
        payload=[]
        index=convlen(index,16)
        index=bitstobytes(index)
        for i in range(len(index)):
            payload.append(index[i])

        exposure=convlen(exposure,24)
        exposure=bitstobytes(exposure)
        for i in range(len(exposure)):
            payload.append(exposure[i])
        optionsbyte=''
        optionsbyte+='1'
        bitdepth=convlen(bitdepth-1,3)
        optionsbyte=bitdepth+optionsbyte
        optionsbyte=color+optionsbyte
        if triggerin:
            optionsbyte='1'+optionsbyte
        else:
            optionsbyte='0'+optionsbyte

        payload.append(bitstobytes(optionsbyte)[0])

        darktime=convlen(darktime,24)
        darktime=bitstobytes(darktime)
        for i in range(len(darktime)):
            payload.append(darktime[i])

        triggerout=convlen(triggerout,8)
        triggerout=bitstobytes(triggerout)
        payload.append(triggerout[0])

        patind=convlen(patind,11)
        bitpos=convlen(bitpos,5)
        lastbits=bitpos+patind
        lastbits=bitstobytes(lastbits)
        for i in range(len(lastbits)):
            payload.append(lastbits[i])



        self.command('w',0x00,0x1a,0x34,payload)
        self.checkforerrors()



    def setbmp(self,index,size):
        payload=[]

        index=convlen(index,5)
        index='0'*11+index
        index=bitstobytes(index)
        for i in range(len(index)):
            payload.append(index[i])


        total=convlen(size,32)
        total=bitstobytes(total)
        for i in range(len(total)):
            payload.append(total[i])

        self.command('w',0x00,0x1a,0x2a,payload)
        self.checkforerrors()

## Extra functions for GPIO
    def GPIO_config(self, pin_select: int, config: int, state: int):
        '''
        pin_select: pin number from 0 to 8
        config:     0 for input, 1 for output
        state:      0 for low, 1 for high
        '''
        self.command('w',0x00,0x1a,0x38,[pin_select, (config<<1) | state])
        self.checkforerrors()

#    def GPIO_state(self, pin_select: int, state: int):
#        '''
#        pin_select: pin number from 0 to 8
#        state:      0 for low. 1 for high
#        '''
#        self.command('w',0x00,0x1a,0x38,[pin_select, state])
#        self.checkforerrors()
## End of GPIO functions


## bmp loading function, divided in 56 bytes packages
## max  hid package size=64, flag bytes=4, usb command bytes=2
## size of package description bytes=2. 64-4-2-2=56

    def bmpload(self,image,size):

        packnum=size//504+1

        counter=0

        for i in range(packnum):
            #if i %100==0:
                #print (i,packnum)
            payload=[]
            if i<packnum-1:
                leng=convlen(504,16)
                bits=504
            else:
                leng=convlen(size%504,16)
                bits=size%504
            leng=bitstobytes(leng)
            for j in range(2):
                payload.append(leng[j])
            for j in range(bits):
                payload.append(image[counter])
                counter+=1
            self.command('w',0x11,0x1a,0x2b,payload)


            self.checkforerrors()


    def defsequence(self,images,exp,ti,dt,to,rep):

        self.stopsequence()

        arr=[]

        for i in images:
            arr.append(i)

##        arr.append(numpy.ones((1080,1920),dtype='uint8'))

        num=len(arr)

        encodedimages=[]
        sizes=[]
        # print("Merging and encoding...")
        for i in range((num-1)//24+1):
            # print ('merging...')
            if i<((num-1)//24):
                imagedata=arr[i*24:(i+1)*24]
            else:
                imagedata=arr[i*24:]
            # print ('encoding...')
            imagedata,size=encode(imagedata)

            encodedimages.append(imagedata)
            sizes.append(size)

            if i<((num-1)//24):
                for j in range(i*24,(i+1)*24):
                    self.definepattern(j,exp[j],1,'111',ti[j],dt[j],to[j],i,j-i*24)
            else:
                for j in range(i*24,num):
                    self.definepattern(j,exp[j],1,'111',ti[j],dt[j],to[j],i,j-i*24)

        self.configurelut(num,rep)

        # print('Uploading...')
        for i in tqdm(range((num-1)//24+1), total = (num-1)//24+1, leave=False):

            self.setbmp((num-1)//24-i,sizes[(num-1)//24-i])

            # print ('uploading...')
            self.bmpload(encodedimages[(num-1)//24-i],sizes[(num-1)//24-i])

    #--------------Modified extra function: Load from a file list-------------------

    def dmd_pattern_load(self, pattern_file_list, exposure_val = 1e6, dark_time_val = 1e6, trigger_in_val = False, trigger_out_val = True, repeat = 0,  open_from_file = True):
        ''' This function loads a sequence into the dmd
        pattern_file_list: list containing file names
        exposure_vals: exposure time in microseconds
        dark_time_vals: dark time in microseconds
        trigger_in_val: bool
        trigger_out_val: bool
        open_from_file = =True (False if numpy arrays or PIL Images are input)
        return None
        '''
        images = []
        if open_from_file == True:
            for image_filename in pattern_file_list:
                images.append((np.asarray(PIL.Image.open(image_filename)))//129)
        elif type(pattern_file_list[0])==np.ndarray:
            for image in pattern_file_list:
                images.append(image)
        else:
            for image in pattern_file_list:
                images.append(np.asarray(image)//129)

        self.stopsequence()
        self.changemode(3)       #Pattern on the fly mode

        exposure = [int(exposure_val)]*len(pattern_file_list)
        dark_time = [int(dark_time_val)]*len(pattern_file_list)
        trigger_in = [trigger_in_val]*len(pattern_file_list)
        trigger_out = [trigger_out_val]*len(pattern_file_list)
        self.defsequence(images, exposure, trigger_in, dark_time, trigger_out, repeat)