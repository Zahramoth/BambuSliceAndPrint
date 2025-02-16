# BambuSliceAndPrint
python script for slicing a 3mf and sending it to your bambu printer with the command line

## requierements 
    - Orca-slicer
    - specific user changes to config.json

## restrictions
    - only tested on windows
    - not all printer settings are working
    - tested with p1s
    - only lan-mode supported
    - only 3mf files and must be in same folder as SliceAndPrint.py

## usage 
- edit config.json
- add your printer to json from  "C:\Users\USER\AppData\Roaming\OrcaSlicer\system\BBL\machine" to settings folder and
add to config.json
- eddit SliceAndPrint.py input_3mf with your 3mf file
- enter python SliceAndPrint.py in command line
- monitor your print carefully
- don't blame me if anything goes sideways ;)
-