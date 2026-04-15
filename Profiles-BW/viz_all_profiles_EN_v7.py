"""
viz_all_profiles_EN_v7.py
=========================
Generates vertical cross-section plots for archaeological site profiles.

Input:  one or more tab/comma-separated survey text files (total-station data)
Output: PNG images — one per profile file — saved to OUT_DIR

Workflow
--------
1. Parse each survey file: auto-detect separator (comma or space).
2. Project all 3-D points onto the profile axis defined by PRA→PRB anchors.
3. Group points into line segments by type code (GR, SH, B, FG, …).
4. Draw filled polygons for layer types, scatter-plot all individual points.
5. Place non-overlapping leader-line labels for every measured point.
6. Append a legend and a layer-statistics table (width & depth per layer).
7. Save as high-resolution PNG.

Point-code convention
---------------------
  <site>_<TYPE>_<number>[$ | @]
  $  = closed polygon (last point connects back to first)
  @  = interrupted line (segment ends here, new segment starts)

Measured types (MEASURE_TYPES):  GR SH B FG NI TI HP HO
Profile anchors (PR_ANCHORS):    PRA PRB PRC PRD

Changes vs v6
-------------
- Auto-detect separator (comma or space) in input files
- Layer statistics (width & depth) for all measured types printed to console
  and rendered as a monospaced text table on the figure
- Pylance type suppressions for MPoly, scatter marker, fig.transFigure

Based on v6. v6 was based on v5 (EN translation).
Author: Marcin / SAPIENS ARCHAEOLOGIE
"""

from pathlib import Path
from collections import defaultdict
import numpy as np  # type: ignore[import]
import matplotlib  # type: ignore[import-untyped]
matplotlib.use('Agg')                          # non-interactive backend — no display needed
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.patches import Polygon as MPoly  # type: ignore[import-untyped]

# ── Paths ──────────────────────────────────────────────────────────────────────
# DATA_DIR can point to a single .txt file or a directory of files.
# If it is a directory, all files matching '2025_0111_S*.txt' are processed.
DATA_DIR = Path(r"")
OUT_DIR  = Path(r'')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Global figure / output settings ───────────────────────────────────────────
PROJECT        = 'Heidelberg LEMS 2025_0111  |  SAPIENS ARCHAEOLOGIE'
SCALE_CM_PER_M = 50.0    # map scale: 1 data metre → 50 cm on paper  (1 : 2)
DPI_OUT        = 450     # output resolution
FONT_PX        = 30      # desired font size in output pixels
FONT_PT        = FONT_PX * 72 / DPI_OUT   # convert pixels → matplotlib points
LINE_SPACING   = 1.4     # line-height multiplier for multi-line labels
LEGEND_W_CM    = 14.0    # width reserved for the legend panel (right side)

# ── Visual style ───────────────────────────────────────────────────────────────
PR_COLOR   = '#2c3e50'               # colour for profile-anchor points & lines
PR_ANCHORS = {'PRA', 'PRB', 'PRC', 'PRD'}   # codes treated as axis anchors

# 20-colour palette — cycles if more than 20 distinct keys are present
PALETTE = [
    '#e6194b', '#3cb44b', '#4363d8', '#f58231', '#911eb4',
    '#42d4f4', '#f032e6', '#bfef45', '#469990', '#9a6324',
    '#800000', '#808000', '#000075', '#a9a9a9', '#ffe119',
    '#aaffc3', '#dcbeff', '#fabed4', '#ffd8b1', '#fffac8',
]

# Per-type scatter marker styles  {type_code: {marker, s (size), zorder}}
MARKER_STYLE = {
    'NI': dict(marker='o', s=80,  zorder=8),
    'TI': dict(marker='v', s=100, zorder=8),
    'FG': dict(marker='*', s=130, zorder=10),
    'HP': dict(marker='s', s=80,  zorder=7),
    'HO': dict(marker='^', s=80,  zorder=7),
    'B':  dict(marker='.', s=40,  zorder=6),
    'SH': dict(marker='.', s=40,  zorder=6),
    'GR': dict(marker='.', s=40,  zorder=6),
}
PR_MARKER      = dict(marker='D', s=120, zorder=12)   # diamond for anchors
DEFAULT_MARKER = dict(marker='D', s=60,  zorder=7)    # fallback for unknown types

# Types included in the layer-statistics table
MEASURE_TYPES = {'GR', 'SH', 'B', 'FG', 'NI', 'TI', 'HP', 'HO'}

# ── Label layout metrics (in data-unit metres) ─────────────────────────────────
# Derived from font size + scale so labels stay proportional across zoom levels.
_PT_PER_M  = 72.0 * SCALE_CM_PER_M / 2.54   # points per data metre
LINE_H_M   = FONT_PT * LINE_SPACING / _PT_PER_M   # height of one text line
CHAR_W_M   = 0.55 * FONT_PT / _PT_PER_M           # approximate character width
DX_M       = 4.0 / _PT_PER_M                      # horizontal leader-line offset
MAX_CHARS  = 11                                    # max label width in characters
LABEL_W_M  = MAX_CHARS * CHAR_W_M                 # label block width in metres
PROX_D     = LABEL_W_M                            # minimum horizontal gap before overlap check


# ══════════════════════════════════════════════════════════════════════════════
# Parsing helpers
# ══════════════════════════════════════════════════════════════════════════════

def parse_code(raw):
    """
    Decode a raw point-code string into its components.

    Format:  <site>_<TYPE>_<number>[$ | @]
      $  → closed polygon flag
      @  → interrupted line flag

    Returns
    -------
    typ : str   — measurement type  (e.g. 'GR', 'SH', 'NI')
    nr  : str   — sequential number (e.g. '1', '02'), or ''
    closed      : bool — True when code ends with '$'
    interrupted : bool — True when code ends with '@'
    """
    c           = raw.strip().rstrip('.,')
    closed      = c.endswith('$')
    interrupted = c.endswith('@')
    c           = c.rstrip('$@')
    parts = c.split('_')
    typ = parts[1] if len(parts) >= 2 else c
    nr  = parts[2] if len(parts) >= 3 else ''
    return typ, nr, closed, interrupted


def assign_colors(all_keys):
    """
    Assign a palette colour to every (typ, nr) key, skipping anchor types.
    Keys are sorted alphabetically so the colour assignment is deterministic.
    """
    keys = sorted(k for k in all_keys if k[0].upper() not in PR_ANCHORS)
    return {k: PALETTE[i % len(PALETTE)] for i, k in enumerate(keys)}


# ══════════════════════════════════════════════════════════════════════════════
# Label placement
# ══════════════════════════════════════════════════════════════════════════════

def _compute_label_positions(items):
    """
    Greedy non-overlapping label placement along the vertical axis.

    Each label starts just above its anchor point (dy_m offset).  If it would
    overlap a previously placed label at a similar horizontal distance, the
    offset is increased until there is no conflict or the 100-iteration safety
    limit is hit.

    Parameters
    ----------
    items : list of (d, z, text, color)
        Sorted by horizontal distance d before processing.

    Returns
    -------
    result    : list of (d, z, text, color, dy_m)
    z_max_top : float — highest label top edge (used to set y-axis limit)
    """
    placed    = []   # list of (d, z_bot, z_top) for already-placed labels
    result    = []
    z_max_top = -np.inf

    for d0, z0, text, color in sorted(items, key=lambda x: x[0]):
        n_lines  = text.count('\n') + 1
        label_hm = n_lines * LINE_H_M

        dy_m = LINE_H_M * 0.3          # start close to the point
        for _ in range(100):
            z_bot = z0 + dy_m
            z_top = z_bot + label_hm
            # Check for overlap with every already-placed label that is
            # horizontally close enough to matter.
            conflict = any(
                abs(d0 - pd) < PROX_D and not (z_bot >= pz_top or z_top <= pz_bot)
                for pd, pz_bot, pz_top in placed
            )
            if not conflict:
                break
            dy_m += label_hm + LINE_H_M * 0.15   # push label upward and retry

        placed.append((d0, z0 + dy_m, z0 + dy_m + label_hm * 1.05))
        z_max_top = max(z_max_top, z0 + dy_m + label_hm)
        result.append((d0, z0, text, color, dy_m))

    return result, z_max_top


def _draw_labels(ax, positioned_items):
    """
    Draw leader-line annotations for all positioned labels onto *ax*.

    Each annotation uses a thin grey arrowhead from the data point to the
    label box.  The box has a semi-transparent white background so labels
    remain readable over dense scatter plots.
    """
    for d0, z0, text, color, dy_m in positioned_items:
        ax.annotate(
            text, xy=(d0, z0),
            xytext=(d0 + DX_M, z0 + dy_m),
            textcoords='data',
            fontsize=FONT_PT, color=color, fontweight='bold',
            va='bottom', ha='left',
            arrowprops=dict(arrowstyle='-', color='#bbbbbb', lw=0.6,
                            shrinkA=3, shrinkB=3),
            bbox=dict(boxstyle='round,pad=0.1', fc='white', alpha=0.92, ec='none'),
            zorder=20,
        )


# ══════════════════════════════════════════════════════════════════════════════
# Main processing function
# ══════════════════════════════════════════════════════════════════════════════

def process_file(txt_file):
    """
    Read one survey text file and produce a PNG cross-section plot.

    Steps
    -----
    1. Parse rows → list of point dicts (id, x, y, z, typ, nr, flags).
    2. Build the profile axis from PRA (and optionally PRB).
    3. Project every point onto the axis → distance d along the profile.
    4. Collect points into line segments, respecting $ (close) and @ (break).
    5. Render: filled polygons for GR / SH / B, scatter for all types.
    6. Place non-overlapping leader-line labels.
    7. Add legend, layer-statistics table, footer info line.
    8. Save PNG; skip if no points or no PRA anchor found.
    """
    profile_name = txt_file.stem.replace('2025_0111_', '')

    # ── 1. Parse the survey file ───────────────────────────────────────────────
    points = []
    for line in txt_file.read_text(encoding='utf-8', errors='replace').splitlines():
        row  = line.strip()
        cols = row.split(',') if ',' in row else row.split()   # auto-detect separator
        if len(cols) < 5:
            continue
        try:
            pid = int(cols[0])
            x   = float(cols[1])
            y   = float(cols[2])
            z   = float(cols[3])
        except ValueError:
            continue
        raw_kod = cols[4].strip()
        typ, nr, closed, interrupted = parse_code(raw_kod)
        points.append(dict(id=pid, x=x, y=y, z=z, raw=raw_kod,
                           typ=typ, nr=nr,
                           closed=closed, interrupted=interrupted))

    if not points:
        print(f'  SKIP {profile_name}: empty file')
        return

    # ── 2. Locate PRA (required) and PRB (optional) anchors ───────────────────
    pra_pts = [p for p in points if p['typ'].upper() == 'PRA']
    prb_pts = [p for p in points if p['typ'].upper() == 'PRB']

    if not pra_pts:
        print(f'  SKIP {profile_name}: no PRA')
        return

    pra     = pra_pts[0]
    A       = np.array([pra['x'], pra['y']])
    has_prb = bool(prb_pts)

    if has_prb:
        # Unit vector along the PRA→PRB axis
        prb = prb_pts[0]
        B   = np.array([prb['x'], prb['y']])
        L   = float(np.linalg.norm(B - A))
        if L < 0.001:
            print(f'  SKIP {profile_name}: PRA == PRB')
            return
        u = (B - A) / L
    else:
        # Fallback: choose axis along dominant spread of non-anchor points
        ref = [p for p in points if p['typ'].upper() not in PR_ANCHORS] or points
        xs  = np.array([p['x'] for p in ref])
        ys  = np.array([p['y'] for p in ref])
        u   = np.array([1.0, 0.0]) if (xs.max() - xs.min()) >= (ys.max() - ys.min()) \
              else np.array([0.0, 1.0])

    # ── 3. Project points onto the profile axis ────────────────────────────────
    for p in points:
        p['d'] = float(np.dot(np.array([p['x'], p['y']]) - A, u))

    # Without PRB, flip the axis so the bulk of points have positive distances
    if not has_prb:
        ref_ds = [p['d'] for p in points if p['typ'].upper() not in PR_ANCHORS]
        if ref_ds and float(np.mean(ref_ds)) < 0:
            u = -u
            for p in points:
                p['d'] = float(np.dot(np.array([p['x'], p['y']]) - A, u))

    all_ds    = [p['d'] for p in points]
    d_min, d_max = min(all_ds), max(all_ds)
    data_span = max(d_max - d_min, 0.001)
    if not has_prb:
        L = data_span   # profile length when only PRA is available

    all_z   = [p['z'] for p in points]
    z_min   = min(all_z)
    z_range = max(all_z) - z_min

    # ── 4. Build line segments ─────────────────────────────────────────────────
    # Points are collected into buf[key] until a '$' or '@' flag triggers
    # a segment break.  Remaining buffered points form the final segment.
    segments = defaultdict(list)
    buf      = defaultdict(list)
    for p in points:
        key = (p['typ'], p['nr'])
        buf[key].append(p)
        if p['interrupted'] or p['closed']:
            segments[key].append(buf[key][:])
            buf[key] = []
    for key, pts in buf.items():
        if pts:
            segments[key].append(pts)

    # ── Colour assignment ──────────────────────────────────────────────────────
    all_keys  = {(p['typ'], p['nr']) for p in points}
    color_map = assign_colors(all_keys)

    # ── Label data: one entry per point ───────────────────────────────────────
    point_labels = []
    for p in points:
        key  = (p['typ'], p['nr'])
        text = (f'{p["raw"] if p["raw"] else "(no code)"}\n'
                f'id={p["id"]}\n'
                f'X={p["x"]:.3f}\n'
                f'Y={p["y"]:.3f}\n'
                f'Z={p["z"]:.3f}')
        color = PR_COLOR if p['typ'].upper() in PR_ANCHORS \
                else color_map.get(key, '#555555')
        point_labels.append((p['d'], p['z'], text, color))

    positioned, z_max_top = _compute_label_positions(point_labels)

    # ── Figure / axes dimensions (all in inches) ───────────────────────────────
    margin  = max(0.02, z_range * 0.05)   # vertical padding around data
    x_extra = DX_M + LABEL_W_M + 0.02    # horizontal room for rightmost labels

    x_lo = d_min - 0.10
    x_hi = d_max + x_extra
    y_lo = z_min - margin
    y_hi = z_max_top + margin

    # Data-unit extents converted to physical inches via the chosen scale
    ax_w_in = (x_hi - x_lo) * SCALE_CM_PER_M / 2.54
    ax_h_in = (y_hi - y_lo) * SCALE_CM_PER_M / 2.54

    # Fixed margins (in inches) + legend panel on the right
    L_MAR = 1.0;  R_MAR = 0.2;  T_MAR = 0.8;  B_MAR = 0.7
    LEG_W = LEGEND_W_CM / 2.54

    fig_w_in = L_MAR + ax_w_in + R_MAR + LEG_W
    fig_h_in = B_MAR + ax_h_in + T_MAR

    fig, ax = plt.subplots(figsize=(fig_w_in, fig_h_in))
    fig.suptitle(PROJECT, fontsize=10, color='#666666', y=0.998)

    # ── Segment helpers ────────────────────────────────────────────────────────
    def seg_dz(seg):
        """Return (distances, elevations) lists for a segment, closing if flagged."""
        ds = [p['d'] for p in seg]
        zs = [p['z'] for p in seg]
        if seg[-1]['closed']:
            ds.append(ds[0])
            zs.append(zs[0])
        return ds, zs

    def draw_closed_poly(ds, zs, color, alpha=0.20, lw=1.8, zorder=3, label=None):
        """Add a filled Polygon patch and register one legend entry."""
        poly = MPoly(list(zip(ds, zs)), closed=True,  # type: ignore[arg-type]
                     facecolor=color, alpha=alpha,
                     edgecolor=color, linewidth=lw, zorder=zorder)
        ax.add_patch(poly)
        if label:
            # Invisible line just to populate the legend
            ax.plot([], [], color=color, linewidth=lw, label=label)

    # ── 5a. Draw GR (Grube / pit) as filled polygons ──────────────────────────
    gr_labeled = set()
    for key in [k for k in segments if k[0] == 'GR']:
        color = color_map.get(key, '#8B4513')
        label = f'GR_{key[1]}'
        for seg in segments[key]:
            ds, zs = seg_dz(seg)
            draw_closed_poly(ds, zs, color, alpha=0.12, lw=2.0, zorder=2,
                             label=label if label not in gr_labeled else '')
            gr_labeled.add(label)

    # ── 5b. Draw SH (Schicht / layer) as filled+outlined areas ───────────────
    sh_labeled = set()
    for (typ, nr), segs in segments.items():
        if typ != 'SH':
            continue
        color = color_map.get((typ, nr), '#4682B4')
        label = f'SH_{nr}'
        for seg in segs:
            ds, zs = seg_dz(seg)
            ax.fill(ds, zs, color=color, alpha=0.25, zorder=3)
            ax.plot(ds, zs, color=color, linewidth=1.8, zorder=4,
                    label=label if label not in sh_labeled else '')
            sh_labeled.add(label)

    # ── 5c. Draw B (Befund / feature) as filled+outlined areas ───────────────
    b_labeled = set()
    for (typ, nr), segs in segments.items():
        if typ != 'B':
            continue
        color = color_map.get((typ, nr), '#D2691E')
        label = f'B_{nr}'
        for seg in segs:
            ds, zs = seg_dz(seg)
            ax.fill(ds, zs, color=color, alpha=0.20, zorder=4)
            ax.plot(ds, zs, color=color, linewidth=2.0, zorder=5,
                    label=label if label not in b_labeled else '')
            b_labeled.add(label)

    # ── 5d. Scatter-plot every individual point ────────────────────────────────
    legend_keys = set()
    for p in points:
        key      = (p['typ'], p['nr'])
        is_anch  = p['typ'].upper() in PR_ANCHORS
        color    = PR_COLOR if is_anch else color_map.get(key, '#555555')
        style    = PR_MARKER if is_anch else MARKER_STYLE.get(p['typ'], DEFAULT_MARKER)
        leg_lbl  = ''
        if key not in legend_keys:
            # First occurrence of each key → add to legend
            leg_lbl = f'{p["typ"]}_{p["nr"]}' if p['nr'] \
                      else p['typ'] if p['typ'] else '(no code)'
        legend_keys.add(key)
        ax.scatter(p['d'], p['z'], color=color,
                   edgecolors='white', linewidths=0.6,
                   marker=str(style['marker']), s=float(style['s']),  # type: ignore[arg-type]
                   zorder=int(style['zorder']), label=leg_lbl)

    # ── Profile anchor decorations ─────────────────────────────────────────────
    # PRA: vertical dotted line + annotation box
    ax.axvline(pra['d'], color=PR_COLOR, linewidth=0.8, linestyle=':', alpha=0.5)
    ax.annotate(f'PRA\n{pra["z"]:.3f} m', (pra['d'], pra['z']),
                textcoords='offset points', xytext=(-6, 8), ha='right',
                fontsize=FONT_PT * 0.7, color=PR_COLOR, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.2', fc='white',
                          alpha=0.88, ec=PR_COLOR, lw=0.8))
    if has_prb:
        # PRB: vertical dotted line + dashed connecting line + annotation
        ax.axvline(prb['d'], color=PR_COLOR, linewidth=0.8, linestyle=':', alpha=0.5)
        ax.plot([pra['d'], prb['d']], [pra['z'], prb['z']],
                color=PR_COLOR, linewidth=0.8, linestyle='--', alpha=0.4, zorder=1)
        ax.annotate(f'PRB\n{prb["z"]:.3f} m', (prb['d'], prb['z']),
                    textcoords='offset points', xytext=(6, 8), ha='left',
                    fontsize=FONT_PT * 0.7, color=PR_COLOR, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.2', fc='white',
                              alpha=0.88, ec=PR_COLOR, lw=0.8))

    # ── Draw all point labels ──────────────────────────────────────────────────
    _draw_labels(ax, positioned)

    # ── Axes formatting ────────────────────────────────────────────────────────
    ax.set_xlim(d_min - 0.10, d_max + x_extra)
    ax.set_ylim(z_min - margin, z_max_top + margin)
    xlabel = 'Distance along profile PRA\u2192PRB  [m]' if has_prb \
             else 'Distance along profile from PRA  [m]'
    ax.set_xlabel(xlabel, fontsize=12)
    ax.set_ylabel('Elevation Z  [m a.s.l.]', fontsize=12)
    ax.set_title(f'{profile_name} \u2014 Vertical Cross-Section  (all points)',
                 fontsize=16, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.3)
    ax.tick_params(labelsize=10)

    # Reposition the axes to honour the fixed-inch margins exactly
    ax_left   = L_MAR / fig_w_in
    ax_bottom = B_MAR / fig_h_in
    ax_width  = ax_w_in / fig_w_in
    ax_height = ax_h_in / fig_h_in
    ax.set_position((ax_left, ax_bottom, ax_width, ax_height))

    # ── Legend (placed in the dedicated panel to the right of the plot) ────────
    handles, labels_leg = ax.get_legend_handles_labels()
    if handles:
        leg_x = (L_MAR + ax_w_in + R_MAR) / fig_w_in
        leg_y = (B_MAR + ax_h_in) / fig_h_in
        ax.legend(loc='upper left',
                  bbox_to_anchor=(leg_x, leg_y),
                  bbox_transform=fig.transFigure,  # type: ignore[attr-defined]
                  borderaxespad=0, fontsize=10, framealpha=0.9)

    # ── 6. Layer statistics: width & depth for every measured type ─────────────
    # For each (typ, nr) key whose type is in MEASURE_TYPES, collect all points
    # from all segments and compute the horizontal and vertical extent.
    layer_stats = []
    for key in sorted(segments):
        typ, nr = key
        if typ.upper() not in MEASURE_TYPES:
            continue
        pts_flat = [p for seg in segments[key] for p in seg]
        if len(pts_flat) < 2:
            continue
        ds    = [p['d'] for p in pts_flat]
        zs    = [p['z'] for p in pts_flat]
        name  = f'{typ}_{nr}' if nr else typ
        width = max(ds) - min(ds)
        depth = max(zs) - min(zs)
        layer_stats.append((name, width, depth))

    if layer_stats:
        # Print to console
        print(f'  {"Layer":<12}  {"Width [m]":>9}  {"Depth [m]":>9}')
        print(f'  {"-"*12}  {"-"*9}  {"-"*9}')
        for name, width, depth in layer_stats:
            print(f'  {name:<12}  {width:>9.3f}  {depth:>9.3f}')

    # ── Footer: profile length + point count ──────────────────────────────────
    info = f'PRA\u2192PRB: {L:.2f} m   |   points: {len(point_labels)}' if has_prb \
           else f'span: {L:.2f} m   |   points: {len(point_labels)}'
    fig.text(ax_left, 0.002, info, ha='left', va='bottom',
             fontsize=9, color='#333333',
             bbox=dict(boxstyle='round,pad=0.3', fc='#f8f8f8',
                       alpha=0.95, ec='#cccccc', lw=0.7))

    # ── Layer statistics table rendered on figure ──────────────────────────────
    if layer_stats:
        stats_lines = ['Layer measurements:', '']
        stats_lines.append(f'{"Layer":<12}  {"Width":>7}  {"Depth":>7}')
        stats_lines.append(f'{"─"*12}  {"─"*7}  {"─"*7}')
        for name, width, depth in layer_stats:
            stats_lines.append(f'{name:<12}  {width:>6.3f}m  {depth:>6.3f}m')
        leg_x = (L_MAR + ax_w_in + R_MAR) / fig_w_in
        fig.text(leg_x + 0.01, 0.02, '\n'.join(stats_lines),
                 ha='left', va='bottom', fontsize=8,
                 fontfamily='monospace', color='#222222',
                 bbox=dict(boxstyle='round,pad=0.4', fc='#f0f4f8',
                           alpha=0.95, ec='#aabbcc', lw=0.8))

    # ── 7. Save PNG ────────────────────────────────────────────────────────────
    out_path = OUT_DIR / f'{profile_name}_allpts.png'
    i = 2
    while out_path.exists():   # avoid overwriting: append -v2, -v3, …
        out_path = OUT_DIR / f'{profile_name}_allpts-v{i}.png'
        i += 1
    plt.savefig(out_path, dpi=DPI_OUT)
    plt.close()
    print(f'  OK: {out_path.name}  ({len(point_labels)} pts)'
          f'  [{fig_w_in*2.54:.0f}x{fig_h_in*2.54:.0f} cm]')


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if DATA_DIR.is_file():
    files = [DATA_DIR]
else:
    files = sorted(DATA_DIR.glob('2025_0111_S*.txt'))
print(f'Processing {len(files)} profile file(s) ...')
for f in files:
    process_file(f)
print('Done.')
