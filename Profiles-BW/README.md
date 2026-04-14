# viz_all_profiles_EN_v7.py

Generates high-resolution vertical cross-section plots from total-station survey data for archaeological site profiles.

---

## What it does

For each input survey file the script:

1. Parses a text file of measured points (auto-detects comma or space separator)
2. Projects all 3-D coordinates onto the profile axis defined by anchors **PRA → PRB**
3. Groups points into line segments using type codes (with `$` close / `@` break flags)
4. Draws the cross-section:
   - filled polygons for **GR** (pits), **SH** (layers), **B** (features)
   - scatter plot for all individual points (NI, TI, FG, HP, HO, B, SH, GR, …)
   - non-overlapping leader-line labels with full coordinate info for every point
5. Appends a legend panel and a layer-statistics table (width & depth per layer)
6. Saves a PNG at 450 DPI — file is auto-versioned if output already exists

---

## Input format

Plain-text file, one point per row.  Columns:

```
<id>  <X>  <Y>  <Z>  <code>
```

- Separator: comma **or** space (detected automatically)
- `<code>` format: `<site>_<TYPE>_<number>[$ | @]`
  - `$` — closes the current polygon (segment loops back to its first point)
  - `@` — interrupts the current line (new segment starts on the next point)

Example row:

```
42  3456789.123  5432100.456  118.234  2025_GR_01$
```

---

## Point-code types

| Code | Meaning         | Rendered as                  |
|------|-----------------|------------------------------|
| PRA  | Profile anchor A | diamond, dark blue            |
| PRB  | Profile anchor B | diamond, dark blue            |
| GR   | Grube (pit)     | filled polygon + dot          |
| SH   | Schicht (layer) | filled + outlined area + dot  |
| B    | Befund (feature)| filled + outlined area + dot  |
| NI   | Niet (rivet)    | circle                        |
| TI   | Tinte (?)       | triangle-down                 |
| FG   | Fund gesamt     | star                          |
| HP   | Holzpfahl (post)| square                        |
| HO   | Holz (wood)     | triangle-up                   |

---

## Configuration

Edit the constants near the top of the script:

| Constant | Default | Description |
|----------|---------|-------------|
| `DATA_DIR` | *(path)* | Input file or directory of `*.txt` files |
| `OUT_DIR` | *(path)* | Output directory for PNG files |
| `PROJECT` | *(string)* | Title shown at top of every figure |
| `SCALE_CM_PER_M` | `50.0` | Map scale (50 cm/m = 1:2) |
| `DPI_OUT` | `450` | Output resolution |
| `FONT_PX` | `30` | Label font size in output pixels |
| `LEGEND_W_CM` | `14.0` | Width of the legend panel in cm |

---

## Output

- One PNG per input file, named `<profile>_allpts.png`
- If the file already exists, a suffix `-v2`, `-v3`, … is appended automatically
- Figure size is calculated from the data extent + the chosen scale, so every profile is drawn at a consistent physical size
- Layer statistics (horizontal width and vertical depth) are printed to the console and rendered as a monospaced table in the figure

---

## Requirements

```
numpy
matplotlib
```

Install with:

```bash
pip install numpy matplotlib
```

---

## Usage

```bash
python viz_all_profiles_EN_v7.py
```

Point `DATA_DIR` to a single `.txt` file to process one profile, or to a directory to batch-process all matching files.

---

## Version history

| Version | Key changes |
|---------|-------------|
| v7 | Auto-detect separator; layer-statistics table on figure; Pylance type suppressions |
| v6 | English labels; legend panel; label collision avoidance |
| v5 | EN translation of v4 |
| v1–v4 | Initial development (DE) |

---

*SAPIENS ARCHAEOLOGIE*
