# viz_drone_overlay_v5.py

Overlay drone photos on a tachymeter archaeological plan with automatic
feature-number labels and arrows.

---

## Purpose

This tool overlays georeferenced drone photos onto a tachymeter-surveyed
archaeological plan. For each drone JPG it reads GPS position, relative altitude
and camera heading from the EXIF metadata, computes the photo's ground footprint,
warps the image into plan coordinates, and draws it beneath the plan linework.
Every polygon-type feature whose survey points fall inside a photo's footprint is
automatically labelled with its feature number and an arrow pointing to the
feature centroid.

It lets the user view the actual photographed surface together with the
interpreted plan — useful for checking or documenting feature outlines against
the real ground.

You supply your own tachymeter measurement data exported as a TXT file. Any set
of survey points works, but results are best when the points lie roughly in the
part of the site shown in the photo.

---

## Scope

This tool implements the feature coding and plan conventions of the
*Richtlinie Baden-Württemberg 3* (Codeliste Befunde/Funde). It is built for
excavations documented under those rules and will only produce correct labels
for that code system. If you need a version adapted to a different documentation
standard, please get in touch via GitHub (open an issue or a pull request).

---

## Requirements

### Python packages
```
pip install matplotlib numpy Pillow
```

### External tool
- **exiftool** — reads GPS and camera metadata from DJI JPG files.
  Download: https://exiftool.org
  Must be installed and available on PATH, or set the `EXIFTOOL` environment
  variable to its full path.

---

## Input files

| Argument | Description |
|---|---|
| `--measurements` | Combined tachymeter TXT file (UTF-8). Contains all plan points for the excavation. |
| `--photos` | One or more DJI drone JPGs with GPS + CameraYaw EXIF data. |
| `--output` | Output PNG path. |

### Measurements file format

The `--measurements` file is a plain-text tachymeter point export, UTF-8 encoded,
one point per line. Lines that do not match the expected pattern are silently
skipped, so headers or comments may be interleaved.

**Line format:**
```
id,X,Y,Z,code
```
| Field | Meaning |
|---|---|
| `id` | Running point number (integer). |
| `X`, `Y` | Local plan coordinates (see *Coordinate system*). |
| `Z` | Height (recorded in the file but not used by this tool). |
| `code` | Feature code, see below. |

**Code format:**
```
seq_TYPE_nr[terminator]
```
- `seq` — numeric sequence id (ignored for drawing).
- `TYPE` — letter type code (e.g. `B`, `SH`, `M`); only codes in `LABEL_TYPS` are
  labelled, only drawable codes become plan lines.
- `nr` — feature number (groups points of the same feature).
- `terminator` — optional last-point marker:
  - `.` — last point of an **open** polyline.
  - `@` — last point of a **closed** polygon (connects back to the first point).
  - `$` — same as `@` (alternative closing symbol).

Consecutive points sharing the same `TYPE` and `nr` are joined into one polyline;
a terminator (or a switch to another feature) closes the current segment.

**Example:**
```
1001,32500000.00,5400000.10,98.7,1_B_12
1002,32500000.80,5400000.80,98.6,1_B_12
1003,32500001.20,5399999.90,98.6,1_B_12@
```

### Drone photo requirements

Each photo must be a **nadir** shot (camera pointing straight down). The footprint
model assumes a flat ground plane and a vertical camera axis — oblique shots will
be placed incorrectly.

The following EXIF/XMP tags are read via exiftool and must be present:

| Tag | Source | Use |
|---|---|---|
| `GPSLatitude` / `GPSLongitude` (+ refs) | standard EXIF | photo centre position |
| `RelativeAltitude` | DJI XMP | height above take-off point (footprint scale) |
| `CameraYaw` | DJI XMP | heading, CW from North — image "up" direction |
| `FocalLength` | EXIF | footprint scale |
| `ImageWidth` / `ImageHeight` | EXIF | image aspect ratio |

Notes:
- `RelativeAltitude` and `CameraYaw` are **DJI-specific** XMP tags. Cameras that
  don't write them will not work unless altitude and yaw are supplied another way.
- Altitude is measured relative to the take-off point, so the take-off elevation
  should match the surveyed ground; a large offset rescales the footprint.
- Footprint size = `(sensor_dimension / focal_length) × altitude`. The default
  sensor size (13.2 × 8.8 mm) is for the DJI FC6310 (Phantom 4 Pro); override with
  `--sensor-w-mm` / `--sensor-h-mm` for other cameras.
- GPS accuracy directly affects placement; consumer-drone GPS is typically within
  a few metres, so expect small absolute offsets.

---

## Usage

Run from PowerShell (backtick `` ` `` for line continuation):

```powershell
python viz_drone_overlay_v5.py `
  --measurements "path/to/ALL_MEASUREMENTS_COMBINED.txt" `
  --output "path/to/output/result.png" `
  --photos "path/to/DJI_0493.JPG"
```

Multiple photos:
```powershell
python viz_drone_overlay_v5.py `
  --measurements "path/to/ALL_MEASUREMENTS_COMBINED.txt" `
  --output "path/to/output/result.png" `
  --photos "path/to/DJI_0493.JPG" "path/to/DJI_0494.JPG"
```

All arguments:
```
--measurements FILE    tachymeter measurements file (required)
--output FILE          output PNG path (required)
--photos PHOTO [...]   drone JPG path(s) (required)
--sensor-w-mm MM       sensor width in mm  (default: 13.2 — DJI FC6310)
--sensor-h-mm MM       sensor height in mm (default:  8.8 — DJI FC6310)
--alpha A              photo transparency 0–1 (default: 0.75)
--dpi N                output resolution (default: 200)
--title TEXT           figure title
```

---

## Coordinate system

The tachymeter uses a local variant of Gauss-Krüger Zone 3:

```
X_local = 32_000_000 + UTM32N_easting
Y_local = UTM32N_northing
```

GPS (WGS84) coordinates from the drone EXIF are converted to this system
automatically. Valid for sites within UTM Zone 32N.

---

## Feature type codes

Labels are generated for all polygon-type feature codes defined in `LABEL_TYPS`
(source: *Codeliste Befunde/Funde, Richtlinie Baden-Württemberg 3*).

| Colour group | Codes | Meaning |
|---|---|---|
| orange | `B`, `G`, `P`, `S`, … | Befunde / earth features |
| sky-blue | `SH` | Cuts / Schichten |
| green | `M`, `STO`, `STZ`, … | Masonry / stone |
| violet | `GA`, `GB`, `KG`, … | Graves |
| red | `FS`, `HE`, `HS`, … | Fire / hearth |

---

## Label placement algorithm

1. Each label starts at `half_diag + 3 m` from the photo centre, at the natural
   angle toward its feature centroid.
2. Arrow tip is fixed at the feature centroid (inside the footprint).
3. Arrow length is hard-capped at the photo's longer side (`max_arrow = max(W, H)`).
4. Iterative collision resolver (max 120 iterations, exits early on convergence):
   - **Pass 1** — text-box overlap → push labels apart angularly (5°/2 each).
   - **Pass 2** — arrow-arrow crossing → swap the two label angles.

---

## Output

A single PNG at the `--output` path, rendered at `--dpi` (default 200) with equal
aspect ratio:

- Each drone photo is drawn as a semi-transparent background layer (`--alpha`,
  default 0.75), rotated so North is up and scaled to its ground footprint.
- With several photos, each footprint is outlined in a different colour (red,
  blue, orange, magenta, cycling).
- Plan linework from the measurements file is drawn on top, coloured by
  feature-type group (see *Feature type codes*).
- Every feature whose survey points fall inside a footprint gets a white label
  box with its feature number and an arrow pointing to the in-footprint centroid;
  overlapping labels and crossing arrows are de-cluttered by the collision
  resolver.
- Axes are in local plan coordinates (metres); the figure title comes from
  `--title`.

The console also prints, per photo: GPS centre, local centre X/Y, footprint size,
and the feature numbers found inside each footprint — a quick sanity check.

---

## Known limitations

- **No orthorectification.** Each photo is only scaled and rotated to its
  footprint rectangle, not warped to a terrain model. Lens distortion is not
  corrected, so the image is approximate, not pixel-accurate.
- **Nadir + flat-ground assumption.** Camera tilt / oblique shots and sloped
  terrain are not modelled; both displace the footprint.
- **Altitude is relative to take-off.** If the take-off point is not at the
  surveyed ground level, the footprint is mis-scaled.
- **GPS-only georeferencing.** Placement inherits consumer-drone GPS error (a few
  metres); there is no ground-control-point (GCP) adjustment.
- **DJI-specific.** Requires the DJI XMP tags `RelativeAltitude` and `CameraYaw`;
  other drones need those values supplied another way.
- **Only polygon-type codes are labelled** (those in `LABEL_TYPS`); open lines
  such as profiles or levels are ignored.
- **Heuristic label placement.** The collision resolver runs a capped number of
  iterations and may not fully separate labels in very dense scenes.
- **2D only.** Point heights (Z) are not used.

---

## Project context

This tool was created while working with the documentation standards of
Baden-Württemberg, to make it easier to georeference individual photos when the
location where they were taken is difficult to verify. It can also help check the
positioning of files used in SfM (Structure-from-Motion) photogrammetry.

It belongs to the [Archeology-Software-BW](https://github.com/akroterion/Archeology-Software-BW)
collection.

---

## Version history

| Version | Changes |
|---|---|
| v5 | Arrow tip at centroid, max_arrow cap, two-pass collision resolver (angular push + arrow swap) |
| v4 | argparse CLI, polygon_entry arrow tips, locked axis limits, max_r cap |
| v3 | expand=True rotation fix, point-in-polygon filter, pixel-space collision resolver |
| v2 | LABEL_TYPS hardcoded, feature label overlay |
| v2a | Profile visualisation variant |
