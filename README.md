# FalseColor Python

Python module for H&E pseudo coloring for greyscale fluorescent images of datasets with nuclear and cytoplasmic staining. False coloring methods is based on: [Giacomelli et al.](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0159337)


## Installation

In order to use FalseColor Python's GPU acceleration install cudatoolkit using conda:
```bash
conda install cudatoolkit
```

FalseColor Python can be installed using pip:

```bash
pip install FalseColor
```

Or by running setup.py install while in the working directory.

```bash
python setup.py install
```


## Usage
See Examples to get started.

Several methods within Color.py are setup with GPU acceleration using numba.cuda.jit:
(See Example/GPU examples.ipynb)

#Set color levels for false coloring using background subtraction
```python
#Using Defaults:
settings_dict = fc.getDefaultRGBsettings()
nuclei_RGBsettings = settings_dict['nuclei']
cyto_RGBsettings = settings_dict['cyto']
```

```python
#Or Levels can be set manually, provided they are in the following order
nuclei_RGBsettings = [R,G,B] # list of floats (0.0:1.0) for color levels in nuclear channel
cyto_RGBsettings = [R,G,B] # list of floats (0.0:1.0) for color levels in cyto channel

#nuclei,cyto are 2D numpy arrays for false coloring see GPU example.ipynb for more details
pseudo_colored_data = fc.rapidFalseColor(nuclei,cyto,
                                         nuclei_RGBsettings,cyto_RGBsettings)
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

## License 
GNU Affero General Public License v3.0

Copyright (c) 2019 Rob Serafin, Liu Lab, 
The University of Washington Department of Mechanical Engineering 
 
  License: GPL
 
  This program is free software; you can redistribute it and/or
  modify it under the terms of the GNU General Public License 2
  as published by the Free Software Foundation.
 
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
 
   You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
 
