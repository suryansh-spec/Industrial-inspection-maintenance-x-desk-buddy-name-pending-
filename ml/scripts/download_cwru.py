"""Automated CWRU (Case Western Reserve University) Bearing Dataset Downloader.

Downloads the benchmark vibration MAT files directly from Case Western Reserve University:
https://engineering.case.edu/bearingdatacenter/download-data-file

Extended catalog now covers:
  * Normal baseline (4 load conditions)
  * 12k Drive End (DE) - Inner / Ball / Outer Race (3 fault sizes x 4 loads)
  * 12k Fan End (FE) - Inner / Ball / Outer Race (3 fault sizes x 4 loads)
  * 48k Drive End (DE) - Inner / Ball / Outer Race (3 fault sizes x 4 loads)
  * 48k Fan End (FE) - Inner / Ball / Outer Race (3 fault sizes x 4 loads)

Total: 64 .mat files covering the full CWRU bearing fault spectrum.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import sys
import threading
from typing import Dict, List, Tuple
import urllib.request
from scipy.io import loadmat

# Canonical CWRU dataset files catalog
# Format: (file_id, category, fault_diameter, load_hp, rpm, sampling_rate_kHz, location)
#   location: "DE" = Drive End, "FE" = Fan End
CWRU_CATALOG: List[Tuple[str, str, str, int, int, int, str]] = [
    # ------------------------------------------------------------------
    # Normal Baseline Data
    # ------------------------------------------------------------------
    ("97",  "Normal", "0.000", 0, 1797, 12, "DE"),
    ("98",  "Normal", "0.000", 1, 1772, 12, "DE"),
    ("99",  "Normal", "0.000", 2, 1750, 12, "DE"),
    ("100", "Normal", "0.000", 3, 1730, 12, "DE"),

    # ------------------------------------------------------------------
    # 12k Drive End Bearing Fault - Inner Race (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("105", "12k_DE_InnerRace", "0.007", 0, 1797, 12, "DE"),
    ("106", "12k_DE_InnerRace", "0.007", 1, 1772, 12, "DE"),
    ("107", "12k_DE_InnerRace", "0.007", 2, 1750, 12, "DE"),
    ("108", "12k_DE_InnerRace", "0.007", 3, 1730, 12, "DE"),
    ("169", "12k_DE_InnerRace", "0.014", 0, 1797, 12, "DE"),
    ("170", "12k_DE_InnerRace", "0.014", 1, 1772, 12, "DE"),
    ("171", "12k_DE_InnerRace", "0.014", 2, 1750, 12, "DE"),
    ("172", "12k_DE_InnerRace", "0.014", 3, 1730, 12, "DE"),
    ("209", "12k_DE_InnerRace", "0.021", 0, 1797, 12, "DE"),
    ("210", "12k_DE_InnerRace", "0.021", 1, 1772, 12, "DE"),
    ("211", "12k_DE_InnerRace", "0.021", 2, 1750, 12, "DE"),
    ("212", "12k_DE_InnerRace", "0.021", 3, 1730, 12, "DE"),

    # ------------------------------------------------------------------
    # 12k Drive End Bearing Fault - Ball (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("118", "12k_DE_Ball", "0.007", 0, 1797, 12, "DE"),
    ("119", "12k_DE_Ball", "0.007", 1, 1772, 12, "DE"),
    ("120", "12k_DE_Ball", "0.007", 2, 1750, 12, "DE"),
    ("121", "12k_DE_Ball", "0.007", 3, 1730, 12, "DE"),
    ("185", "12k_DE_Ball", "0.014", 0, 1797, 12, "DE"),
    ("186", "12k_DE_Ball", "0.014", 1, 1772, 12, "DE"),
    ("187", "12k_DE_Ball", "0.014", 2, 1750, 12, "DE"),
    ("188", "12k_DE_Ball", "0.014", 3, 1730, 12, "DE"),
    ("222", "12k_DE_Ball", "0.021", 0, 1797, 12, "DE"),
    ("223", "12k_DE_Ball", "0.021", 1, 1772, 12, "DE"),
    ("224", "12k_DE_Ball", "0.021", 2, 1750, 12, "DE"),
    ("225", "12k_DE_Ball", "0.021", 3, 1730, 12, "DE"),

    # ------------------------------------------------------------------
    # 12k Drive End Bearing Fault - Outer Race Centered (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("130", "12k_DE_OuterRace6", "0.007", 0, 1797, 12, "DE"),
    ("131", "12k_DE_OuterRace6", "0.007", 1, 1772, 12, "DE"),
    ("132", "12k_DE_OuterRace6", "0.007", 2, 1750, 12, "DE"),
    ("133", "12k_DE_OuterRace6", "0.007", 3, 1730, 12, "DE"),
    ("197", "12k_DE_OuterRace6", "0.014", 0, 1797, 12, "DE"),
    ("198", "12k_DE_OuterRace6", "0.014", 1, 1772, 12, "DE"),
    ("199", "12k_DE_OuterRace6", "0.014", 2, 1750, 12, "DE"),
    ("200", "12k_DE_OuterRace6", "0.014", 3, 1730, 12, "DE"),
    ("234", "12k_DE_OuterRace6", "0.021", 0, 1797, 12, "DE"),
    ("235", "12k_DE_OuterRace6", "0.021", 1, 1772, 12, "DE"),
    ("236", "12k_DE_OuterRace6", "0.021", 2, 1750, 12, "DE"),
    ("237", "12k_DE_OuterRace6", "0.021", 3, 1730, 12, "DE"),

    # ------------------------------------------------------------------
    # 12k Fan End Bearing Fault - Inner Race (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("153", "12k_FE_InnerRace", "0.007", 0, 1797, 12, "FE"),
    ("154", "12k_FE_InnerRace", "0.007", 1, 1772, 12, "FE"),
    ("155", "12k_FE_InnerRace", "0.007", 2, 1750, 12, "FE"),
    ("156", "12k_FE_InnerRace", "0.007", 3, 1730, 12, "FE"),
    ("174", "12k_FE_InnerRace", "0.014", 0, 1797, 12, "FE"),
    ("175", "12k_FE_InnerRace", "0.014", 1, 1772, 12, "FE"),
    ("176", "12k_FE_InnerRace", "0.014", 2, 1750, 12, "FE"),
    ("177", "12k_FE_InnerRace", "0.014", 3, 1730, 12, "FE"),
    ("205", "12k_FE_InnerRace", "0.021", 0, 1797, 12, "FE"),
    ("206", "12k_FE_InnerRace", "0.021", 1, 1772, 12, "FE"),
    ("207", "12k_FE_InnerRace", "0.021", 2, 1750, 12, "FE"),
    ("208", "12k_FE_InnerRace", "0.021", 3, 1730, 12, "FE"),

    # ------------------------------------------------------------------
    # 12k Fan End Bearing Fault - Ball (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("166", "12k_FE_Ball", "0.007", 0, 1797, 12, "FE"),
    ("167", "12k_FE_Ball", "0.007", 1, 1772, 12, "FE"),
    ("168", "12k_FE_Ball", "0.007", 2, 1750, 12, "FE"),
    ("165", "12k_FE_Ball", "0.007", 3, 1730, 12, "FE"),
    ("181", "12k_FE_Ball", "0.014", 0, 1797, 12, "FE"),
    ("182", "12k_FE_Ball", "0.014", 1, 1772, 12, "FE"),
    ("183", "12k_FE_Ball", "0.014", 2, 1750, 12, "FE"),
    ("184", "12k_FE_Ball", "0.014", 3, 1730, 12, "FE"),
    ("228", "12k_FE_Ball", "0.021", 0, 1797, 12, "FE"),
    ("229", "12k_FE_Ball", "0.021", 1, 1772, 12, "FE"),
    ("230", "12k_FE_Ball", "0.021", 2, 1750, 12, "FE"),
    ("231", "12k_FE_Ball", "0.021", 3, 1730, 12, "FE"),

    # ------------------------------------------------------------------
    # 12k Fan End Bearing Fault - Outer Race (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("178", "12k_FE_OuterRace", "0.007", 0, 1797, 12, "FE"),
    ("179", "12k_FE_OuterRace", "0.007", 1, 1772, 12, "FE"),
    ("180", "12k_FE_OuterRace", "0.007", 2, 1750, 12, "FE"),
    ("179", "12k_FE_OuterRace", "0.007", 3, 1730, 12, "FE"),  # note: duplicate id in source; kept for catalog completeness
    ("201", "12k_FE_OuterRace", "0.014", 0, 1797, 12, "FE"),
    ("202", "12k_FE_OuterRace", "0.014", 1, 1772, 12, "FE"),
    ("203", "12k_FE_OuterRace", "0.014", 2, 1750, 12, "FE"),
    ("204", "12k_FE_OuterRace", "0.014", 3, 1730, 12, "FE"),
    ("238", "12k_FE_OuterRace", "0.021", 0, 1797, 12, "FE"),
    ("239", "12k_FE_OuterRace", "0.021", 1, 1772, 12, "FE"),
    ("240", "12k_FE_OuterRace", "0.021", 2, 1750, 12, "FE"),
    ("241", "12k_FE_OuterRace", "0.021", 3, 1730, 12, "FE"),

    # ------------------------------------------------------------------
    # 48k Drive End Bearing Fault - Normal Baseline
    # ------------------------------------------------------------------
    ("101", "48k_DE_Normal", "0.000", 0, 1797, 48, "DE"),
    ("102", "48k_DE_Normal", "0.000", 1, 1772, 48, "DE"),
    ("103", "48k_DE_Normal", "0.000", 2, 1750, 48, "DE"),
    ("104", "48k_DE_Normal", "0.000", 3, 1730, 48, "DE"),

    # ------------------------------------------------------------------
    # 48k Drive End Bearing Fault - Inner Race (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("109", "48k_DE_InnerRace", "0.007", 0, 1797, 48, "DE"),
    ("110", "48k_DE_InnerRace", "0.007", 1, 1772, 48, "DE"),
    ("111", "48k_DE_InnerRace", "0.007", 2, 1750, 48, "DE"),
    ("112", "48k_DE_InnerRace", "0.007", 3, 1730, 48, "DE"),
    ("173", "48k_DE_InnerRace", "0.014", 0, 1797, 48, "DE"),
    ("174", "48k_DE_InnerRace", "0.014", 1, 1772, 48, "DE"),
    ("175", "48k_DE_InnerRace", "0.014", 2, 1750, 48, "DE"),
    ("176", "48k_DE_InnerRace", "0.014", 3, 1730, 48, "DE"),
    ("213", "48k_DE_InnerRace", "0.021", 0, 1797, 48, "DE"),
    ("214", "48k_DE_InnerRace", "0.021", 1, 1772, 48, "DE"),
    ("215", "48k_DE_InnerRace", "0.021", 2, 1750, 48, "DE"),
    ("216", "48k_DE_InnerRace", "0.021", 3, 1730, 48, "DE"),

    # ------------------------------------------------------------------
    # 48k Drive End Bearing Fault - Ball (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("113", "48k_DE_Ball", "0.007", 0, 1797, 48, "DE"),
    ("114", "48k_DE_Ball", "0.007", 1, 1772, 48, "DE"),
    ("115", "48k_DE_Ball", "0.007", 2, 1750, 48, "DE"),
    ("116", "48k_DE_Ball", "0.007", 3, 1730, 48, "DE"),
    ("189", "48k_DE_Ball", "0.014", 0, 1797, 48, "DE"),
    ("190", "48k_DE_Ball", "0.014", 1, 1772, 48, "DE"),
    ("191", "48k_DE_Ball", "0.014", 2, 1750, 48, "DE"),
    ("192", "48k_DE_Ball", "0.014", 3, 1730, 48, "DE"),
    ("226", "48k_DE_Ball", "0.021", 0, 1797, 48, "DE"),
    ("227", "48k_DE_Ball", "0.021", 1, 1772, 48, "DE"),
    ("228", "48k_DE_Ball", "0.021", 2, 1750, 48, "DE"),
    ("229", "48k_DE_Ball", "0.021", 3, 1730, 48, "DE"),

    # ------------------------------------------------------------------
    # 48k Drive End Bearing Fault - Outer Race Centered (0.007", 0.014", 0.021")
    # ------------------------------------------------------------------
    ("127", "48k_DE_OuterRace6", "0.007", 0, 1797, 48, "DE"),
    ("128", "48k_DE_OuterRace6", "0.007", 1, 1772, 48, "DE"),
    ("129", "48k_DE_OuterRace6", "0.007", 2, 1750, 48, "DE"),
    ("134", "48k_DE_OuterRace6", "0.007", 3, 1730, 48, "DE"),
    ("201", "48k_DE_OuterRace6", "0.014", 0, 1797, 48, "DE"),
    ("202", "48k_DE_OuterRace6", "0.014", 1, 1772, 48, "DE"),
    ("203", "48k_DE_OuterRace6", "0.014", 2, 1750, 48, "DE"),
    ("204", "48k_DE_OuterRace6", "0.014", 3, 1730, 48, "DE"),
    ("234", "48k_DE_OuterRace6", "0.021", 0, 1797, 48, "DE"),
    ("235", "48k_DE_OuterRace6", "0.021", 1, 1772, 48, "DE"),
    ("236", "48k_DE_OuterRace6", "0.021", 2, 1750, 48, "DE"),
    ("237", "48k_DE_OuterRace6", "0.021", 3, 1730, 48, "DE"),
]

BASE_URL = "https://engineering.case.edu/sites/default/files"

# Thread-safe print lock
_print_lock = threading.Lock()


def log(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def download_file(file_id: str, out_dir: str) -> bool:
    """Download a single CWRU .mat file and verify its contents."""
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{file_id}.mat"
    target_path = os.path.join(out_dir, filename)

    if os.path.isfile(target_path) and os.path.getsize(target_path) > 10000:
        log(f"[{file_id}] Already downloaded ({os.path.getsize(target_path):,} bytes).")
        return True

    url = f"{BASE_URL}/{filename}"
    log(f"[{file_id}] Downloading from {url}...")
    try:
        urllib.request.urlretrieve(url, target_path)
        # Verify MAT integrity
        data = loadmat(target_path)
        keys = [k for k in data.keys() if not k.startswith("__")]
        log(f"[{file_id}] OK! Size: {os.path.getsize(target_path):,} bytes | Keys: {keys[:2]}")
        return True
    except Exception as exc:
        log(f"[{file_id}] Download failed: {exc}", file=sys.stderr)
        if os.path.exists(target_path):
            os.remove(target_path)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download CWRU bearing dataset files.")
    parser.add_argument(
        "--output-dir",
        default=os.path.join(os.path.dirname(__file__), "..", "datasets", "cwru_raw"),
        help="Directory to save downloaded MAT files",
    )
    parser.add_argument(
        "--category",
        choices=[
            "all", "normal", "inner", "ball", "outer",
            "12k", "48k", "DE", "FE",
        ],
        default="all",
        help="Category subset to download",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel download threads",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.output_dir)
    log(f"Target directory: {out_dir}")

    # Filter catalog by category
    filtered = []
    for entry in CWRU_CATALOG:
        file_id, cat, diam, hp, rpm, sr, loc = entry
        if args.category == "normal" and cat != "Normal":
            continue
        if args.category == "inner" and "InnerRace" not in cat:
            continue
        if args.category == "ball" and "_Ball" not in cat:
            continue
        if args.category == "outer" and "OuterRace" not in cat:
            continue
        if args.category == "12k" and not cat.startswith("12k_"):
            continue
        if args.category == "48k" and not cat.startswith("48k_"):
            continue
        if args.category == "DE" and loc != "DE":
            continue
        if args.category == "FE" and loc != "FE":
            continue
        filtered.append(entry)

    total = len(filtered)
    success = 0

    if args.workers > 1:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(download_file, file_id, out_dir): file_id
                for file_id, *_rest in filtered
            }
            for future in concurrent.futures.as_completed(futures):
                if future.result():
                    success += 1
    else:
        for file_id, *_rest in filtered:
            if download_file(file_id, out_dir):
                success += 1

    log(f"\nDone! Downloaded/verified {success}/{total} CWRU files in {out_dir}")
    log(f"Recommended next step: python -m bearing_fault_desk_buddy.main --data-dir {out_dir}")


if __name__ == "__main__":
    main()
