"""
viz_drone_overlay_v5.py
Overlay drone photo(s) on the archaeological tachymeter plan, with feature-number
labels (arrows) for every polygon-type code whose points fall inside the photo
footprint.

-------------------------------------------------------------------------------
USAGE
-------------------------------------------------------------------------------

Required arguments:
  --measurements FILE    Tachymeter measurements file (combined TXT, UTF-8).
                         Example: path/to/ALL_MEASUREMENTS_COMBINED.txt
  --output FILE          Output PNG file path.
                         Example: path/to/output/result.png
  --photos PHOTO [...]   One or more drone JPG paths (space-separated).
                         Example: DJI_0493.JPG DJI_0494.JPG

Optional arguments:
  --sensor-w-mm MM       Sensor width in mm.  Default: 13.2  (DJI FC6310, 1" sensor)
  --sensor-h-mm MM       Sensor height in mm. Default:  8.8  (DJI FC6310, 1" sensor)
  --alpha A              Photo transparency, 0.0 (invisible) to 1.0 (opaque).
                         Default: 0.75
  --dpi N                Output PNG resolution. Default: 200
  --title TEXT           Figure title. Default: "Drone photo overlay with feature numbers"

Dependencies (install once):
  pip install matplotlib numpy Pillow

External tool required:
  exiftool  -- must be installed and available on PATH.
              Alternatively, set the EXIFTOOL environment variable to its full path.
  Download from: https://exiftool.org

Coordinate system:
  GPS (WGS84) is converted to local tachymeter coords via UTM Zone 32N:
    X_local = 32_000_000 + UTM_easting
    Y_local = UTM_northing

-------------------------------------------------------------------------------
EXAMPLES
-------------------------------------------------------------------------------

Single photo, explicit output (PowerShell -- backtick ` for line continuation):

  python viz_drone_overlay_v5.py `
    --measurements "path/to/ALL_MEASUREMENTS_COMBINED.txt" `
    --output "path/to/output/overlay_0493.png" `
    --photos "path/to/DJI_0493.JPG"

Multiple photos, custom alpha and DPI:

  python viz_drone_overlay_v5.py `
    --measurements "path/to/ALL_MEASUREMENTS_COMBINED.txt" `
    --output "path/to/output/overlay_multi.png" `
    --photos "path/to/DJI_0493.JPG" "path/to/DJI_0494.JPG" `
    --alpha 0.6 --dpi 300

Different camera (e.g. Mavic 3, 4/3" sensor):

  python viz_drone_overlay_v5.py `
    --measurements "..." --output "..." --photos "..." `
    --sensor-w-mm 17.3 --sensor-h-mm 13.0

Help:

  python viz_drone_overlay_v5.py --help

-------------------------------------------------------------------------------
"""

import argparse
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import]
from PIL import Image  # type: ignore[import-untyped]
from matplotlib.patches import Polygon as MplPolygon  # type: ignore[import-untyped]
from matplotlib.path import Path as MplPath  # type: ignore[import-untyped]

# ============================================================
# CONFIG
# ============================================================

# Path to the exiftool binary (needed for GPS / camera EXIF extraction).
# Resolved in order: EXIFTOOL env var -> PATH -> bare "exiftool" command name
# (the last raises FileNotFoundError, handled in read_exif()).
EXIFTOOL = os.environ.get("EXIFTOOL") or shutil.which("exiftool") or "exiftool"

# Alpha (transparency) of the drone photo background: 0.0 = invisible, 1.0 = opaque.
PHOTO_ALPHA = 0.75

# Style of the feature-number text boxes drawn on top of the photo.
BEF_FONTSIZE = 7
BEF_COLOR = "black"
BEF_BBOX = dict(
    boxstyle="round,pad=0.2",
    facecolor="white",
    alpha=1.0,
    edgecolor="#aaaaaa",
    linewidth=0.5,
)

# Feature type codes and their plan-line colours.
# Source: codeliste_befunde_funde.xls (Richtlinie Baden-Württemberg 3).
# Only closed-polygon types are included — open lines (e.g. profiles, levels)
# are not labelled.
# Colour groups:
#   saddlebrown — generic Befunde / earth features
#   steelblue   — cuts / Schichten
#   darkgreen   — masonry / stone
#   purple      — graves
#   crimson     — fire / hearth features
LABEL_TYPS = {
    # --- Befunde / earth features ---
    "ABG": "saddlebrown",   # Abgrabung
    "AH":  "saddlebrown",   # Althorizont
    "B":   "saddlebrown",   # Befund (generic)
    "BG":  "saddlebrown",   # Befundgrenze
    "BH":  "saddlebrown",   # Befundhorizont
    "BRU": "saddlebrown",   # Brunnen
    "BU":  "saddlebrown",   # Baumstumpf / Baumgrube
    "ES":  "saddlebrown",   # Estrich
    "F":   "saddlebrown",   # Fläche
    "FB":  "saddlebrown",   # Fußboden
    "FM":  "saddlebrown",   # Fundamentmauer
    "G":   "saddlebrown",   # Grube
    "GD":  "saddlebrown",   # Grubenverfüllung dunkel
    "GE":  "saddlebrown",   # Geländeerhebung
    "GEO": "saddlebrown",   # Geologische Einheit
    "GH":  "saddlebrown",   # Grubenhaus
    "GN":  "saddlebrown",   # Grubennegativ
    "GRU": "saddlebrown",   # Grubenverfüllung
    "GW":  "saddlebrown",   # Grubenwand
    "GX":  "saddlebrown",   # Grubenerweiterung
    "KA":  "saddlebrown",   # Kanal
    "KR":  "saddlebrown",   # Kreisgrabenverfüllung
    "LH":  "saddlebrown",   # Lehmhorizont
    "LT":  "saddlebrown",   # Lehm-/Tonschicht
    "OF":  "saddlebrown",   # Oberfläche
    "P":   "saddlebrown",   # Pfosten
    "PF":  "saddlebrown",   # Pfostengrube
    "PS":  "saddlebrown",   # Pfostenstein
    "R":   "saddlebrown",   # Rinnenverfüllung
    "S":   "saddlebrown",   # Schicht
    "T":   "saddlebrown",   # Tiefpunkt / Tümpel
    "WG":  "saddlebrown",   # Wandgraben
    # --- Cuts / Schichten ---
    "SH":  "steelblue",     # Schnitt / Schichthorizont
    # --- Masonry / stone ---
    "STO": "darkgreen",     # Stein (einzeln)
    "STZ": "darkgreen",     # Steinzange
    "M":   "darkgreen",     # Mauer
    "MA":  "darkgreen",     # Mauer aus Spolien
    "MW":  "darkgreen",     # Mauerwange
    "ZM":  "darkgreen",     # Ziegelmauer
    # --- Graves ---
    "BGB": "purple",        # Bestattungsgrube
    "GA":  "purple",        # Grabanlage
    "GB":  "purple",        # Grabgrube
    "GBN": "purple",        # Grabgrubennegativ
    "GG":  "purple",        # Grabgefäß
    "KG":  "purple",        # Körpergrab
    # --- Fire / hearth ---
    "BS":  "crimson",       # Brandspur
    "BT":  "crimson",       # Brandtopf
    "FS":  "crimson",       # Feuerstelle
    "HE":  "crimson",       # Herd
    "HS":  "crimson",       # Herdstelle
}

# Vivid overlay colours for label text and arrows.
# LABEL_TYPS colours above are intentionally muted (plan legibility);
# these brighter variants are used only for the label/arrow layer.
ARROW_COLORS = {
    "saddlebrown": "#FF5500",   # Befunde     → vivid orange
    "steelblue":   "#00AAFF",   # Cuts        → vivid sky-blue
    "darkgreen":   "#00CC44",   # Masonry     → vivid green
    "purple":      "#CC00EE",   # Graves      → vivid violet
    "crimson":     "#FF1133",   # Fire/hearth → vivid red
}

# Label collision-resolution parameters.
# Each iteration nudges overlapping labels by LABEL_ANG_STEP_DEG degrees.
# The loop runs at most LABEL_MAX_ITER times; it exits early when no overlap
# or arrow crossing remains.
LABEL_BASE_MARGIN  = 3.0   # metres added to footprint half-diagonal → first label ring
LABEL_ANG_STEP_DEG = 5.0   # angular push per collision iteration (degrees)
LABEL_MAX_ITER     = 120   # maximum collision-resolution iterations

# Output figure dimensions and default DPI.
FIG_SIZE  = (16, 14)
DPI       = 200
FIG_TITLE = "Drone photo overlay with feature numbers"

# Plan-line drawing config — derived automatically from LABEL_TYPS.
# Masonry codes get a slightly thicker line (0.9 pt) for visual weight.
POLY_CFG = {
    code: dict(
        color=color,
        lw=0.9 if code in ("STO", "STZ", "M", "MA", "MW", "ZM") else 0.7,
    )
    for code, color in LABEL_TYPS.items()
}


# ============================================================
# UTM32N → LOCAL TACHYMETER COORDINATE CONVERSION
# ============================================================
# The tachymeter uses a local variant of Gauss-Krüger Zone 3:
#   X_local = 32_000_000 + UTM32N_easting
#   Y_local = UTM32N_northing
# The 32_000_000 prefix is the GK zone identifier added to the raw UTM easting.
# This applies to sites within UTM Zone 32N (easting carried into X_local).
# The conversion uses the standard Karney / USGS formulas; no external library needed.


def wgs84_to_utm32n(lat_deg, lon_deg):
    """Return (easting, northing) in UTM Zone 32N (WGS84 datum)."""
    # WGS84 ellipsoid parameters
    a  = 6378137.0
    f  = 1 / 298.257223563
    b  = a * (1 - f)
    e2 = 1 - (b / a) ** 2          # first eccentricity squared
    e2_ = e2 / (1 - e2)            # second eccentricity squared

    lat  = math.radians(lat_deg)
    lon  = math.radians(lon_deg)
    lon0 = math.radians(9.0)       # central meridian for Zone 32
    k0   = 0.9996                  # UTM scale factor

    # Auxiliary quantities
    N = a / math.sqrt(1 - e2 * math.sin(lat) ** 2)   # radius of curvature in prime vertical
    T = math.tan(lat) ** 2
    C = e2_ * math.cos(lat) ** 2
    A = math.cos(lat) * (lon - lon0)                  # longitude difference scaled by cos(lat)

    # Meridional arc length M from the equator
    M = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * lat
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * lat)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * lat)
        - (35 * e2**3 / 3072) * math.sin(6 * lat)
    )

    # UTM easting (false easting 500 000 m added so all values are positive)
    E = (
        k0 * N * (
            A
            + (1 - T + C)                            * A**3 / 6
            + (5 - 18*T + T**2 + 72*C - 58*e2_)     * A**5 / 120
        )
        + 500_000
    )

    # UTM northing
    Nn = k0 * (
        M + N * math.tan(lat) * (
            A**2 / 2
            + (5 - T + 9*C + 4*C**2)                * A**4 / 24
            + (61 - 58*T + T**2 + 600*C - 330*e2_)  * A**6 / 720
        )
    )

    return E, Nn


def gps_to_local(lat_deg, lon_deg):
    """Convert WGS84 GPS coords to local tachymeter (GK Zone 3 with 32-prefix)."""
    E, N = wgs84_to_utm32n(lat_deg, lon_deg)
    return 32_000_000 + E, N


# ============================================================
# EXIF EXTRACTION
# ============================================================


def dms_to_deg(dms_str):
    """Parse an exiftool DMS string like '12 deg 34' 56.78" N' to decimal degrees."""
    m = re.match(r"(\d+)\s*deg\s*(\d+)'\s*([\d.]+)\"", dms_str)
    if not m:
        return None
    return float(m.group(1)) + float(m.group(2)) / 60 + float(m.group(3)) / 3600


def safe_float(s, default=None):
    """Parse a float from an EXIF value string; return default on any failure."""
    try:
        return float(str(s).lstrip("+").replace(" mm", "").strip())
    except (ValueError, AttributeError):
        return default


def read_exif(photo_path):
    """
    Run exiftool on photo_path and return a dict of {tag_name: value_string}.
    Returns an empty dict if exiftool is missing, times out, or returns an error.
    """
    tags = [
        "-GPSLatitude",
        "-GPSLongitude",
        "-GPSLatitudeRef",
        "-GPSLongitudeRef",
        "-RelativeAltitude",   # DJI-specific: height above take-off point (metres)
        "-CameraYaw",          # DJI-specific: heading of drone nose, CW from North
        "-FocalLength",
        "-ImageWidth",
        "-ImageHeight",
    ]
    try:
        result = subprocess.run(
            [str(EXIFTOOL)] + tags + [str(photo_path)],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            print(f" WARNING: exiftool exit {result.returncode}: {result.stderr.strip()}")
            return {}
    except FileNotFoundError:
        print(f" ERROR: exiftool not found at {EXIFTOOL}")
        return {}
    except subprocess.TimeoutExpired:
        print(" ERROR: exiftool timed out")
        return {}

    # Parse "Tag Name : Value" lines into a flat dict
    data = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            data[k.strip()] = v.strip()
    return data


# ============================================================
# FOOTPRINT GEOMETRY
# ============================================================


def footprint_corners(cx, cy, alt_m, focal_mm, sensor_w, sensor_h, yaw_deg_from_north):
    """
    Compute the four ground-plane corners of a nadir drone photo footprint.

    Parameters
    ----------
    cx, cy              : photo centre in local tachymeter coordinates
    alt_m               : flight altitude above ground (metres)
    focal_mm            : focal length (mm)
    sensor_w, sensor_h  : physical sensor dimensions (mm)
    yaw_deg_from_north  : drone heading, CW from North — this is also the
                          direction from image bottom to image top

    Returns
    -------
    corners : list of 4 (x, y) points in order TL, TR (rotated), BL, BR
    gw, gh  : ground width and height of the footprint (metres)
    """
    # Ground coverage in metres: ground_dim = (sensor_dim / focal) * altitude
    gw = (sensor_w / focal_mm) * alt_m
    gh = (sensor_h / focal_mm) * alt_m

    # Unit vectors for the rotated image axes
    theta = math.radians(yaw_deg_from_north)
    fwd = (math.sin(theta),  math.cos(theta))   # image "up" direction in local coords
    rgt = (math.cos(theta), -math.sin(theta))   # image "right" direction

    hw, hh = gw / 2, gh / 2

    # Four corners: ±right ±forward from centre
    offsets = [
        ( hw*rgt[0] + hh*fwd[0],  hw*rgt[1] + hh*fwd[1]),   # top-right
        (-hw*rgt[0] + hh*fwd[0], -hw*rgt[1] + hh*fwd[1]),   # top-left
        (-hw*rgt[0] - hh*fwd[0], -hw*rgt[1] - hh*fwd[1]),   # bottom-left
        ( hw*rgt[0] - hh*fwd[0],  hw*rgt[1] - hh*fwd[1]),   # bottom-right
    ]

    return [(cx + dE, cy + dN) for dE, dN in offsets], gw, gh


# ============================================================
# TACHYMETER FILE PARSER
# ============================================================

# Line format: id, X, Y, Z, code[terminator]
# Code format: sequence_id _ TYPE _ feature_nr [. | @ | $]
#   .  = last point of an open polyline
#   @  = last point of a closed polygon (connect back to first)
#   $  = same as @ (alternative closing symbol)
line_pat = re.compile(r"^\s*\d+,([0-9.]+),([0-9.]+),([0-9.]+),(\S+)")
kod_pat  = re.compile(r"^\d+_([A-Za-z]+)_(.+)")


def parse_measurements(filepath, draw_typs, label_typs):
    """
    Parse a combined tachymeter measurement file.

    The file may contain measurements for many feature types.  Only types in
    draw_typs are converted to polylines; only types in label_typs are indexed
    for the point-in-polygon label filter.

    Returns
    -------
    segments     : {typ: [[(x,y), ...], ...]}  — polylines per type
    all_feat_pts : {(typ, nr): [(x,y), ...]}   — all raw points per feature
    """
    segments: dict     = {}   # accumulates completed polylines
    all_feat_pts: dict = {}   # accumulates all point coords per feature
    seg_buf: list      = []   # points of the polyline currently being built
    seg_typ            = None
    seg_bef            = None

    def flush(end):
        """Commit the current segment buffer as a completed polyline."""
        nonlocal seg_typ, seg_bef
        if seg_buf and seg_typ and seg_typ in draw_typs:
            pts = list(seg_buf)
            if end in ("@", "$"):
                pts.append(pts[0])   # close the polygon
            segments.setdefault(seg_typ, []).append(pts)
        seg_buf.clear()
        seg_typ = None
        seg_bef = None

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        for line in f:
            lm = line_pat.match(line.strip())
            if not lm:
                continue

            X, Y = float(lm.group(1)), float(lm.group(2))

            km = kod_pat.match(lm.group(4).rstrip(","))
            if not km:
                continue

            typ = km.group(1).upper()
            raw = km.group(2)
            end = raw[-1] if raw and raw[-1] in (".", "@", "$") else ""
            nr  = raw[:-1] if end else raw   # strip terminator from feature number

            # Index this point for the label filter regardless of draw type
            if typ in label_typs:
                all_feat_pts.setdefault((typ, nr), []).append((X, Y))

            # --- Polyline builder ---
            if typ not in draw_typs:
                # Non-drawable type: flush any open segment and skip
                if seg_typ is not None:
                    flush("")
                continue

            if seg_typ is not None and (seg_typ != typ or seg_bef != nr):
                # Switched to a different feature — flush the previous segment
                flush("")

            seg_typ = typ
            seg_bef = nr
            seg_buf.append((X, Y))

            if end:
                # Terminator found — flush and start fresh for the next feature
                flush(end)

    flush("")   # flush any remaining open segment at end of file
    return segments, all_feat_pts


# Set of type codes that will be drawn as plan lines (all POLY_CFG keys)
DRAW_TYPS = set(POLY_CFG.keys())


# ============================================================
# CLI
# ============================================================


def parse_cli():
    """Define and parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Overlay drone photos on the archaeological plan with feature labels."
    )
    p.add_argument(
        "--measurements", required=True, metavar="FILE",
        help="tachymeter measurements file (combined TXT, UTF-8)",
    )
    p.add_argument(
        "--output", required=True, metavar="FILE",
        help="output PNG file path",
    )
    p.add_argument(
        "--photos", required=True, nargs="+", metavar="PHOTO",
        help="one or more drone JPG paths",
    )
    p.add_argument(
        "--sensor-w-mm", type=float, default=13.2, metavar="MM",
        help="sensor width in mm (default: 13.2 — DJI FC6310, 1-inch sensor)",
    )
    p.add_argument(
        "--sensor-h-mm", type=float, default=8.8, metavar="MM",
        help="sensor height in mm (default: 8.8 — DJI FC6310, 1-inch sensor)",
    )
    p.add_argument(
        "--alpha", type=float, default=PHOTO_ALPHA, metavar="A",
        help="photo transparency 0–1 (default: %(default)s)",
    )
    p.add_argument(
        "--dpi", type=int, default=DPI, metavar="N",
        help="output PNG resolution (default: %(default)s)",
    )
    p.add_argument(
        "--title", default=FIG_TITLE,
        help="figure title (default: %(default)s)",
    )
    return p.parse_args()


# ============================================================
# LABEL GEOMETRY HELPERS
# ============================================================


def seg_cross(x1, y1, x2, y2, x3, y3, x4, y4):
    """
    Return True if line segment (x1,y1)-(x2,y2) intersects (x3,y3)-(x4,y4).
    Uses the standard parametric cross-product test; parallel segments return False.
    """
    d1x, d1y = x2 - x1, y2 - y1
    d2x, d2y = x4 - x3, y4 - y3
    denom = d1x * d2y - d1y * d2x
    if abs(denom) < 1e-9:
        return False   # parallel or coincident
    t = ((x3 - x1) * d2y - (y3 - y1) * d2x) / denom
    s = ((x3 - x1) * d1y - (y3 - y1) * d1x) / denom
    return 0.0 <= t <= 1.0 and 0.0 <= s <= 1.0


# ============================================================
# MAIN PIPELINE
# ============================================================


def main():
    args = parse_cli()
    measurements_path = Path(args.measurements)
    output_path       = Path(args.output)
    drone_photos      = args.photos
    sensor_w_mm       = args.sensor_w_mm
    sensor_h_mm       = args.sensor_h_mm
    photo_alpha       = args.alpha
    dpi               = args.dpi
    fig_title         = args.title

    # ----------------------------------------------------------
    # 1. PARSE TACHYMETER PLAN
    # ----------------------------------------------------------
    segments, all_feat_pts = parse_measurements(
        measurements_path, DRAW_TYPS, LABEL_TYPS
    )
    total_segs = sum(len(v) for v in segments.values())
    print(f"Plan segments: {total_segs} | Feature codes indexed: {len(all_feat_pts)}")

    # ----------------------------------------------------------
    # 2. PROCESS DRONE PHOTOS — extract EXIF, compute footprints
    # ----------------------------------------------------------
    drone_info = []

    for photo_path in drone_photos:
        print(f"\nPhoto: {Path(photo_path).name}")

        # --- Read EXIF via exiftool ---
        exif = read_exif(photo_path)
        if not exif:
            print(" WARNING: no EXIF data, skipping")
            continue

        # Parse GPS coordinates from DMS strings
        lat = dms_to_deg(exif.get("GPS Latitude", ""))
        lon = dms_to_deg(exif.get("GPS Longitude", ""))
        if lat is None or lon is None:
            print(" WARNING: no GPS data, skipping")
            continue
        if "S" in exif.get("GPS Latitude Ref",  ""):
            lat = -lat
        if "W" in exif.get("GPS Longitude Ref", ""):
            lon = -lon

        # Relative altitude is mandatory for footprint calculation
        alt_m = safe_float(exif.get("Relative Altitude"), default=None)
        if alt_m is None:
            print(" WARNING: Relative Altitude missing — skipping")
            continue

        yaw_deg = safe_float(exif.get("Camera Yaw"),   default=0.0)
        focal   = safe_float(exif.get("Focal Length"), default=8.8)

        # Convert GPS centre to local tachymeter coordinates
        cx, cy = gps_to_local(lat, lon)

        # Compute the four ground-plane corners of the rotated footprint
        corners, ground_w, ground_h = footprint_corners(
            cx, cy, alt_m, focal, sensor_w_mm, sensor_h_mm, yaw_deg
        )

        print(f" GPS: {lat:.6f}N {lon:.6f}E  alt={alt_m}m  yaw={yaw_deg}°")
        print(f" Local centre: X={cx:.2f}  Y={cy:.2f}")
        print(f" Footprint: {ground_w:.2f}m × {ground_h:.2f}m")

        # --- Rotate photo so North is up ---
        # PIL.rotate is CCW; CameraYaw is CW from North, so -yaw aligns North to top.
        # expand=True pads the canvas with transparent pixels so no corner is clipped.
        # The geographic extent is then scaled proportionally to the enlarged canvas.
        img_pil  = Image.open(photo_path).convert("RGBA")
        orig_w, orig_h = img_pil.size
        img_rot  = img_pil.rotate(
            -yaw_deg,
            expand=True,
            resample=Image.Resampling.BICUBIC,
            fillcolor=(0, 0, 0, 0),
        )
        new_w, new_h = img_rot.size

        # Scale the ground footprint dimensions to the expanded canvas size
        gw_exp = ground_w * (new_w / orig_w)
        gh_exp = ground_h * (new_h / orig_h)
        img_extent = (
            cx - gw_exp / 2,
            cx + gw_exp / 2,
            cy - gh_exp / 2,
            cy + gh_exp / 2,
        )

        # Axis-aligned bounding box (AABB) of the actual rotated footprint corners.
        # Used only for max_arrow calculation; the label filter uses the true polygon.
        xs_c = [p[0] for p in corners]
        ys_c = [p[1] for p in corners]
        bbox = (min(xs_c), max(xs_c), min(ys_c), max(ys_c))

        # --- Point-in-polygon filter ---
        # Build an MplPath from the rotated footprint and test all feature centroids.
        # contains_points() is accurate for the real rotated polygon shape,
        # unlike a simple AABB test which includes transparent corner padding.
        footprint_path = MplPath(corners + [corners[0]])
        inside: dict = {}
        for (typ, nr), pts in all_feat_pts.items():
            if not pts:
                continue
            arr  = np.array(pts)
            mask = footprint_path.contains_points(arr)
            if not mask.any():
                continue
            local = arr[mask]
            # Use the centroid of all in-footprint points as the arrow tip
            mx = float(local[:, 0].mean())
            my = float(local[:, 1].mean())
            inside.setdefault(typ, {})[nr] = (mx, my)

        for typ, hits in inside.items():
            print(f" {typ} in footprint: {sorted(hits.keys())}")

        drone_info.append({
            "name":       Path(photo_path).stem,
            "cx":         cx,
            "cy":         cy,
            "corners":    corners,
            "img_rot":    np.array(img_rot),
            "img_extent": img_extent,
            "bbox":       bbox,
            "inside":     inside,
        })

    # ----------------------------------------------------------
    # 3. BUILD FIGURE
    # ----------------------------------------------------------
    fig, ax = plt.subplots(figsize=FIG_SIZE)
    ax.set_aspect("equal")

    # Cycle of outline colours for the footprint rectangles when multiple photos
    colors = ["red", "blue", "orange", "magenta"]

    # Draw each drone photo as a semi-transparent background layer
    for info in drone_info:
        xmin, xmax, ymin, ymax = info["img_extent"]
        ax.imshow(
            info["img_rot"],
            extent=(xmin, xmax, ymin, ymax),
            alpha=photo_alpha,
            zorder=0,
            origin="upper",
        )

    # Draw tachymeter plan lines on top of the photo
    for typ, segs in segments.items():
        cfg = POLY_CFG[typ]
        for pts in segs:
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=cfg["color"], lw=cfg["lw"], zorder=2)

    # Draw footprint outlines and photo-name labels for each drone photo
    for i, info in enumerate(drone_info):
        c = colors[i % len(colors)]
        ax.add_patch(MplPolygon(
            info["corners"],
            closed=True,
            edgecolor=c,
            facecolor="none",
            lw=1.2,
            zorder=5,
        ))
        ax.scatter(info["cx"], info["cy"], color=c, s=40, zorder=6)
        ax.text(
            info["cx"], info["cy"] + 0.5,
            info["name"],
            fontsize=6, color=c, ha="center", zorder=7,
        )

    # Lock axis limits from plan + footprint extents before placing labels.
    # Locking keeps the px/m scale constant during collision resolution so that
    # pixel-space bbox sizes do not change between iterations.
    all_xs = [x for segs in segments.values() for pts in segs for x, _ in pts]
    all_ys = [y for segs in segments.values() for pts in segs for _, y in pts]
    for info in drone_info:
        all_xs.extend(p[0] for p in info["corners"])
        all_ys.extend(p[1] for p in info["corners"])
    pad = 5.0
    ax.set_xlim(min(all_xs) - pad, max(all_xs) + pad)
    ax.set_ylim(min(all_ys) - pad, max(all_ys) + pad)

    # ----------------------------------------------------------
    # 4. BUILD LABEL LIST
    # ----------------------------------------------------------
    # Each label dict holds the mutable state used by the collision resolver:
    #   cx, cy     — photo centre (anchor for the radial placement)
    #   bx, by     — feature centroid (fixed arrow tip, inside the footprint)
    #   ang        — current label angle in degrees, measured from cx/cy
    #   r          — current label distance from cx/cy (may be capped by max_arrow)
    #   max_arrow  — longest photo side (metres); hard cap on arrow length
    #   txt        — label string, e.g. "B 159"
    #   color      — vivid ARROW_COLORS entry for this feature type
    #   ann        — matplotlib Annotation object (set during initial placement)

    all_labels = []
    for info in drone_info:
        xmin, xmax, ymin, ymax = info["bbox"]
        cx_p, cy_p = info["cx"], info["cy"]

        # half_diag: distance from photo centre to AABB corner — used as a
        # natural offset so labels start just outside the visible photo area.
        half_diag = math.hypot(xmax - xmin, ymax - ymin) / 2
        base_r    = half_diag + LABEL_BASE_MARGIN

        # max_arrow: labels may not produce an arrow longer than the photo's
        # longer dimension.  Enforced geometrically in _label_pos() below.
        max_arrow = max(xmax - xmin, ymax - ymin)

        for typ, hits in info["inside"].items():
            txt_color = ARROW_COLORS.get(LABEL_TYPS[typ], "#FF5500")
            for nr, (bx, by) in hits.items():
                # Natural angle: direction from photo centre to feature centroid.
                # Labels start on this radial so the arrow points naturally.
                nat_ang = math.degrees(math.atan2(by - cy_p, bx - cx_p))
                all_labels.append({
                    "cx":        cx_p,
                    "cy":        cy_p,
                    "bx":        bx,
                    "by":        by,
                    "ang":       nat_ang,
                    "r":         base_r,
                    "max_arrow": max_arrow,
                    "txt":       f"{typ} {nr}",
                    "color":     txt_color,
                    "ann":       None,
                })

    # ----------------------------------------------------------
    # 5. HELPER: compute clamped label position
    # ----------------------------------------------------------
    def _label_pos(ld):
        """
        Return (tx, ty, r_used) for label ld.

        r_used is min(ld["r"], r_cap) where r_cap is the maximum r such that
        the arrow length distance((tx,ty), (bx,by)) equals max_arrow.

        Derivation: let (dcx, dcy) = centroid - photo_centre.
            arrow_len^2 = (r*cos_a - dcx)^2 + (r*sin_a - dcy)^2
                        = r^2 - 2*r*dot + d0^2
        Setting arrow_len = max_arrow and solving for r:
            r_cap = dot + sqrt(dot^2 - d0^2 + max_arrow^2)
        The discriminant is always >= 0 when the centroid is inside the footprint
        and max_arrow >= half_diag (both guaranteed by construction).
        """
        rad          = math.radians(ld["ang"])
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        dcx  = ld["bx"] - ld["cx"]
        dcy  = ld["by"] - ld["cy"]
        dot  = dcx * cos_a + dcy * sin_a
        d0sq = dcx ** 2 + dcy ** 2
        disc = dot ** 2 - d0sq + ld["max_arrow"] ** 2
        r_cap = dot + math.sqrt(max(disc, 0.0))
        r     = min(ld["r"], r_cap)
        return ld["cx"] + r * cos_a, ld["cy"] + r * sin_a, r

    # ----------------------------------------------------------
    # 6. INITIAL LABEL PLACEMENT
    # ----------------------------------------------------------
    for ld in all_labels:
        tx, ty, _ = _label_pos(ld)
        ld["ann"] = ax.annotate(
            ld["txt"],
            xy=(ld["bx"], ld["by"]),        # arrow tip — at the feature centroid
            xytext=(tx, ty),                  # label text position
            fontsize=BEF_FONTSIZE,
            color=ld["color"],
            fontweight="bold",
            ha="center",
            va="center",
            bbox=BEF_BBOX,
            arrowprops=dict(
                arrowstyle="->",
                color=ld["color"],
                lw=1.1,
                shrinkA=0,   # no gap between text box and arrow tail
                shrinkB=0,   # no gap between arrowhead and feature centroid
            ),
            zorder=12,
        )

    # ----------------------------------------------------------
    # 7. COLLISION RESOLUTION
    # ----------------------------------------------------------
    # Two-pass iterative resolver.  Each pass modifies label angles (and
    # occasionally r) in ld dicts; positions are recomputed and annotations
    # updated after both passes complete.
    #
    # Pass 1 — text-box overlap
    #   If two label bounding boxes overlap in screen space, push them apart by
    #   LABEL_ANG_STEP_DEG / 2 each in opposite angular directions.
    #   Radial bumping is intentionally absent: max_arrow already caps how far
    #   out a label can go, so pushing r outward would silently stall once r_cap
    #   is reached (the overlap flag would stay True but the position would not
    #   move, preventing convergence).
    #
    # Pass 2 — arrow crossing
    #   If the line segment of arrow i crosses the line segment of arrow j (tested
    #   in data coordinates), swap the angles of the two labels.  After the swap
    #   each arrow points toward the other label's original side, which generically
    #   uncrosses them.  Any resulting text-box overlaps are handled in the next
    #   Pass 1 iteration.
    #
    # The loop exits early when neither pass finds anything to fix.

    fig.canvas.draw()
    renderer = fig.canvas.renderer  # type: ignore[attr-defined]

    for _iter in range(LABEL_MAX_ITER):
        bboxes  = [ld["ann"].get_window_extent(renderer) for ld in all_labels]
        changed = False

        # --- Pass 1: resolve text-box overlaps ---
        for i in range(len(all_labels)):
            for j in range(i + 1, len(all_labels)):
                if not bboxes[i].overlaps(bboxes[j]):
                    continue
                changed = True
                li, lj  = all_labels[i], all_labels[j]
                # ang_diff in (-180, +180]: positive means lj is CCW ahead of li
                ang_diff = (lj["ang"] - li["ang"] + 360) % 360
                if ang_diff > 180:
                    ang_diff -= 360
                push = LABEL_ANG_STEP_DEG / 2
                if ang_diff >= 0:
                    li["ang"] -= push   # push li CW
                    lj["ang"] += push   # push lj CCW
                else:
                    li["ang"] += push
                    lj["ang"] -= push

        # --- Pass 2: uncross crossing arrows ---
        # Compute clamped label positions once (avoids redundant sqrt per pair).
        positions = [_label_pos(ld) for ld in all_labels]
        for i in range(len(all_labels)):
            for j in range(i + 1, len(all_labels)):
                tx_i, ty_i, _ = positions[i]
                tx_j, ty_j, _ = positions[j]
                li, lj = all_labels[i], all_labels[j]
                if not seg_cross(
                    tx_i, ty_i, li["bx"], li["by"],
                    tx_j, ty_j, lj["bx"], lj["by"],
                ):
                    continue
                changed = True
                # Swap angles: each label moves to the other's angular position,
                # which generically uncrosses the two arrows.
                li["ang"], lj["ang"] = lj["ang"], li["ang"]

        if not changed:
            print(f" Labels converged after {_iter} iterations")
            break

        # Update all annotation positions with the new angles.
        # _label_pos re-applies the max_arrow cap, so r never silently grows.
        for ld in all_labels:
            tx, ty, _ = _label_pos(ld)
            ld["ann"].set_position((tx, ty))
            ld["ann"].xy = (ld["bx"], ld["by"])

        fig.canvas.draw()

    # ----------------------------------------------------------
    # 8. FINALISE AND SAVE
    # ----------------------------------------------------------
    fig.canvas.draw()
    ax.set_title(fig_title)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi)
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()
