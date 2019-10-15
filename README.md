# falseColoring

Python module for H&E pseudo coloring for greyscale fluorescent images of datasets with nuclear and cytoplasmic staining. False coloring methods is based on: [Giacomelli et al.](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0159337)


## Installation

Run setup.py install while in the working directory.

```bash
python setup.py install
```


## Usage

```python
from FalseColor.FCdataobject import DataObject
import FalseColor.Color as fc
```
For CPU batch processing load data into DataObject:
(See Example/example notebook.ipynb)
```python
data_path = 'path/to/data' #contains .h5 file
dataSet = DataObject(data_path)

#zips data into imageSet property of Dataobject 
#imageSet will be a 4D array of images with [Z,X,Y,C]
Dataset.setupH5data() 
```
Batch process data using DataObjects processImages method:
```python
#method and kwargs are put into a dictionary
runnable_dict = {'runnable' : fc.falseColor, 'kwargs' : None}

#runnable_dict and desired images are passed into processImages method
pseudo_colored_data = Dataset.processImages(runnable_dict, Dataset.imageSet)

```

Several methods within Color.py are setup with GPU acceleration using numba.cuda.jit:
(See Example/GPU examples.ipynb)

```python
#set color levels for false coloring using background subtraction
nuclei_RGBsettings = [R,G,B] # list of floats (0.0:1.0) for color levels in nuclear channel
cyto_RGBsettings = [R,G,B] # list of floats (0.0:1.0) for color levels in cyto channel

#nuclei,cyto are 2D numpy arrays for false coloring see GPU example.ipynb for more details
pseudo_colored_data = fc.rapidFalseColor(nuclei,cyto,nuclei_RGBsettings,cyto_RGBsettings, run_normalization=False)
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## Liscence 
MIT License

Copyright (c) [2019] [Robert Serafin]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
