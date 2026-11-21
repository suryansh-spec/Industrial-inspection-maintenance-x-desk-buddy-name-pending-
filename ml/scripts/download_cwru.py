"""Automated CWRU (Case Western Reserve University) Bearing Dataset Downloader.

Downloads the benchmark vibration MAT files directly from Case Western Reserve University:
https://engineering.case.edu/bearingdatacenter
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Dict, List, Tuple
import urllib.request
from scipy.io import loadmat

# Canonical CWRU dataset files catalog
# Format: (file_id, category, fault_diameter, load_hp, rpm)
CWRU_CATALOG: List[Tuple[str, str, str, int, int]] = [
    # Normal Baseline Data
    ("97", "Normal", "0.000", 0, 1797),
    ("98", "Normal", "0.000", 1, 1772),
    ("99", "Normal", "0.000", 2, 1750),
    ("100", "Normal", "0.000", 3, 1730),

    # 12k Drive End Bearing Fault - Inner Race (0.007", 0.014", 0.021", 0.028")
    ("105", "12k_DE_InnerRace", "0.007", 0, 1797),
    ("106", "12k_DE_InnerRace", "0.007", 1, 1772),
    ("107", "12k_DE_InnerRace", "0.007", 2, 1750),
    ("108", "12k_DE_InnerRace", "0.007", 3, 1730),
    ("169", "12k_DE_InnerRace", "0.014", 0, 1797),
    ("170", "12k_DE_InnerRace", "0.014", 1, 1772),
    ("171", "12k_DE_InnerRace", "0.014", 2, 1750),
    ("172", "12k_DE_InnerRace", "0.014", 3, 1730),
    ("209", "12k_DE_InnerRace", "0.021", 0, 1797),
    ("210", "12k_DE_InnerRace", "0.021", 1, 1772),
    ("211", "12k_DE_InnerRace", "0.021", 2, 1750),
    ("212", "12k_DE_InnerRace", "0.021", 3, 1730),

    # 12k Drive End Bearing Fault - Ball (0.007", 0.014", 0.021")
    ("118", "12k_DE_Ball", "0.007", 0, 1797),
    ("119", "12k_DE_Ball", "0.007", 1, 1772),
    ("120", "12k_DE_Ball", "0.007", 2, 1750),
    ("121", "12k_DE_Ball", "0.007", 3, 1730),
    ("185", "12k_DE_Ball", "0.014", 0, 1797),
    ("186", "12k_DE_Ball", "0.014", 1, 1772),
    ("187", "12k_DE_Ball", "0.014", 2, 1750),
    ("188", "12k_DE_Ball", "0.014", 3, 1730),
    ("222", "12k_DE_Ball", "0.021", 0, 1797),
    ("223", "12k_DE_Ball", "0.021", 1, 1772),
    ("224", "12k_DE_Ball", "0.021", 2, 1750),
    ("225", "12k_DE_Ball", "0.021", 3, 1730),

    # 12k Drive End Bearing Fault - Outer Race Centered (0.007", 0.014", 0.021")
    ("130", "12k_DE_OuterRace6", "0.007", 0, 1797),
    ("131", "12k_DE_OuterRace6", "0.007", 1, 1772),
    ("132", "12k_DE_OuterRace6", "0.007", 2, 1750),
    ("133", "12k_DE_OuterRace6", "0.007", 3, 1730),
    ("197", "12k_DE_OuterRace6", "0.014", 0, 1797),
    ("198", "12k_DE_OuterRace6", "0.014", 1, 1772),
    ("199", "12k_DE_OuterRace6", "0.014", 2, 1750),
    ("200", "12k_DE_OuterRace6", "0.014", 3, 1730),
    ("234", "12k_DE_OuterRace6", "0.021", 0, 1797),
    ("235", "12k_DE_OuterRace6", "0.021", 1, 1772),
    ("236", "12k_DE_OuterRace6", "0.021", 2, 1750),
    ("237", "12k_DE_OuterRace6", "0.021", 3, 1730),
]

BASE_URL = "https://engineering.case.edu/sites/default/files"


def download_file(file_id: str, out_dir: str) -> bool:
    """Download a single CWRU .mat file and verify its contents."""
    os.makedirs(out_dir, exist_ok=True)
    filename = f"{file_id}.mat"
    target_path = os.path.join(out_dir, filename)

    if os.path.isfile(target_path) and os.path.getsize(target_path) > 10000:
        print(f"[{file_id}] Already downloaded ({os.path.getsize(target_path):,} bytes).")
        return True

    url = f"{BASE_URL}/{filename}"
    print(f"[{file_id}] Downloading from {url}...")
    try:
        urllib.request.urlretrieve(url, target_path)
        # Verify MAT integrity
        data = loadmat(target_path)
        keys = [k for k in data.keys() if not k.startswith("__")]
        print(f"[{file_id}] OK! Size: {os.path.getsize(target_path):,} bytes | Keys: {keys[:2]}")
        return True
    except Exception as exc:
        print(f"[{file_id}] Download failed: {exc}", file=sys.stderr)
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
        choices=["all", "normal", "inner", "ball", "outer"],
        default="all",
        help="Category subset to download",
    )
    args = parser.parse_args()

    out_dir = os.path.abspath(args.output_dir)
    print(f"Target directory: {out_dir}")

    total = 0
    success = 0
    for file_id, cat, diam, hp, rpm in CWRU_CATALOG:
        if args.category == "normal" and cat != "Normal":
            continue
        if args.category == "inner" and "InnerRace" not in cat:
            continue
        if args.category == "ball" and "Ball" not in cat:
            continue
        if args.category == "outer" and "OuterRace" not in cat:
            continue

        total += 1
        if download_file(file_id, out_dir):
            success += 1

    print(f"\nDone! Downloaded/verified {success}/{total} CWRU files in {out_dir}")


if __name__ == "__main__":
    main()
