# RAW-and-HEIC-convert-to-tiff-or-jpeg

Batch photo converter for RAW and HEIC/HEIF files.  
Converts to JPEG or 16-bit TIFF while preserving all EXIF metadata.

---

## What it does

| Input | `--fmt jpeg` | `--fmt rawtiff` |
|-------|-------------|-----------------|
| RAW (CR3, DNG, CR2, NEF, ARW) | 8-bit JPEG, EXIF via exiftool | 16-bit linear TIFF (gamma 1,1), EXIF via exiftool |
| HEIC / HEIF | 8-bit JPEG, EXIF embedded by Pillow | LZW-compressed TIFF, EXIF via exiftool |

- Recurses into subfolders, preserving the folder structure in the output
- Skips files that already exist in the output (safe to re-run)
- Optional parallel processing (`--workers N`)
- Dry-run mode to preview without converting

---

## Requirements

### Python packages

```bash
pip install rawpy imageio pillow pillow-heif
```

| Package | Purpose | License |
|---------|---------|---------|
| `rawpy` | RAW file decoding (CR3/DNG/CR2/NEF/ARW) | MIT |
| `imageio` | Writing 16-bit TIFF files | BSD-2-Clause |
| `pillow` | JPEG/TIFF saving, image manipulation | MIT |
| `pillow-heif` | HEIC/HEIF decoding (registers opener in Pillow) | BSD-3-Clause |

All packages work independently — if only one group is installed:
- Only `rawpy` + `imageio` → RAW files work, HEIC files skipped
- Only `pillow` + `pillow-heif` → HEIC files work, RAW files skipped

### exiftool (external tool)

Required for copying EXIF to TIFF files and from RAW to JPEG.

Download: https://exiftool.org  
Place `exiftool.exe` at the path set in the `EXIFTOOL` constant in the script (default: `D:\Sapiens\software\exiftool.exe`).

Without exiftool: images are converted but EXIF metadata is not transferred (a warning is printed per file).

---

## Usage

```bash
# Convert all RAW + HEIC in a folder to JPEG
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --fmt jpeg

# Convert to 16-bit TIFF
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --fmt rawtiff

# Half-size RAW (2× faster, half resolution — useful for quick previews)
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --fmt rawtiff --half-size

# Parallel processing (4 cores)
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --fmt jpeg --workers 4

# Preview without converting
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --dry-run
```

### Hardcoded paths (alternative to CLI)

Edit `INPUT_DIR` and `OUTPUT_DIR` at the top of the script to set default folders,
then run without arguments:

```bash
python RAW-and-HEIC-convert-to-tiff-or-jpeg.py --fmt jpeg
```

---

## Output format details

### JPEG (`--fmt jpeg`)
- 8-bit, quality 100, no chroma subsampling (4:4:4)
- Camera white balance applied
- EXIF: embedded directly by Pillow (HEIC) or copied by exiftool (RAW)

### TIFF (`--fmt rawtiff`)
- RAW → 16-bit linear (gamma 1,1, no tone curve, no auto-exposure) — suitable for photogrammetry and scientific use
- HEIC → 8-bit LZW-compressed TIFF
- EXIF copied by exiftool after saving (Pillow drops HEIF EXIF on TIFF write)

---

## Legal notes

**This script** is original code and can be published freely.

**Python dependencies** are all permissive open-source licenses (MIT / BSD) — safe to list in a public repo as `pip install` requirements. They are not bundled.

**exiftool** is licensed under GPL. It is an external executable called via subprocess — not bundled or distributed with this script. Users download and install it separately. No GPL obligations apply to this script.

**HEIC/HEIF format** uses the HEVC codec which is patent-licensed. The `pillow-heif` library uses `libheif`, which handles codec licensing. Personal use and publishing a conversion tool is generally unproblematic; commercial redistribution of the decoded images may require checking with your legal counsel.

**Conclusion: safe to publish as a public GitHub repo.**
