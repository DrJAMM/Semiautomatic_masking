
#%% IMPORT MODULES
import os
import sys
######
# SETTING UP ENVIRONMEBT
PYTHON = '/Users/jam48/miniforge3/envs/spydervaug25/bin/python3'
if not getattr(sys, 'frozen', False) and os.path.realpath(sys.executable) != os.path.realpath(PYTHON):      # (not in the packaged app)
    os.execv(PYTHON, [PYTHON] + sys.argv)      # relaunch in the right env
######
import re
import textwrap
import traceback
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.widgets import PolygonSelector, Button, RadioButtons, TextBox
from scipy.io import loadmat, savemat
from scipy.ndimage import distance_transform_edt
import contourpy
import pydicom
import nibabel as nib

#%% INITIALIZING LOCATION AND FILE
MAT = None                  
DATA_DIR = os.path.expanduser('~')      # where the file dialog starts

VAR = 'Dcm_mag'             # SEGMENTATION OCCURS IN THIS DATA VARIABLE 
NPTS = 30                   # NUMBER OF POINTS IN THE INTERPOLATED DATA TO BE MODIFIED IF NEEDED
'''
ESTIMATION OF NUMBER OF MANUAL NUMBER OF SLICES DRAWN: 
n: number of slices or keyframes drawn 
N: Range of slices selected where we want to place our ROIs
dz: slice thickness/ spacing between slices
tol: accuracy of the interpolation. low--> less slices to draw. high--> more slices to draw.
n= 1+ sqrt((N·dz)/(4· tol))
'''
TOL = {'Low': 2.0, 'Medium': 1.0, 'High': 0.5} 

###### GUI
BG = '#42433A'       # window background
TXT = 'lightgreen'   # colour of the text
#three viewer grid in GUI
GRID = [[0.01, 0.55, 0.31, 0.41], [0.34, 0.55, 0.31, 0.41], [0.01, 0.09, 0.31, 0.41]] 
# two views grid once the selected view is applied (appears in red)
SIDE = [[0.49, 0.55, 0.16, 0.41], [0.49, 0.09, 0.16, 0.41]]   
HELP = {'range': '1. scroll to find the organ *type the name*, \n\n 2. click the view where you want to draw segment\n(turns red),\n\n 3. scroll to select first and last slice where the \n  organ is seen (Set first and last slice)\n\n 4. Click on Start drawing' ,
        'draw': 'outline the organ on the red box (drag points to adjust, Esc restarts)\nempty = organ absent in this slice, then Next keyframe',
        'edit': 'scroll = slice | drag the red (keyframe) or orange (interpolated) points\nd = delete this keyframe'}
######

#%% FUNCTIONS

# makes a mask out of the drawn ROI (verts)
def sdf_of(verts, shape):
    if verts is None:
        return np.full(shape, -float(max(shape))) # no organ visible in this slice, no roi there
    xx, yy = np.meshgrid(np.arange(shape[1]), np.arange(shape[0])) #voxel coordinates

    m = Path(verts).contains_points(np.column_stack([xx.ravel(), yy.ravel()])).reshape(shape) #closes shape and masks
    return distance_transform_edt(m) - distance_transform_edt(~m)


# interpolation between the manually drawn slices
# mask: volume of slices where the organ is 
# polys: ROIs drawn by user
# sdl calculated from sdf_of, helps us understand where the edges are
# sl: active slice drawn, 

def refill(mask, polys, sdf, sl):
    prev = max([k for k in polys if k < sl], default=None) #previous slice drawn
    nxt = min([k for k in polys if k > sl], default=None) #following slice drawn 
    mask[:, sl if prev is None else prev:(sl if nxt is None else nxt) + 1] = False
    ks = [k for k in (prev, sl, nxt) if k is not None and (k != sl or sl in polys)] #number of slices where we need to interpolate the mask 
    for a, b in zip(ks[:-1], ks[1:]): #a,b neighbor slice,
        for s in range(a + 1, b): # slice between a and b
            mask[:, s] = (b - s) / (b - a) * sdf[a] + (s - a) / (b - a) * sdf[b] > 0 # blend of the mask, closer to the drawn slice, more weight 
    for k in ks:
        mask[:, k] = sdf[k] > 0


# number of keyframes  or slices that the interpolation will occur following the tol .
# This is a linear interpolation of its edge between keyframes

def keyframes(first, last, level, dz):
    N = last - first + 1
    n = min(max(int(np.ceil(1 + np.sqrt(N * dz / (4 * TOL[level])))), 3), N)
    return sorted(set(np.linspace(first, last, n).round().astype(int).tolist()))

#the outline interpolated and gets points in the slice if user wants to modify it 
def outline(m, n):     
    lines = contourpy.contour_generator(z=np.pad(m.astype(float), 1)).lines(0.5)
    if not lines:
        return None
    line = max(lines, key=len)[:-1] - 1
    return line[np.linspace(0, len(line) - 1, n, endpoint=False).astype(int)]

# file (.mat / nifti) or folder (dicom) dialog; works on mac, windows, etc
def pick_file(start, folder=False):       # returns '' if cancelled
    import subprocess
    title = 'Select the DICOM folder' if folder else 'Select the .mat or NIfTI to segment'
    if sys.platform == 'darwin':        # native dialog (Tk crashes the app on recent macOS)
        cmd = ['osascript', '-e', f'POSIX path of (choose {"folder" if folder else "file"} with prompt "{title}" default location POSIX file "{start}"' + ('' if folder else ' of type {"mat", "nii", "gz"}') + ')']
    else:
        ask = f"d.askdirectory(initialdir={start!r}, title={title!r})" if folder else f"d.askopenfilename(initialdir={start!r}, title={title!r}, filetypes=[('MAT or NIfTI', '*.mat *.nii *.nii.gz')])"
        if getattr(sys, 'frozen', False):     # packaged app: sys.executable is the app itself, so open the Tk dialog directly
            import tkinter, tkinter.filedialog as d
            tkinter.Tk().withdraw()
            return eval(ask)
        # Tk dialog in its own process, so it cannot clash with the matplotlib window
        cmd = [sys.executable, '-c', f"import tkinter, tkinter.filedialog as d; tkinter.Tk().withdraw(); print({ask})"]
    return subprocess.run(cmd, capture_output=True, text=True).stdout.strip()


# dicom folder -> volume [rows, cols, slices], mm per voxel [row, col, slice] and the affine (RAS) used to save the nifti mask
# one series (the largest in the folder), slices sorted by position; one image type per series (no magnitude + phase mixed)
def load_dicom(folder):
    heads = {}
    for r, _, fs in os.walk(folder):
        for f in fs:
            try:
                h = pydicom.dcmread(os.path.join(r, f), stop_before_pixels=True)
                if 'ImagePositionPatient' in h and 'Rows' in h:
                    heads.setdefault(h.SeriesInstanceUID, []).append((os.path.join(r, f), h))
            except Exception:
                pass            # not a dicom
    if not heads:
        raise ValueError('no DICOM images found')
    series = max(heads.values(), key=len)
    h0 = series[0][1]
    row, col = np.array(h0.ImageOrientationPatient[:3], float), np.array(h0.ImageOrientationPatient[3:], float)      # direction of increasing column / row index
    n = np.cross(row, col)
    series.sort(key=lambda x: np.dot(np.array(x[1].ImagePositionPatient, float), n))
    pos = np.array([x[1].ImagePositionPatient for x in series], float)
    if len(np.unique(np.round(pos @ n, 3))) < len(series):
        raise ValueError('repeated slice positions: the folder mixes echoes / magnitude + phase, load one image type only')
    vol = np.stack([pydicom.dcmread(f).pixel_array * float(getattr(h, 'RescaleSlope', 1)) + float(getattr(h, 'RescaleIntercept', 0)) for f, h in series], axis=2)
    step = (pos[-1] - pos[0]) / (len(series) - 1) if len(series) > 1 else n * float(h0.SliceThickness)
    dr, dc = (float(v) for v in h0.PixelSpacing)         # row spacing, column spacing
    lps = np.column_stack([col * dr, row * dc, step, pos[0]])         # voxel (row, col, slice) -> patient LPS
    affine = np.diag([-1.0, -1.0, 1.0]) @ lps
    return vol, [dr, dc, float(np.linalg.norm(step))], np.vstack([affine, [0, 0, 0, 1]])


#%% GUI 
##################
class App:
    def __init__(self):
        self.mode, self.level, self.mag3, self.axs, self.sel, self.drag, self.shown = 'range', 'Medium', None, [], None, None, None
        self.a = self.first = self.last = None
        self.dir = os.path.dirname(MAT) if MAT else DATA_DIR
        for k in [k for k in plt.rcParams if k.startswith('keymap.')]:
            plt.rcParams[k] = []            # default shortcuts (s, k, l, q...) clash with typing in the name box
        self.fig = plt.figure(figsize=(13, 7), facecolor=BG)
        try:        # on mac matplotlib swaps the Dock icon for its own logo when the window opens: put ours back
            from matplotlib.backends import _macosx
            _macosx.FigureManager.set_icon(os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'icon.png'))
        except Exception:
            pass
        f = self.fig
        f.canvas.callbacks.exception_handler = lambda exc: (traceback.print_exception(exc), self.say(f'error: {type(exc).__name__}: {exc}', 'red'))      # errors inside the window are shown in red
        self.fname = f.text(0.72, 0.99, '', va='top', fontsize=9, color=TXT)
        self.acc_t = f.text(0.72, 0.84, 'Accuracy', fontsize=10, fontweight='bold', color=TXT)
        self.info = f.text(0.72, 0.70, '', va='top', fontsize=9, color=TXT)
        self.msgs = []          # message area: one text per line (a leading '1.' can have its own colour)
        self.tb = TextBox(f.add_axes([0.78, 0.865, 0.20, 0.04]), 'organ  ', initial='brain')
        self.tb.label.set(fontweight='bold', color=TXT)
        self.radio = RadioButtons(f.add_axes([0.72, 0.72, 0.26, 0.11]), list(TOL), active=1, activecolor='yellow', label_props={'color': [TXT] * 3}, radio_props={'edgecolor': 'w', 's': 90})
        self.radio.ax.set_facecolor(BG)
        self.radio.on_clicked(lambda lab: (setattr(self, 'level', lab), self.update()))
        self.fmt, self.fmt_t = 'MAT', f.text(0.72, 0.84, 'Save as', fontsize=10, fontweight='bold', color=TXT)       # same place as Accuracy, other step
        self.fmt_radio = RadioButtons(f.add_axes([0.72, 0.72, 0.26, 0.11]), ['MAT', 'NIfTI'], active=0, activecolor='yellow', label_props={'color': [TXT] * 2}, radio_props={'edgecolor': 'w', 's': 90})
        self.fmt_radio.ax.set_facecolor(BG)
        self.fmt_radio.on_clicked(lambda lab: setattr(self, 'fmt', lab))

        def btn(label, rect, cb, modes):
            b = Button(f.add_axes(rect), label)
            b.on_clicked(cb)
            return b, modes
        self.w = [(self.tb, ('range', 'edit')), (self.radio, ('range',)), (self.fmt_radio, ('edit',)),
                  btn('Set first slice', [0.72, 0.50, 0.12, 0.05], lambda e: self.mark('first'), ('range',)),
                  btn('Set last slice', [0.86, 0.50, 0.12, 0.05], lambda e: self.mark('last'), ('range',)),
                  btn('Start drawing', [0.72, 0.43, 0.26, 0.05], self.start, ('range',)),
                  btn('Search .mat/.nii', [0.72, 0.92, 0.125, 0.045], lambda e: self.load(pick_file(self.dir)), ('range',)),
                  btn('Load DICOMs', [0.855, 0.92, 0.125, 0.045], lambda e: self.load(pick_file(self.dir, True)), ('range',)),
                  btn('Next keyframe', [0.72, 0.50, 0.26, 0.05], self.next, ('draw',)),
                  btn('Clear polygon', [0.72, 0.43, 0.26, 0.05], lambda e: self.draw_slice(), ('draw',)),
                  btn('Finish organ (save)', [0.72, 0.50, 0.26, 0.05], self.finish, ('edit',)),
                  btn('Segment another organ', [0.72, 0.43, 0.26, 0.05], self.new, ('edit',)),
                  btn('Go to first slice', [0.01, 0.015, 0.20, 0.05], lambda e: self.go('first'), ('range', 'edit')),       # under the viewers
                  btn('Go to center slice', [0.235, 0.015, 0.20, 0.05], lambda e: self.go('center'), ('range', 'edit')),
                  btn('Go to last slice', [0.46, 0.015, 0.19, 0.05], lambda e: self.go('last'), ('range', 'edit')),
                  btn('Exit', [0.72, 0.03, 0.26, 0.05], self.exit, ('range', 'draw', 'edit'))]      # keep the references or the buttons die
        for ev, fn in [('scroll_event', self.scroll), ('button_press_event', self.press), ('motion_notify_event', self.move),
                       ('button_release_event', self.release), ('key_press_event', self.key)]:
            f.canvas.mpl_connect(ev, fn)
        self.show('range')
        if MAT:
            self.load(MAT)
        else:
            self.say("0. Press 'Search .mat/.nii' (a .mat needs the magnitude saved as 'Dcm_mag') or 'Load DICOMs' (a folder with one image type) to start.", 'lightgreen', 'deepskyblue')

    def say(self, text, color=TXT, num=None):       # num = colour of the leading '1.' of each line (None = same as the text)
        for t in self.msgs:
            t.remove()
        self.msgs, y = [], 0.38
        ind = 0.025 * bool(re.search(r'^\s*\d+\.', text, re.M))        # indent of the text when the lines are numbered
        for line in text.split('\n'):
            n, rest = re.match(r'\s*(\d+\.)?\s*(.*)', line).groups()
            hi, rest = rest.startswith('§'), rest.lstrip('§')        # a line starting with § is written in blue and bold
            for k, part in enumerate(textwrap.wrap(rest, 50 - int(ind * 100)) or ['']):        # long lines are wrapped to fit the panel
                if n and k == 0:
                    self.msgs.append(self.fig.text(0.72, y, n, va='top', fontsize=9, color=num or color))
                self.msgs.append(self.fig.text(0.72 + ind, y, part, va='top', fontsize=9, color='deepskyblue' if hi else color, fontweight='bold' if hi else 'normal'))
                y -= 0.026
        self.fig.canvas.draw_idle()

    def load(self, path):       # a .mat, a nifti or a dicom folder
        if not path:
            return
        path = path.rstrip('/\\')
        try:
            if os.path.isdir(path):
                mag3, vox, affine = load_dicom(path)
                out = os.path.join(os.path.dirname(path), 'mask')       # <subject>/mask
            elif path.endswith(('.nii', '.nii.gz')):
                img = nib.load(path)
                mag3 = np.asarray(img.dataobj, float)
                if mag3.ndim == 4:
                    mag3 = mag3[..., 0]         # first volume of a 4D file
                if mag3.ndim != 3:
                    return self.say(f'{os.path.basename(path)} is not a 3D image')
                vox, affine = [float(v) for v in img.header.get_zooms()[:3]], img.affine
                out = os.path.join(os.path.dirname(os.path.dirname(path)), 'mask')       # <subject>/mask
            else:
                m = loadmat(path, variable_names=[VAR, 'Resolution', 'minSlice', 'maxSlice'])
                if np.ndim(m.get(VAR, 0)) != 3:
                    return self.say(f'no 3D {VAR} in {os.path.basename(path)}')
                mag3, vox = np.asarray(m[VAR], float), [1.0] * 3            # vox: mm per voxel along D0, D1, D2
                if 'Resolution' in m and 'minSlice' in m:
                    vox = [m['Resolution'].ravel()[0]] * 2 + [(m['maxSlice'].item() - m['minSlice'].item()) / (mag3.shape[2] - 1)]
                affine = np.diag(vox + [1.0])
                out = os.path.join(os.path.dirname(os.path.dirname(path)), 'mask')       # <subject>/mask
        except Exception as e:
            return self.say(f'could not load: {e}')
        self.path, self.dir, self.mag3, self.vox, self.affine, self.out = path, os.path.dirname(path), mag3, vox, affine, out
        os.makedirs(out, exist_ok=True)
        self.file = os.path.join(out, 'organ_masks.mat')            # one '<name>_mask' (+ keyframes) per organ; organs from earlier runs are kept
        self.data = {k: v for k, v in loadmat(self.file).items() if not k.startswith('__')} if os.path.exists(self.file) else {}
        self.mask3, self.polys, self.sdf = np.zeros(self.mag3.shape, bool), {}, {}      # polys: keyframe slice -> (n, 2) x, y (None = absent)
        self.a = self.first = self.last = None
        self.pos = [s // 2 for s in self.mag3.shape]            # crosshair = current slice of each box
        self.rc = [[x for x in range(3) if x != a] for a in range(3)]         # (row axis, column axis) of each box
        for ax in self.axs:
            ax.remove()
        self.axs, self.ims, self.ovs, self.lines, self.hl, self.vl = [], [], [], [], [], []
        for a in range(3):
            asp = self.vox[self.rc[a][0]] / self.vox[self.rc[a][1]]
            ax = self.fig.add_axes(GRID[a])
            self.ims.append(ax.imshow(np.take(self.mag3, self.pos[a], axis=a), cmap='gray', aspect=asp))
            self.ovs.append(ax.imshow(np.ma.masked_all(np.delete(self.mag3.shape, a)), cmap='Reds', vmin=0, vmax=1.5, alpha=0.35, aspect=asp))
            self.hl.append(ax.axhline(0, color='y', lw=0.7))
            self.vl.append(ax.axvline(0, color='y', lw=0.7))
            self.lines.append(ax.plot([], [], 'r-o', ms=4, lw=1)[0])
            ax.set(xticks=[], yticks=[])
            ax.set_autoscale_on(False)
            self.axs.append(ax)
        self.fname.set_text('file: ' + os.path.basename(path))
        self.fmt_radio.set_active(0 if self.path.endswith('.mat') else 1)           # dicom / nifti in -> nifti out (can be changed in the last step)
        self.tb.set_val('brain')
        self.show('range')

    def show(self, mode):       # widgets / layout / help of each mode
        self.mode, self.warned, side = mode, False, iter(SIDE)
        for w, modes in self.w:
            w.ax.set_visible(mode in modes)
            w.active = mode in modes
        for t in (self.acc_t, self.info):
            t.set_visible(mode == 'range')
        self.fmt_t.set_visible(mode == 'edit')
        for a, ax in enumerate(self.axs):
            ax.set_position(GRID[a] if mode == 'range' else [0.01, 0.09, 0.46, 0.87] if a == self.a else next(side))
        self.say(HELP[mode], 'lightgreen', 'deepskyblue')
        self.update()

    def update(self):
        ks = keyframes(self.first, self.last, self.level, self.vox[self.a]) if self.a is not None and None not in (self.first, self.last) and self.last > self.first else []
        self.info.set_text(f'first {self.first}, last {self.last}' + (f'\n{len(ks)} keyframes, one every {(self.last - self.first) / (len(ks) - 1) * self.vox[self.a]:.1f} mm\nedge error <= {TOL[self.level]} mm' if ks else ''))
        for a, ax in enumerate(self.axs):
            i, (r, c) = self.pos[a], self.rc[a]
            pl, ml = np.take(self.mag3, i, axis=a), np.take(self.mask3, i, axis=a)
            self.ims[a].set_data(pl)
            self.ims[a].set_clim(0, np.percentile(pl, 99.5))
            self.ovs[a].set_data(np.ma.masked_where(~ml, ml))
            self.hl[a].set_ydata([self.pos[r]] * 2)
            self.vl[a].set_xdata([self.pos[c]] * 2)
            for sp in ax.spines.values():
                sp.set(edgecolor='red' if a == self.a else '0.6', linewidth=3 if a == self.a else 0.8)
            v, tag = None, ''
            if a == self.a and self.mode == 'range':
                tag = ' [first]' * (i == self.first) + ' [last]' * (i == self.last)
            elif a == self.a and self.mode == 'draw':
                tag = f' keyframe {self.k + 1}/{len(self.keys)}'
            elif a == self.a:                       # edit: keyframe polygon (red) or outline of the interpolated slice (orange)
                v = self.polys.get(i)
                self.shown = outline(ml, NPTS) if v is None else v
                v, tag = self.shown, ' [KEYFRAME]' if i in self.polys else ' [interpolated]'
                self.lines[a].set_color('red' if i in self.polys else 'orange')
            self.lines[a].set_data(*(np.vstack([v, v[:1]]).T if v is not None else ([], [])))
            ax.set_title(f'D{a}: slice {i}' + tag, fontsize=9, color=TXT)
        self.fig.canvas.draw_idle()

    def mark(self, which):
        if self.a is None:
            return self.say('click the box you want to segment in first')
        setattr(self, which, self.pos[self.a])
        if None not in (self.first, self.last) and self.first > self.last:        # marked in the other order: swap them
            self.first, self.last = self.last, self.first
        self.update()

    def go(self, which):       # jump the red box to the first / center / last slice (the whole volume until they are set)
        if self.a is None:
            return self.say('click the box you want to segment in first')
        lo, hi = 0 if self.first is None else self.first, self.mag3.shape[self.a] - 1 if self.last is None else self.last
        self.pos[self.a] = {'first': lo, 'center': (lo + hi) // 2, 'last': hi}[which]
        self.update()

    def start(self, e):
        if self.a is None:
            return self.say('click the box you want to segment in first (it turns red)', 'tomato')
        if None in (self.first, self.last):
            return self.say('press Set first slice and Set last slice first', 'tomato')
        if self.first == self.last:
            return self.say('the first and the last slice are the same: pick two different slices', 'tomato')
        self.mask3[:] = False
        self.polys.clear()
        self.sdf.clear()
        self.keys, self.k, self.done = keyframes(self.first, self.last, self.level, self.vox[self.a]), 0, False
        self.show('draw')
        self.draw_slice()

    def draw_slice(self):       # (re)start the polygon of keyframe k
        if self.sel:
            self.sel.set_visible(False)
            self.sel.disconnect_events()
        self.pos[self.a] = self.keys[self.k]
        self.sel = PolygonSelector(self.axs[self.a], lambda v: None, useblit=False, props=dict(color='yellow', linewidth=2), handle_props=dict(markerfacecolor='red', markeredgecolor='red', markersize=7))
        self.update()

    def next(self, e):
        i, v = self.keys[self.k], self.sel.verts
        self.polys[i] = np.array(v, float) if len(v) >= 3 else None
        self.sdf[i] = sdf_of(self.polys[i], self.mask.shape[::2])
        self.k += 1
        if self.k < len(self.keys):
            return self.draw_slice()
        self.sel.set_visible(False)
        self.sel.disconnect_events()
        self.sel = None
        for s in self.keys[:-1]:
            refill(self.mask, self.polys, self.sdf, s)           # fills the segment up to the next keyframe
        self.pos[self.a] = self.keys[0]
        self.show('edit')

    def commit(self):       # after a keyframe changed: re-interpolate around it
        i = self.pos[self.a]
        if i in self.polys:
            self.sdf[i] = sdf_of(self.polys[i], self.mask.shape[::2])
        else:
            self.sdf.pop(i, None)
        refill(self.mask, self.polys, self.sdf, i)
        self.done = False
        self.update()

    def scroll(self, e):
        if e.inaxes in self.axs and self.mode != 'draw':
            a = self.axs.index(e.inaxes)
            step = 1 if e.button == 'up' else -1
            if self.mode == 'edit' and a == self.a:         # the red box loops between the first and the last slice
                self.pos[a] = self.first + (self.pos[a] + step - self.first) % (self.last - self.first + 1)
            else:
                self.pos[a] = int(np.clip(self.pos[a] + step, 0, self.mag3.shape[a] - 1))
            self.update()

    def press(self, e):
        if e.inaxes not in self.axs or e.button != 1:
            return
        a = self.axs.index(e.inaxes)
        if self.mode == 'range':        # click = choose this box as the working view + move the crosshair
            if a != self.a:
                self.a, self.first, self.last = a, None, None
                self.mask = np.moveaxis(self.mask3, a, 1)       # view: the slice axis in position 1, writes through to mask3
            r, c = self.rc[a]
            self.pos[r], self.pos[c] = np.clip([round(e.ydata), round(e.xdata)], 0, [self.mag3.shape[r] - 1, self.mag3.shape[c] - 1]).tolist()
            self.update()
        elif self.mode == 'edit' and a == self.a and self.shown is not None:
            d = np.hypot(*(e.inaxes.transData.transform(self.shown) - [e.x, e.y]).T)
            if d.min() < 10:
                i = self.pos[a]
                if self.polys.get(i) is None:           # dragging a point of an interpolated slice makes it a keyframe
                    self.polys[i] = self.shown.copy()
                self.shown, self.drag = self.polys[i], d.argmin()

    def move(self, e):
        if self.drag is not None and e.inaxes is self.axs[self.a]:
            self.shown[self.drag] = [e.xdata, e.ydata]
            self.lines[self.a].set_data(*np.vstack([self.shown, self.shown[:1]]).T)
            self.fig.canvas.draw_idle()

    def release(self, e):
        if self.drag is not None:
            self.drag = None
            self.commit()

    def key(self, e):
        if self.mode == 'edit' and not self.tb.capturekeystrokes and e.key == 'd' and self.pos[self.a] in self.polys and len(self.polys) > 1:
            del self.polys[self.pos[self.a]]
            self.commit()

    def finish(self, e):
        name = re.sub(r'\W+', '_', self.tb.text.strip())
        if not name:
            return self.say('type an organ name first')
        f, msg = self.file, ''
        if self.fmt == 'NIfTI':     # one separate file per organ, named with the given name
            f = os.path.join(self.out, f'{name}.nii.gz')
            nib.save(nib.Nifti1Image(self.mask3.astype('uint8'), self.affine), f)
        else:
            self.data.update({f'{name}_mask': self.mask3.astype('uint8'), f'{name}_keyframes': np.array(sorted(self.polys)), f'{name}_view': self.a})
            savemat(self.file, self.data, do_compression=True)
        self.done = True
        self.say(f'saved "{name}"\n§format: {self.fmt}\n§folder:\n' + '\n'.join('§' + l for l in textwrap.wrap(os.path.dirname(f), 40)) + f'\n§file: {os.path.basename(f)}' + msg)

    def new(self, e):
        if not self.done:
            return self.say('press Finish organ (save) first')
        self.mask3[:] = False
        self.polys.clear()
        self.sdf.clear()
        self.a = self.first = self.last = None
        self.tb.set_val('')
        self.show('range')

    def exit(self, e):
        if self.mode == 'edit' and not self.done and not self.warned:
            self.warned = True
            return self.say('this organ is not saved: press Exit again to discard it')
        plt.close(self.fig)


######### Run GUI
app = App()
plt.show()
########