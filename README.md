# ezbv

Figure-ready 3D brain viewer. Pick a transparent template shell, pick an atlas, pick the regions you want highlighted, style them, save the scene for later, and export a high-DPI PNG or a rotating GIF.

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

Inside the repo:
```bash
.venv/bin/python -m ezbv
```

Or from anywhere (once per machine, after `pip install -e`):
```bash
ln -sf "$(pwd)/.venv/bin/ezbv" ~/.local/bin/ezbv
ezbv
```

- **Template** section: switch between MNI152 and the three fsaverage variants; adjust opacity; hide/show the shell; toggle back-face culling.
- **Atlas** section: pick an atlas, filter regions, multi-select and click *Add* (or double-click a region). Use the **+** button to register a custom NIfTI + labels pair.
- **Layers** section: each row has a visibility checkbox, color picker, opacity slider, label toggle, and remove (✕). Hidden layers are greyed out and excluded from exports.
- **View** section: six cardinal view presets plus an oblique.
- **File → Open scene… / Save scene…** (Ctrl+O / Ctrl+S): persist the full editable scene (active shells, layers, colors, opacities, label toggles, visibility, camera, back-face toggle) as a `*.ezbv.json` file and reopen it later. Missing atlases or templates on load produce warnings; everything else restores.
- **File → Export figure…** (or Ctrl+E): choose format (PNG still or animated GIF), width (px), DPI, transparent background. GIF adds rotation axis (vertical / horizontal / roll), total sweep, frame count, and cycle duration.

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

The dropdown ships **~40 built-in atlases** grouped by anatomy (Cortex / Subcortex / Cerebellum / Thalamus / White matter / Whole brain / Networks). First-time loads download through nilearn or a pinned external URL; subsequent loads hit the on-disk cache under `~/.cache/ezbv/atlases/`.

### Cortex
| id | Source | Regions |
|---|---|---|
| `harvard_oxford_cort` | nilearn `fetch_atlas_harvard_oxford('cort-maxprob-thr25-2mm')` | 48 |
| `destrieux` | nilearn `fetch_atlas_destrieux_2009()` | 148 gyri/sulci |
| `juelich` | nilearn `fetch_atlas_juelich('maxprob-thr25-2mm')` | 62 cytoarchitectonic |
| `schaefer_{100,200,400,600,1000}_7` | nilearn `fetch_atlas_schaefer_2018` | 100–1000 parcels, 7 nets |
| `yeo_7`, `yeo_17` | nilearn `fetch_atlas_yeo_2011` | 7 / 17 networks |
| `talairach_lobe`, `talairach_gyrus`, `talairach_ba` | nilearn `fetch_atlas_talairach` | 12 / 55 / 48 |
| `allen_2011_rsn` | nilearn `fetch_atlas_allen_2011` | 28 RSNs |
| `glasser_hcp_mmp1_auto` | figshare 3501911 → `HCP-MMP1_on_MNI152_ICBM2009a_nlin.nii.gz` | 179 (left hemisphere only) |
| `glasser_hcp_mmp1` | manual install (see below) | 360 (bilateral) |

### Subcortex
| id | Source | Regions |
|---|---|---|
| `harvard_oxford_sub` | nilearn `fetch_atlas_harvard_oxford('sub-…-thr25-2mm')` | 21 |
| `pauli_2017_det`, `pauli_2017_prob` | nilearn `fetch_atlas_pauli_2017` | 12 / 16 |
| `melbourne_sub_s{1,2,3,4}` | nitrc Tian 2020 MSA zip | 16 / 32 / 50 / 54 |

### Cerebellum
| id | Source | Regions |
|---|---|---|
| `suit_anatom` | github DiedrichsenLab/cerebellar_atlases | 34 lobules (SUIT) |
| `buckner_cerebellar_7`, `buckner_cerebellar_17` | same repo | 7 / 17 networks |
| `mdtb_10` | same repo (King 2019) | 10 task domains |

### Thalamus
| id | Source | Regions |
|---|---|---|
| `najdenovska_thalamus` | Zenodo 1405484 (max-prob) | 14 (7 per hemi) |
| `najdenovska_thalamus_prob` | Zenodo 1405484 (4D probabilistic) | 14 |

### White matter
| id | Source | Regions |
|---|---|---|
| `jhu_wm_labels` | NeuroVault 264 — JHU ICBM labels | 48 tracts |

### Whole brain / Networks
| id | Source | Regions |
|---|---|---|
| `aal` | nilearn `fetch_atlas_aal('SPM12')` | ~116 |
| `basc_{64,122,444}_sym` | nilearn `fetch_atlas_basc_multiscale_2015` | 64 / 122 / 444 |
| `difumo_{64,256,1024}` | nilearn `fetch_atlas_difumo` | 64 / 256 / 1024 (probabilistic) |
| `craddock_2012` | nilearn `fetch_atlas_craddock_2012` | ~43 (scorr_mean) |
| `brainnetome_246` | github mirror of Fan 2016 BN_Atlas (official LUT) | 246 (210 cortical + 36 subcortical, incl. 6 insular subregions/hemi) |
| `msdl` | nilearn `fetch_atlas_msdl` | 39 probabilistic |
| `smith_2009_rsn_{10,70}` | nilearn `fetch_atlas_smith_2009` | 10 / 70 ICA networks |

### Known issues

- **AAL** and **Talairach gyrus/BA** and **Craddock 2012** upstream hosts (`www.gin.cnrs.fr`, `www.talairach.org`, `cluster_roi.projects.nitrc.org`) have had intermittent TLS certificate problems. If these fail to download with `SSLCertVerificationError`, updating your system `ca-certificates` usually fixes it.
- **Glasser auto-download** is left-hemisphere only (179 regions). For full bilateral 360-region Glasser, use the manual-install path below.

### Atlases available via "+ Add custom atlas" (manual / restricted)

These require registration, have ambiguous redistribution terms, or aren't in MNI152 volume form — use the **`+`** button in the Atlas section to paste a URL or local file after downloading:

- **AICHA** (384 regions) — Joliot lab / Lead-DBS
- **Iglesias hippocampal subfields** — FreeSurfer license; tied to FreeSurfer install
- **Gordon 2016** (333 cortical parcels) — BALSA (CIFTI surface-only by default)
- **Morel thalamus** — Zenodo (search "Morel atlas")
- **CIT168** (14 subcortical ROIs) — https://osf.io/r2hvk
- **Glasser bilateral (360 regions)** — place at `~/.cache/ezbv/atlases/glasser/HCP-MMP1_on_MNI152.nii.gz` with a `HCP-MMP1_labels.csv` alongside (see `glasser_hcp_mmp1` entry).

### Custom atlases

To add your own parcellation (e.g. a more detailed insula atlas), click **`+`** next to the atlas dropdown:

- **Display name** — how it appears in the dropdown (prefixed `Custom: …`).
- **Volume** — a local NIfTI path (`.nii` / `.nii.gz`) or an HTTP(S) URL. Must be in MNI152 space to align with the template shells. 4D volumes are auto-detected as probabilistic (one channel per region, thresholded at 0.25 by default for mesh extraction).
- **Labels** (optional) — a CSV/TSV with `index` + `name` columns, a JSON dict (`{"1": "Insula_anterior", ...}`), or a plain text file with `index name` lines (FSL LUT style). If omitted, regions are auto-named `Label N` from unique integer values in the volume.

The dialog downloads or copies the files into `~/.cache/ezbv/atlases/custom/<id>/` and writes a small `index.json`, so your custom atlases persist across sessions. The **`✕`** button next to the dropdown removes the currently-selected custom atlas (cache files and all).

### Glasser HCP-MMP1.0 (manual install)

The Glasser atlas is not bundled with nilearn because of licensing. To enable it:

1. Download an MNI152-projected volume version (CC-BY), e.g. from figshare ([search "HCP-MMP1 MNI"](https://figshare.com/search?q=HCP-MMP1+MNI)).
2. Place the files at:
   ```
   ~/.cache/ezbv/atlases/glasser/HCP-MMP1_on_MNI152.nii.gz
   ~/.cache/ezbv/atlases/glasser/HCP-MMP1_labels.csv
   ```
   The CSV must have `index,name` columns (one row per parcel, integer index matching the volume value).
3. Restart ezbv. "Glasser HCP-MMP1.0" will then load like any other atlas.

## Templates

Each template is a glass shell mesh rendered semi-transparent. ROI solids always sit in MNI152 world coords regardless of which template is active — switching templates only changes the enclosing shell, not where the regions are.

| id | Source | Notes |
|---|---|---|
| `mni152_detailed` | iso-surface of `load_mni152_gm_template(resolution=1)` at 0.5 | Default. Detailed cortical gyri visible. Includes subcortical GM so subcortical ROIs still fit inside. |
| `mni152_brain` | `load_mni152_brain_mask()` → marching_cubes → smooth | Simplified brain envelope. Chunkier, no gyri, but fully watertight around every voxel of the brain mask. |
| `fsaverage_pial` | `fetch_surf_fsaverage('fsaverage6').pial_{left,right}` | FreeSurfer pial surface. |
| `fsaverage_white` | same, `white_*` | Grey/white boundary surface. |
| `fsaverage_inflated` | same, `infl_*` | Stylized inflated cortex. LH/RH separated along X with a 20 mm midline gap so the two hemispheres don't overlap. |

**Alignment caveat**: fsaverage lives in FreeSurfer's MNI305-ish space — ROIs in MNI152 volume space will have mm-scale drift relative to fsaverage shells, mostly visible at the cortical surface. For precise overlay, use `mni152_detailed`. fsaverage is best for cortical-only figures where stylized aesthetics matter more than mm-level anatomical precision.

Template meshes are cached at `~/.cache/ezbv/templates/{id}_v{N}.vtp` — delete to force a rebuild.

## Scenes (save / open)

**File → Save scene…** writes an `*.ezbv.json` file describing everything the user can edit in the GUI:

- Active template shells (id, opacity, visibility)
- Layers (atlas id, label index + display name, color RGB, opacity, label toggle, visibility)
- Back-face culling toggle
- Camera (position, focal point, view-up)

**File → Open scene…** clears the current scene, re-fetches the referenced atlases & templates, rebuilds meshes from the on-disk cache, restores all state, and syncs the left-panel rows. Missing items (e.g. a custom atlas that was deleted, or a renamed template id) are reported as warnings and the rest of the scene still loads.

The file is plain indented JSON — it's fine to hand-edit colors, opacities, or visibility flags outside the GUI.

Legacy `ez_brain_viewer.scene` format strings from pre-rename scene files are still accepted on load.

## Export

File → Export figure… opens a dialog with two formats:

**PNG (still image)**
- **Width (px)** — output pixel width. The off-screen plotter renders at a fixed 1600×1200 base then scales up; Pillow resizes to exactly your target width.
- **DPI** — metadata only (PNG `pHYs` chunk). VTK has no concept of DPI; this is what LaTeX / Inkscape / MS Word read to decide physical print size.
- **Transparent background** — on by default; alpha channel is preserved.

**Animated GIF (rotating)**
- **Width (px)** — defaults to 1200 px because GIFs balloon in file size with dimensions × frames.
- **Axis** — `vertical` (azimuth spin around the up axis; classic rotating brain), `horizontal` (elevation pitch), or `roll` (line-of-sight roll).
- **Total rotation** — sweep angle across the whole clip. 360° gives a seamless loop.
- **Frames** — number of captured frames. More = smoother motion, larger file.
- **Cycle duration** — total playback time (seconds) for one full sweep. Per-frame duration = `1000 × duration / frames` ms.
- **Loop indefinitely** — standard GIF looping flag.
- **Background** — always solid white. GIF supports only 1-bit palette transparency, which bleeds through any semi-transparent shell; for alpha-correct output, export PNG.

The live viewer window is never resized during export.

## Caching

- Atlas downloads: `~/.cache/ezbv/atlases/`
- Template meshes (pre-computed `.vtp`): `~/.cache/ezbv/templates/`
- ROI meshes (per atlas label, `.vtp`): `~/.cache/ezbv/meshes/`
- App icon (rendered from the MNI152 mesh on first run): `~/.cache/ezbv/app_icon_v1.png`

Safe to delete any of these to force a rebuild.

If you are upgrading from the previous `brain_viewer` / `ez_brain_viewer` names, migrate your existing downloads in one command:

```bash
mv ~/.cache/ez_brain_viewer ~/.cache/ezbv   # or ~/.cache/brain_viewer if you never went through the intermediate name
```

## License

MIT.
