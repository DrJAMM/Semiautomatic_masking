# Semiautomatic masking

Semi automatic mask of large datasets. It only requires to draw an ROI every other slice and the code will interpolate i. The shapes around the drawn ROIS. Data is loaded from a mat file with DCM_mag or a DICOM folder. 
ii. The accuracy of the mask depends on how many slices wants to be drawn. less drwan, less accurate. 
ii. export can be mat or nifti.  

## Notes: 
DICOM folder: one series, one image type (magnitude only, not magnitude + phase); the NIfTI gets the DICOM orientation. From a NIfTI input it keeps that file's orientation; from a .mat it only has the voxel sizes.

## Run from Python
    pip install -r utils/requirements.txt
    python utils/Semiautomatic_masking.py

