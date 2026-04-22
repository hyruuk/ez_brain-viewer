# brain_viewer

Figure-ready 3D brain viewer. Pick a transparent template shell, pick an atlas, pick the regions you want highlighted, style them, export a transparent-background PNG at any DPI.

## Install

```bash
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python -e ".[dev]"
```

Or with vanilla pip:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the GUI

```bash
.venv/bin/python -m brain_viewer
```

- **Template** section: switch between MNI152 and the three fsaverage variants; adjust opacity; hide/show the shell.
- **Atlas** section: pick an atlas, filter regions, multi-select and click *Add* (or double-click a region).
- **Layers** section: per-layer color picker, opacity slider, label toggle, remove button.
- **View** section: six cardinal view presets plus an oblique.
- **File → Export PNG…** (or Ctrl+E): choose width (px), DPI, transparent background.

## Quick demo (no GUI)

```bash
.venv/bin/python scripts/demo.py
```

Writes `scripts/demo.png` and `scripts/demo_anterior.png`.

## Tests

```bash
.venv/bin/python -m pytest -v
```

## Atlases

All shipped atlases resolve labels into a 3D volume in MNI152 (or close) space, then extract ROI meshes via marching cubes + Taubin smoothing. First-time loads download the atlas through nilearn; subsequent loads hit the local cache in `~/.cache/brain_viewer/atlases/`.

| id | Source | Coverage |
|---|---|---|
| `harvard_oxford_cort` | `fetch_atlas_harvard_oxford('cort-maxprob-thr25-2mm')` | 48 cortical regions |
| `harvard_oxford_sub` | `fetch_atlas_harvard_oxford('sub-maxprob-thr25-2mm')` | 21 subcortical regions |
| `aal` | `fetch_atlas_aal('SPM12')` | ~116 regions, cortex + subcortex + cerebellum |
| `destrieux` | `fetch_atlas_destrieux_2009()` | 148 cortical gyri/sulci |
| `juelich` | `fetch_atlas_juelich('maxprob-thr25-2mm')` | 62 cytoarchitectonic areas |
| `schaefer_{100,200,400,600,1000}_7` | `fetch_atlas_schaefer_2018(n_rois=n, yeo_networks=7)` | Cortical parcellations, 7 networks |
| `yeo_7`, `yeo_17` | `fetch_atlas_yeo_2011(n_networks=n, thickness='thick')` | Resting-state functional networks |
| `msdl` | `fetch_atlas_msdl()` | 39 probabilistic functional networks (thresholded at 0.25 by default) |
| `glasser_hcp_mmp1` | Manual — see below | 360 cortical parcels |

### Known issues

- **AAL**: the upstream server `www.gin.cnrs.fr` uses a certificate chain that some systems reject. If AAL fails to download with `SSLCertVerificationError`, update `ca-certificates` on your system and retry.

### Glasser HCP-MMP1.0 (manual install)

The Glasser atlas is not bundled with nilearn because of licensing. To enable it:

1. Download an MNI152-projected volume version (CC-BY), e.g. from figshare ([search "HCP-MMP1 MNI"](https://figshare.com/search?q=HCP-MMP1+MNI)).
2. Place the files at:
   ```
   ~/.cache/brain_viewer/atlases/glasser/HCP-MMP1_on_MNI152.nii.gz
   ~/.cache/brain_viewer/atlases/glasser/HCP-MMP1_labels.csv
   ```
   The CSV must have `index,name` columns (one row per parcel, integer index matching the volume value).
3. Restart brain_viewer. "Glasser HCP-MMP1.0" will then load like any other atlas.

## Templates

Each template is a glass shell mesh rendered semi-transparent. ROI solids sit inside. Switching templates does not re-mesh ROIs.

| id | Source | Notes |
|---|---|---|
| `mni152_brain` | `load_mni152_brain_mask()` → marching_cubes → smooth | Default. Full brain incl. subcortex. Correct alignment with all volume atlases. |
| `fsaverage_pial` | `fetch_surf_fsaverage('fsaverage6').pial_{left,right}` | Most anatomically detailed cortical surface. |
| `fsaverage_white` | same, `white_*` | Grey/white boundary surface. |
| `fsaverage_inflated` | same, `infl_*` | Stylized inflated cortex. |

**Alignment caveat**: fsaverage lives in FreeSurfer's MNI305-ish space — ROIs in MNI152 volume space will have ~mm-scale drift relative to fsaverage shells, mostly visible at the cortical surface. For precise overlay, use the default `mni152_brain`. fsaverage is best for cortical-only figures where stylized aesthetics matter more than mm-level anatomical precision.

## Export

File → Export PNG… lets you set:
- **Width (px)** — output pixel width. The off-screen plotter renders at a fixed 1600×1200 base then scales up; Pillow resizes to exactly your target width.
- **DPI** — metadata only (PNG `pHYs` chunk). VTK has no concept of DPI; this is what LaTeX / Inkscape / MS Word read to decide physical print size.
- **Transparent background** — on by default; alpha channel is preserved.

The live viewer window is never resized during export.

## Caching

- Atlas downloads: `~/.cache/brain_viewer/atlases/`
- Template meshes (pre-computed `.vtp`): `~/.cache/brain_viewer/templates/`
- ROI meshes (per atlas label, `.vtp`): `~/.cache/brain_viewer/meshes/`

Safe to delete any of these to force a rebuild.

## License

MIT.
