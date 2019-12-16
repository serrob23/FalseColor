"""
#===============================================================================
# 
#  License: GPL
#
#
#  Copyright (c) 2019 Rob Serafin, Liu Lab, 
#  The University of Washington Department of Mechanical Engineering  
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License 2
#  as published by the Free Software Foundation.
# 
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
# 
#   You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
# 
#===============================================================================

Rob Serafin
11/20/2019

"""


import os
import scipy.ndimage as nd
import skimage.filters as filt
import skimage.exposure as ex
import skimage.util as util
import skimage.morphology as morph
from skimage.color import rgb2hed, rgb2hsv, hsv2rgb
import cv2
import numpy
from numba import cuda, njit
import math


@cuda.jit #direct GPU compiling
def rapid_getRGBframe(nuclei, cyto, output, nuc_settings,
                        cyto_settings, k_nuclei, k_cyto):
    #TODO: implement array base normalization
    """
    GPU based exponential false coloring operation. Used by rapidFalseColor()

    Parameters
    ----------
    nuclei : 2D numpy array 
        dtype = float
        Nuclear channel image, already pre processed

    cyto : 2d numpy array
        dtype = float
        Cytoplasm channel image, already pre processed.
        
    nuc_settings : float
        RGB constant for nuclear channel
    
    cyto_settings : float
        RGB constant for cyto channel

    k_nuclei : float
        Additional multiplicative constant for nuclear channel. Eventually will get removed once 
        flat fielding is in place for all pseudo coloring methods.

    k_cyto: float
        Additional multiplicative constant for cytoplasmic channel. Eventually will get removed once 
        flat fielding is in place for all pseudo coloring methods.        
    """
    row,col = cuda.grid(2)

    #iterate through image and assign pixel values
    if row < output.shape[0] and col < output.shape[1]:
        tmp = nuclei[row,col]*nuc_settings*k_nuclei + cyto[row,col]*cyto_settings*k_cyto
        output[row,col] = 255*math.exp(-1*tmp)


@cuda.jit
def rapidFieldDivision(image,flat_field,output):
    """
    Used for rapidFalseColoring() when flat field has been calculated

    Parameters
    ----------

    image : numpy array written to GPU

    flat_field : numpy array written to GPU

    output : numpy array written to GPU
        result from computation

    """
    row,col = cuda.grid(2)

    if row < output.shape[0] and col < output.shape[1]:
        tmp = image[row,col]/flat_field[row,col]
        output[row,col] = tmp

def rapidFalseColor(nuclei, cyto, nuc_settings, cyto_settings,
                   TPB=(32,32) , nuc_normfactor = 8500, cyto_normfactor=3000,
                   nuc_background = 50, cyto_background = 50,
                   run_FlatField = False):
    """
    Parameters
    ----------
    nuclei : numpy array
        Nuclear channel image
        
    cyto : numpy array
        Cytoplasm channel image
        
    nuc_settings : list
        Settings of RGB constants for nuclear channel. Should be in order R, G, B.
    
    cyto_settings : list
        Settings of RGB constants for cytoplasm channel. Should be in order R, G, B.

    nuc_normfactor : int or array
        Defaults to empirically determined constant for flat fielding. Otherwise it should be a 
        numpy array representing the true flat field image.

    cyto_normfactor : int or array
        Defaults to empirically determined constant for flat fielding. Otherwise it should be a 
        numpy array representing the true flat field image.

    nuc_background : int or float
        defaults to 50, background threshold for subtraction

    cyt_background : int or float
        defaults to 50, background threshold for subtraction
        
    TPB : tuple (int,int)
        THREADS PER BLOCK: (x_threads,y_threads)
        used for GPU threads

    run_FlatField : bool
        defaults to False, boolean to apply flatfield

    Returns
    -------
    RGB_image : 3D numpy array
        Combined false colored image in the standard RGB format [X, Y, C]

    """

    #ensure float dtype
    nuclei = nuclei.astype(float)
    cyto = cyto.astype(float)

    #set mulciplicative constants, changes on flat fielding vs background subtraction
    k_nuclei = 1.0
    k_cyto = 1.0

    #create blockgrid for gpu
    blockspergrid_x = int(math.ceil(nuclei.shape[0] / TPB[0]))
    blockspergrid_y = int(math.ceil(nuclei.shape[1] / TPB[1]))
    blockspergrid = (blockspergrid_x, blockspergrid_y)
    
    #allocate memory for background subtraction
    nuclei = numpy.ascontiguousarray(nuclei)
    pre_nuc_output = cuda.to_device(numpy.zeros(nuclei.shape))
    nuc_global_mem = cuda.to_device(nuclei)

    #run background subtraction or normalization for nuclei

    #use flat fielding
    if run_FlatField:
        nuc_normfactor = numpy.ascontiguousarray(nuc_normfactor)
        nuc_norm_mem = cuda.to_device(nuc_normfactor)
        rapidFieldDivision[blockspergrid,TPB](nuc_global_mem,nuc_norm_mem,pre_nuc_output)

    #otherwise use standard background subtraction
    else:
        k_nuclei = 0.08
        nuc_background = getBackgroundLevels(nuclei)[1]
        rapid_preProcess[blockspergrid,TPB](nuc_global_mem,nuc_background,
                                                nuc_normfactor,pre_nuc_output)
    
    #allocate memory for background subtraction
    cyto = numpy.ascontiguousarray(cyto)
    pre_cyto_output = cuda.to_device(numpy.zeros(cyto.shape))
    cyto_global_mem = cuda.to_device(cyto)

    #run background subtraction or normalization for cyto

    #use flat fielding
    if run_FlatField:
        cyto_normfactor = numpy.ascontiguousarray(cyto_normfactor)
        cyto_norm_mem = cuda.to_device(cyto_normfactor)
        rapidFieldDivision[blockspergrid,TPB](cyto_global_mem,cyto_norm_mem,pre_cyto_output)

    # otherwise use standard background subtraction
    else:
        k_cyto = 0.012
        cyto_background = getBackgroundLevels(cyto)[1]
        rapid_preProcess[blockspergrid,TPB](cyto_global_mem,cyto_background,
                                                cyto_normfactor,pre_cyto_output)
    
    #create output array to iterate through
    RGB_image = numpy.zeros((3,nuclei.shape[0],nuclei.shape[1]), dtype = numpy.int8) 

    #iterate through output array and assign values based on RGB settings
    for i,z in enumerate(RGB_image): #TODO: speed this up on GPU

        #allocate memory on GPU with background subtracted images and final output
        output_global = cuda.to_device(numpy.zeros(z.shape)) 
        nuclei_global = cuda.to_device(pre_nuc_output)
        cyto_global = cuda.to_device(pre_cyto_output)

        #get 8bit frame
        rapid_getRGBframe[blockspergrid,TPB](nuclei_global,cyto_global,output_global,
                                                nuc_settings[i],cyto_settings[i],
                                                k_nuclei, k_cyto)
        
        RGB_image[i] = output_global.copy_to_host()

    #reorder array to dimmensional form [X,Y,C]
    RGB_image = numpy.moveaxis(RGB_image,0,-1)
    return RGB_image.astype(numpy.uint8)


@cuda.jit #direct GPU compiling
def rapid_preProcess(image,background,norm_factor,output):
    """
    Background subtraction optimized for GPU, used by rapidFalseColor

    Parameters
    ----------

    image : 2d numpy array, dtype = int16
        image for background subtraction

    background : int
        constant for subtraction

    norm_factor : int
        empirically determaned constant for normalization after subtraction

    output : 2d numpy array
        numpy array of zeros for gpu to assign values to
    """

    #create iterator for gpu  
    row,col = cuda.grid(2)

    #cycle through image shape and assign values
    if row < output.shape[0] and col < output.shape[1]:

        #subtract background and raise to factor
        tmp = image[row,col] - background

        #remove negative values
        if tmp < 0:
            output[row,col] = 0

        #normalize to 8bit range
        else:
            tmp = (tmp**0.85)*(65535/norm_factor)*(255/65535)
            output[row,col] = tmp


@cuda.jit
def Convolve2d(image,kernel,output):
    """
    GPU based 2d convolution method

    Parameters
    ----------
    GPU accelerated 2D convolution 

    image : 2D numpy array
        Image for processing, written to GPU.

    kernel : 2D numpy array
        kernel to convolve image with, written to GPU

    output : 2D numpy array
        Output array, storing result of convolution, written to GPU.

    """

    #create iterator
    row,col = cuda.grid(2)
    
    image_rows,image_cols = image.shape
    
    delta_r = kernel.shape[0]//2
    delta_c = kernel.shape[1]//2
    
    #ignore rows/cols outside image
    if (row >= image_rows) or (col >= image_cols):
        return
    
    tmp = 0
    for i in range(kernel.shape[0]):
        for j in range(kernel.shape[1]):
            #result should be sum of kernel*image as kernel is varied
            row_i = row - i + delta_r
            col_j = col - j + delta_c
            if (row_i>=0) and (row_i < image_rows):
                if (col_j>=0) and (col_j < image_cols):
                    tmp += kernel[i,j]*image[row_i,col_j]
                    
    output[row,col] = tmp 


def sharpenImage(input_image,alpha = 0.5):
    """
    Image sharpening algorithm to amplify edges.

    Parameters
    ----------

    input_image : 2D numpy array
        Image to run sharpening algorithm on

    alpha : float or int
        Multiplicative constant for final result.

    Returns
    --------

    final_image : 2D numpy array
        The sum of the input image and the resulting convolutions
    """
    #create kernels to amplify edges
    hkernel = numpy.array([[1,1,1],[0,0,0],[-1,-1,-1]])
    vkernel = numpy.array([[1,0,-1],[1,0,-1],[1,0,-1]])

    #set grid/threads for GPU
    blocks = (32,32)
    grid = (input_image.shape[0]//blocks[0] + 1, input_image.shape[1]//blocks[1] + 1)

    #run convolution
    input_image = numpy.ascontiguousarray(input_image)
    voutput = numpy.zeros(input_image.shape,dtype=numpy.float64)
    houtput = numpy.zeros(input_image.shape,dtype=numpy.float64)
    Convolve2d[grid,blocks](input_image,vkernel,voutput)
    Convolve2d[grid,blocks](input_image,hkernel,houtput)

    #calculate final result
    final_image = input_image + 0.5*numpy.sqrt(voutput**2 + houtput**2)
    
    return final_image


def getDefaultRGBSettings():

    """returns empirically determined constants for nuclear/cyto channels

    Parameters
    ----------


    Returns
    -------
    settings_dict : dict
        Dictionary with keys 'nuclei', 'cyto' which correspond to lists containing empirically 
        derived RGB constants for false coloring.

    Note: these settings currently only optimized for flat field method in
    rapidFalseColor
    """
    k_cyto = 1.0
    k_nuclei = 0.85
    nuclei_RGBsettings = [0.25*k_nuclei, 0.37*k_nuclei, 0.1*k_nuclei]
    cyto_RGB_settings = [0.05*k_cyto, 1.0*k_cyto, 0.54*k_cyto]

    settings_dict = {'nuclei':nuclei_RGBsettings,'cyto':cyto_RGB_settings}
    return settings_dict


def falseColor(imageSet, output_dtype=numpy.uint8):
    """
    False coloring using Beer's law method based on:
    Giacomelli et al., PLOS one 2016 doi:10.1371/journal.pone.0159337.


    Parameters
    ----------
    imageSet : 3D numpy array
        dimmensions are [X,Y,C]
        for use with process images in FCdataobject

    channelIDs = list
        keys to grab settings from beta_dict
        defaults: s00 : nuclei
                  s01 : cyto

    output_dtype : numpy.uint8
        output datatype for final RGB image


    Returns
    -------
    RGB_image : numpy array
        Combined false colored image in the standard RGB format [X, Y, C]

    """
    beta_dict = {
                #constants for nuclear channel
                'K_nuclei' : 0.08,

                #constants for cytoplasmic channel
                'K_cyto' : 0.0120}

    #returns dictionary with settings for each channel
    #keys are: nuclei, cyto
    #entries are lists in order of RGB constants
    settings = getDefaultRGBSettings()

    nuclei = imageSet[:,:,0].astype(float)
    constants_nuclei = settings['nuclei']
    k_nuclei = beta_dict['K_nuclei']

    cyto = imageSet[:,:,1].astype(float)
    constants_cyto = settings['cyto']
    k_cytoplasm= beta_dict['K_cyto']
    
    #execute background subtraction
    nuc_threshold = getBackgroundLevels(nuclei)[1]
    nuclei = preProcess(nuclei, threshold = nuc_threshold)
    
    cyto_threshold = getBackgroundLevels(cyto)[1]
    cyto = preProcess(cyto, threshold = cyto_threshold)

    RGB_image = numpy.zeros((3,nuclei.shape[0],nuclei.shape[1]))

    #iterate throough RGB constants and execute image multiplication
    for i in range(len(RGB_image)):
        RGB_image[i] = 255*numpy.multiply(numpy.exp(-constants_cyto[i]*k_cytoplasm*cyto),
                                        numpy.exp(-constants_nuclei[i]*k_nuclei*nuclei))

    #reshape to [X,Y,C]
    RGB_image = numpy.moveaxis(RGB_image,0,-1)

    #rescale to 8bit range
    return RGB_image.astype(output_dtype)


def preProcess(image, threshold = 50):
    """
    Method used for background subtracting data with a fixed value

    Parameters
    ----------

    image : 2D numpy array
        image for processing

    threshold : int
        background level to subtract

    Returns
    -------

    processed_image : 2D numpy array
        Background subtracted image. 
    """

    #background subtraction
    image -= threshold

    #no negative values
    image[image < 0] = 0

    #calculate normalization factor
    image = numpy.power(image,0.85)
    image_mean = numpy.mean(image[image>threshold])*8

    #convert into 8bit range
    processed_image = image*(65535/image_mean)*(255/65535)

    return processed_image


def getBackgroundLevels(image, threshold = 50):
    """
    Calculate foreground and background values based on image statistics, background is currently
    set to be 20% of foreground

    Parameters
    ----------

    image : 2D numpy array

    threshold : int
        threshold above which is counted as foreground

    Returns
    -------

    hi_val : int
        Foreground values

    background : int
        Background value
    """

    image_DS = numpy.sort(image,axis=None)

    foreground_vals = image_DS[numpy.where(image_DS > threshold)]

    hi_val = foreground_vals[int(numpy.round(len(foreground_vals)*0.95))]

    background = hi_val/5

    return hi_val,background


def getFlatField(image,tileSize=256,blockSize = 16):

    """
    Returns downsampled flat field of image data and calculated background levels

    Parameters
    ----------

    image : 2D or 3D numpy array

    tileSize : int

    blockSize : int

    Returns
    -------

    flat_field : 2D numpy array
        Calculated flat field for input image

    background : float
        Background level for input image
    """

    midrange,background = getBackgroundLevels(image)
    
    rows_max = int(numpy.floor(image.shape[0]/blockSize)*blockSize)
    cols_max = int(numpy.floor(image.shape[2]/blockSize)*blockSize)
    stacks_max = int(numpy.floor(image.shape[1]/blockSize)*blockSize)


    rows = numpy.arange(0, rows_max+int(tileSize/blockSize), int(tileSize/blockSize))
    cols = numpy.arange(0, cols_max+int(tileSize/blockSize), int(tileSize/blockSize))
    stacks = numpy.arange(0, stacks_max+int(tileSize/blockSize), int(tileSize/blockSize))
    
    flat_field = numpy.zeros((len(rows)-1, len(stacks)-1, len(cols)-1), dtype = float)
    
    for i in range(1,len(rows)):
        for j in range(1,len(stacks)):
            for k in range(1,len(cols)):

                ROI_0 = image[rows[i-1]:rows[i], stacks[j-1]:stacks[j], cols[k-1]:cols[k]]
                
                fkg_ind = numpy.where(ROI_0 > background)
                if fkg_ind[0].size==0:
                    Mtemp = midrange
                else:
                    Mtemp = numpy.median(ROI_0[fkg_ind])
                flat_field[i-1, j-1, k-1] = Mtemp + flat_field[i-1, j-1, k-1]
    return flat_field, background/5


def interpolateDS(M_nuc, M_cyt, k, tileSize = 256):
    """
    Method for resizing downsampled data to be the same size as full res data. Used for 
    interpolating flat field images.

    Parameters
    ----------

    M_nuc : 2D numpy array
        Downsampled data from BigStitcher 

    M_cyt : 2D numpy array
        Downsampled data from BigStitcher

    k : int
        Index for image location in full res HDF5 file

    tileSize : int
        Default = 256, block size for interpolation

    Returns
    -------

    C_nuc : 2D numpy array
        Rescaled downsampled data

    C_cyt : 2D numpy array
        Rescaled downsampled data

    """

    x0 = numpy.floor(k/tileSize)
    x1 = numpy.ceil(k/tileSize)
    x = k/tileSize

    #get background block
    if k < int(M_nuc.shape[1]*tileSize-tileSize):
        if k < int(tileSize/2):
            C_nuc = M_nuc[:,0,:]
            C_cyt = M_cyt[:,0,:]

        elif x0==x1:
            C_nuc = M_nuc[:,int(x1),:]
            C_cyt = M_cyt[:,int(x1),:]
        else:
            nuc_norm0 = M_nuc[:,int(x0),:]
            nuc_norm1 = M_nuc[:,int(x1),:]

            cyto_norm0 = M_cyt[:,int(x0),:]
            cyto_norm1 = M_cyt[:,int(x1),:]

            C_nuc = nuc_norm0 + (x-x0)*(nuc_norm1 - nuc_norm0)/(x1-x0)
            C_cyt = cyto_norm0 + (x-x0)*(cyto_norm1 - cyto_norm0)/(x1-x0)
    else:
        C_nuc = M_nuc[:,M_nuc.shape[1]-1, :]
        C_cyt = M_cyt[:,M_cyt.shape[1]-1, :]

    print('interpolating')
    C_nuc = nd.interpolation.zoom(C_nuc, tileSize, order = 1, mode = 'nearest')

    C_cyt = nd.interpolation.zoom(C_cyt, tileSize, order = 1, mode = 'nearest')

    return C_nuc, C_cyt


def deconvolveColors(image):
    """
    Separates H&E channels from an RGB image using skimage.color.rgb2hed method

    Parameters
    ----------

    image : 3D numpy array
        RGB image in the format [X, Y, C] where the hematoxylin and eosin channels 
        are to be separted.

    Returns
    -------

    hematoxylin : 2D numpy array
        nuclear channel deconvolved from RGB image


    eosin : 2D numpy array
        cytoplasm channel deconvolved from RGB image

    """

    separated_image = rgb2hed(image)

    hematoxylin = separated_image[:,:,0]

    eosin = separated_image[:,:,1]

    return hematoxylin, eosin


def segmentNuclei(image, return3D = True, opening = False, radius = 3, min_size = 64):
    """
    
    Grabs binary mask of nuclei from H&E image using color deconvolution. 

    Parameters
    ----------

    image : 3D numpy array 
        H&E stained RGB image in the form [X, Y, C]

    return3D : bool, default = False
        Return 3D version of mask

    Returns
    -------

    binary_mask : 2D or 3D numpy array
        Binary mask of segmented nuclei

    """

    #separate channels
    nuclei, cyto = deconvolveColors(image)

    #median filter nuclei for optimized otsu threshold
    median_filtered_nuclei = filt.median(nuclei)

    #calculate threshold and create initial binary mask
    threshold = filt.threshold_otsu(median_filtered_nuclei)
    binarized_nuclei = (median_filtered_nuclei > threshold).astype(int)

    #remove small objects
    labeled_mask = morph.label(binarized_nuclei)
    shape_filtered_mask = morph.remove_small_objects(labeled_mask, min_size = min_size)

    if opening:
        shape_filtered_mask = morph.binary_opening(shape_filtered_mask, morph.disk(radius))

    #create final mask and return object
    if return3D:

        binary_mask = numpy.ones(image.shape, dtype = int)

        for i in range(binary_mask.shape[-1]):

            binary_mask[:,:,i] *= (shape_filtered_mask > 0).astype(int)

        #return 3D array
        return binary_mask

    else:

        binary_mask = (shape_filtered_mask > 0).astype(int)

        #return 2D array
        return binary_mask


def maskEmpty(image_RGB, mask_val = 0.05, return3D = True, min_size = 150):

    """
    Method to remove white areas from RGB histology image.

    Parameters
    ----------

    image_RGB : 3D numpy array
        RGB image in the form [X, Y, C]

    mask_val : float:
        Value over which pixels will be masked out of hsv image in value space
    """

    hsv = rgb2hsv(image_RGB)

    binary_mask = (hsv[:,:,1] < mask_val).astype(int)

    labeled_mask = morph.label(binary_mask)

    labeled_mask = morph.remove_small_objects(labeled_mask, min_size =  min_size)

    labeled_mask = morph.remove_small_holes(labeled_mask)

    empty_mask = (labeled_mask < 1).astype(int)

    if return3D:
        empty_mask_3D = numpy.ones(image_RGB.shape, dtype = int)

        for i in range(empty_mask_3D.shape[-1]):
            empty_mask_3D[:,:,i] *= empty_mask

        return empty_mask_3D

    else:

        return empty_mask


def singleChannel_falseColor(input_image, channelID = 's0', output_dtype = numpy.uint8):
    """depreciated
    single channel false coloring based on:
        Giacomelli et al., PLOS one 2016 doi:10.1371/journal.pone.0159337
    """
    
    beta_dict = {
                #nuclear consants
                's00' : {'K' : 0.017,
                             'R' : 0.544,
                             'G' : 1.000,
                             'B' : 0.050,
                             'thresh' : 50},
                             
                #cytoplasmic constants               
                's01' : {'K' : 0.008,
                              'R' : 0.300,
                              'G' : 1.000,
                              'B' : 0.860,
                              'thresh' : 500}}
                
    constants = beta_dict[channelID]
    
    RGB_image = numpy.zeros((input_image.shape[0],input_image.shape[1],3))
    
    #execute background subtraction
    input_image = preProcess(input_image,channelID)
    
    #assign RGB values
    R = numpy.exp(-constants['K']*constants['R']*input_image)
    G = numpy.exp(-constants['K']*constants['G']*input_image)
    B = numpy.exp(-constants['K']*constants['B']*input_image)
    
    #rescale to 8bit range
    RGB_image[:,:,0] = R*255
    RGB_image[:,:,1] = G*255
    RGB_image[:,:,2] = B*255
    
    return RGB_image.astype(output_dtype)


def combineFalseColoredChannels(nuclei, cyto, norm_factor = 255, output_dtype = numpy.uint8):
    """depreciated
    Use for combining false colored channels after single channel false color method
    """
    
    assert(cyto.shape == nuclei.shape)
 
    RGB_image = numpy.multiply(cyto/norm_factor,nuclei/norm_factor)
    RGB_image = numpy.multiply(RGB_image,norm_factor)
    
    return RGB_image.astype(output_dtype)
