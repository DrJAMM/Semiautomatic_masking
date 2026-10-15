# Semiautomatic masking

1. It only requires drawing an ROI every few slices, and the code will interpolate the other slices.  
   Data is loaded from a `.mat` *file with the array saved as `Dcm_mag`*, a DICOM folder, or a NIfTI.
2. The accuracy of the mask depends on how many slices you want to draw: fewer drawn, less accurate.  
   If an interpolated ROI does not follow the structure properly, you can move the dots to match it better.
3. Export can be `.mat` or NIfTI.

# Download the executable here:
- [Windows](https://github.com/DrJAMM/Semiautomatic_masking_App/releases/download/v1.0.1/Semiautomatic_masking_windows.zip)
- [Mac](https://github.com/DrJAMM/Semiautomatic_masking_App/releases/download/v1.0.1/Semiautomatic_masking_mac.zip)
  * *if Mac blocks app, go to: System Settings → Privacy & Security and scroll down to Security to grant access*


## Cite
If used please cite: Martinez, J.A. (2026). *Semiautomatic masking*. Zenodo. https://doi.org/10.5281/zenodo.23401492

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23401492.svg)](https://doi.org/10.5281/zenodo.23401492)
