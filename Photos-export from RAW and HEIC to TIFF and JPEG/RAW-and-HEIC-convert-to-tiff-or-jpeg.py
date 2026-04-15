"""
RAW-and-HEIC-convert-to-tiff-or-jpeg.py
========================================
Batch photo converter: RAW + HEIC/HEIF  →  JPEG or 16-bit TIFF (with EXIF).

Supported input formats
-----------------------
  RAW  : CR3, DNG, CR2, NEF, ARW  (via rawpy)
  HEIC : HEIC, HEIF               (via pillow-heif)

Output formats
--------------
  jpeg    — 8-bit JPEG, quality 100, EXIF embedded by Pillow / exiftool
  rawtiff — 16-bit linear TIFF (gamma 1,1), EXIF copied by exiftool

Usage
-----
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --fmt jpeg
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --fmt rawtiff
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --fmt rawtiff --half-size --workers 4
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py <input_dir> <output_dir> --dry-run

Requirements
------------
  pip install rawpy imageio pillow pillow-heif
  exiftool.exe at the path defined in EXIFTOOL below (needed for TIFF EXIF and RAW EXIF)
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# ── Third-party imports ──────────────────────────────────────────────────────
try:
    import rawpy                        # type: ignore[import-untyped]
    import imageio.v3 as iio            # type: ignore[import-untyped]
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False

try:
    from PIL import Image               # type: ignore[import-untyped]
    from pillow_heif import register_heif_opener  # type: ignore[import-untyped]
    register_heif_opener()
    HAS_HEIF = True
except ImportError:
    HAS_HEIF = False

# ── Machine-specific paths — edit before use ─────────────────────────────────
EXIFTOOL = Path(r"")

# Default folders — set to Path() to require CLI arguments
INPUT_DIR  = Path()
OUTPUT_DIR = Path()

# ── File type groups ─────────────────────────────────────────────────────────
RAW_EXTENSIONS  = {'.cr3', '.dng', '.cr2', '.nef', '.arw'}
HEIC_EXTENSIONS = {'.heic', '.heif'}


# ============================================================================
# File discovery
# ============================================================================

def find_files(input_dir: Path) -> tuple[list[Path], list[Path]]:
    """
    Recursively scan input_dir and return (raw_files, heic_files).
    Duplicates (same path, different case) are removed.
    """
    def _collect(exts: set[str]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for ext in exts:
            # rglob is case-insensitive on Windows but case-sensitive on Linux;
            # the seen-set normalises to lowercase to avoid duplicates on all platforms
            for f in input_dir.rglob(f'*{ext}'):
                key = str(f).lower()
                if key not in seen:
                    seen.add(key)
                    result.append(f)
        return sorted(result)

    return _collect(RAW_EXTENSIONS), _collect(HEIC_EXTENSIONS)


# ============================================================================
# EXIF helpers
# ============================================================================

def copy_exif_exiftool(src: Path, dst: Path) -> str | None:
    """
    Copy all EXIF tags from src to dst using exiftool.
    Returns an error string on failure, None on success.
    """
    if not EXIFTOOL.exists():
        return f'exiftool not found at {EXIFTOOL}'
    try:
        result = subprocess.run(
            [str(EXIFTOOL), '-TagsFromFile', str(src),
             '-all:all', '-overwrite_original', str(dst)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return result.stderr.strip() or result.stdout.strip()
        return None
    except Exception as e:
        return str(e)


# ============================================================================
# Converters
# ============================================================================

def _out_path(src: Path, input_dir: Path, output_dir: Path, suffix: str) -> Path:
    """Build the output path, preserving the subfolder structure of input_dir."""
    relative = src.parent.relative_to(input_dir)
    out_folder = output_dir / relative
    out_folder.mkdir(parents=True, exist_ok=True)
    return out_folder / f'{src.stem}{suffix}'


# ── RAW → JPEG ───────────────────────────────────────────────────────────────

def convert_raw_jpeg(raw_path: Path, input_dir: Path, output_dir: Path) -> str:
    """Convert a RAW file to 8-bit JPEG (camera white balance) + copy EXIF via exiftool."""
    if not HAS_RAWPY:
        return f'ERROR: rawpy not installed — {raw_path.name}'
    try:
        out = _out_path(raw_path, input_dir, output_dir, '.jpg')
        if out.exists():
            return f'SKIP (exists): {raw_path.relative_to(input_dir)}'

        with rawpy.imread(str(raw_path)) as raw:
            rgb = raw.postprocess(
                output_bps=8,
                use_camera_wb=True,
                no_auto_bright=False,   # allow normal brightness for JPEG
            )

        img = Image.fromarray(rgb)      # type: ignore[name-defined]
        # quality=100: maximum JPEG quality; subsampling=0: no chroma subsampling (4:4:4)
        img.save(str(out), 'JPEG', quality=100, subsampling=0)

        # Copy EXIF from RAW to JPEG via exiftool
        err = copy_exif_exiftool(raw_path, out)
        if err:
            return f'OK (EXIF ERROR: {err}): {raw_path.relative_to(input_dir)}'
        return f'OK: {raw_path.relative_to(input_dir)} -> {out.name}'

    except Exception as e:
        return f'ERROR: {raw_path.relative_to(input_dir)} — {e}'


# ── RAW → 16-bit TIFF ────────────────────────────────────────────────────────

def convert_raw_tiff(raw_path: Path, input_dir: Path, output_dir: Path,
                     half_size: bool = False) -> str:
    """Convert a RAW file to 16-bit linear TIFF (gamma 1,1) + copy EXIF via exiftool."""
    if not HAS_RAWPY:
        return f'ERROR: rawpy not installed — {raw_path.name}'
    try:
        out = _out_path(raw_path, input_dir, output_dir, '.tiff')
        if out.exists():
            return f'SKIP (exists): {raw_path.relative_to(input_dir)}'

        with rawpy.imread(str(raw_path)) as raw:
            params: dict[str, object] = dict(
                output_bps=16,
                use_camera_wb=True,
                no_auto_bright=True,    # preserve original exposure levels
                gamma=(1, 1),           # linear — no tone curve applied
                no_auto_scale=True,     # preserve raw sensor values
            )
            if half_size:
                params['half_size'] = True   # 2× faster demosaic at half resolution
            rgb = raw.postprocess(**params)

        iio.imwrite(str(out), rgb)

        err = copy_exif_exiftool(raw_path, out)
        if err:
            return f'OK (EXIF ERROR: {err}): {raw_path.relative_to(input_dir)}'
        return f'OK: {raw_path.relative_to(input_dir)} -> {out.name}'

    except Exception as e:
        return f'ERROR: {raw_path.relative_to(input_dir)} — {e}'


# ── HEIC → JPEG ──────────────────────────────────────────────────────────────

def convert_heic_jpeg(heic_path: Path, input_dir: Path, output_dir: Path) -> str:
    """Convert a HEIC/HEIF file to JPEG with EXIF embedded directly by Pillow."""
    if not HAS_HEIF:
        return f'ERROR: pillow-heif not installed — {heic_path.name}'
    try:
        out = _out_path(heic_path, input_dir, output_dir, '.jpg')
        if out.exists():
            return f'SKIP (exists): {heic_path.relative_to(input_dir)}'

        with Image.open(str(heic_path)) as img:     # type: ignore[name-defined]
            exif_raw = img.info.get('exif', b'')
            save_kwargs: dict[str, object] = dict(quality=100, subsampling=0)
            if exif_raw:
                save_kwargs['exif'] = exif_raw      # embed EXIF directly in JPEG
            img.save(str(out), 'JPEG', **save_kwargs)

        return f'OK: {heic_path.relative_to(input_dir)} -> {out.name}'

    except Exception as e:
        return f'ERROR: {heic_path.relative_to(input_dir)} — {e}'


# ── HEIC → TIFF ──────────────────────────────────────────────────────────────

def convert_heic_tiff(heic_path: Path, input_dir: Path, output_dir: Path) -> str:
    """
    Convert a HEIC/HEIF file to LZW-compressed TIFF + copy EXIF via exiftool.
    Pillow strips HEIF EXIF on TIFF save, so exiftool must add it afterwards.
    """
    if not HAS_HEIF:
        return f'ERROR: pillow-heif not installed — {heic_path.name}'
    try:
        out = _out_path(heic_path, input_dir, output_dir, '.tiff')
        if out.exists():
            return f'SKIP (exists): {heic_path.relative_to(input_dir)}'

        with Image.open(str(heic_path)) as img:     # type: ignore[name-defined]
            img.save(str(out), 'TIFF', compression='tiff_lzw')

        # EXIF added after save — Pillow TIFF writer drops HEIF EXIF
        err = copy_exif_exiftool(heic_path, out)
        if err:
            return f'OK (EXIF ERROR: {err}): {heic_path.relative_to(input_dir)}'
        return f'OK: {heic_path.relative_to(input_dir)} -> {out.name}'

    except Exception as e:
        return f'ERROR: {heic_path.relative_to(input_dir)} — {e}'


# ── Dispatcher (required for ProcessPoolExecutor pickling) ───────────────────

def _dispatch(args_tuple: tuple) -> str:
    """Unpack task tuple and call the correct converter."""
    func_name, src, input_dir, output_dir, half_size = args_tuple
    funcs = {
        'raw_jpeg':  lambda: convert_raw_jpeg(src, input_dir, output_dir),
        'raw_tiff':  lambda: convert_raw_tiff(src, input_dir, output_dir, half_size),
        'heic_jpeg': lambda: convert_heic_jpeg(src, input_dir, output_dir),
        'heic_tiff': lambda: convert_heic_tiff(src, input_dir, output_dir),
    }
    return funcs[func_name]()


# ============================================================================
# Main
# ============================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Batch RAW + HEIC/HEIF → JPEG or 16-bit TIFF converter with EXIF',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --fmt jpeg
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --fmt rawtiff
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --fmt rawtiff --half-size --workers 4
  python RAW-and-HEIC-convert-to-tiff-or-jpeg.py ./photos ./out --dry-run
        """
    )
    parser.add_argument('input_dir',  type=Path, nargs='?',
                        default=INPUT_DIR if INPUT_DIR != Path() else None)
    parser.add_argument('output_dir', type=Path, nargs='?',
                        default=OUTPUT_DIR if OUTPUT_DIR != Path() else None)
    parser.add_argument('--fmt', choices=['jpeg', 'rawtiff'], default='jpeg',
                        help='Output format: jpeg (default) or rawtiff (16-bit linear TIFF)')
    parser.add_argument('--half-size', action='store_true',
                        help='Half-size RAW demosaic — 2× faster, half resolution (RAW only)')
    parser.add_argument('--workers', type=int, default=1,
                        help='Parallel worker processes (default: 1)')
    parser.add_argument('--dry-run', action='store_true',
                        help='List files without converting')

    args = parser.parse_args()

    if not args.input_dir or not args.output_dir:
        parser.error('Provide paths as CLI arguments or set INPUT_DIR / OUTPUT_DIR in the script.')
    if not args.input_dir.is_dir():
        print(f'Error: input folder does not exist: {args.input_dir}')
        sys.exit(1)

    # ── Discover files ───────────────────────────────────────────────────────
    print(f'Scanning: {args.input_dir}')
    raw_files, heic_files = find_files(args.input_dir)

    if not HAS_RAWPY and raw_files:
        print('Warning: rawpy not installed — RAW files will be skipped.')
        raw_files = []
    if not HAS_HEIF and heic_files:
        print('Warning: pillow-heif not installed — HEIC files will be skipped.')
        heic_files = []

    total = len(raw_files) + len(heic_files)
    if total == 0:
        print('No supported files found (CR3/DNG/CR2/NEF/ARW/HEIC/HEIF).')
        sys.exit(0)

    print(f'Found: {len(raw_files)} RAW, {len(heic_files)} HEIC/HEIF  →  format: {args.fmt}')

    if args.dry_run:
        print('\n--- Dry run ---')
        for f in raw_files + heic_files:
            print(f'  {f.relative_to(args.input_dir)}')
        sys.exit(0)

    # ── Build task list ──────────────────────────────────────────────────────
    tasks: list[tuple] = []
    for f in raw_files:
        key = 'raw_jpeg' if args.fmt == 'jpeg' else 'raw_tiff'
        tasks.append((key, f, args.input_dir, args.output_dir, args.half_size))
    for f in heic_files:
        key = 'heic_jpeg' if args.fmt == 'jpeg' else 'heic_tiff'
        tasks.append((key, f, args.input_dir, args.output_dir, False))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f'Output: {args.output_dir}')
    if args.fmt == 'rawtiff':
        print('Mode: 16-bit linear TIFF (gamma 1,1 for RAW) / LZW TIFF (for HEIC)')
    print(f'Workers: {args.workers}\n')

    # ── Run ──────────────────────────────────────────────────────────────────
    ok = skip = err = 0
    start = time.time()

    def _tally(msg: str, idx: int) -> None:
        nonlocal ok, skip, err
        print(f'[{idx}/{total}] {msg}')
        if msg.startswith('OK'):
            ok += 1
        elif msg.startswith('SKIP'):
            skip += 1
        else:
            err += 1

    if args.workers > 1:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_dispatch, t): i for i, t in enumerate(tasks, 1)}
            for future in as_completed(futures):
                _tally(future.result(), futures[future])
    else:
        for i, task in enumerate(tasks, 1):
            _tally(_dispatch(task), i)

    elapsed = time.time() - start
    print(f'\n--- Done in {elapsed:.1f}s ---')
    print(f'  Converted : {ok}')
    print(f'  Skipped   : {skip}')
    print(f'  Errors    : {err}')


if __name__ == '__main__':
    main()
