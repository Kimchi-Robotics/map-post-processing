#!/usr/bin/env python3
"""
map_post_processing.py - ROS 2 occupancy map cleaning (PGM/PNG)

Removes isolated points (e.g. operator's legs during teleop)
while preserving thin walls and map structure.

Usage:
    python3 map_post_processing.py map.png
    python3 map_post_processing.py map.png --min-area 50 --output map_clean.png
    python3 map_post_processing.py map.png --preview  # Show before/after without saving
"""

import argparse
import cv2
import numpy as np
from pathlib import Path


def load_map(path: str) -> np.ndarray:
    """Load the map in grayscale."""
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise FileNotFoundError(f"Could not load: {path}")
    return img


def binarize_obstacles(
    gray: np.ndarray,
    free_thresh: int = 230,
    occupied_thresh: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Separates the map into an obstacle mask and an unknown zone mask.

    In standard ROS maps:
      - 254 (white) = free
      - 0   (black) = occupied
      - 205 (gray)  = unknown

    Returns:
        obstacles: binary mask where 255 = obstacle
        unknown:   binary mask where 255 = unknown
    """
    obstacles = (gray < occupied_thresh).astype(np.uint8) * 255
    unknown = ((gray > occupied_thresh) & (gray < free_thresh)).astype(np.uint8) * 255
    return obstacles, unknown


def remove_small_blobs(
    mask: np.ndarray,
    min_area: int = 30,
) -> np.ndarray:
    """
    Removes blobs (contours) with area smaller than min_area pixels.
    This is what removes legs without affecting thin walls.
    """
    cleaned = mask.copy()
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    removed = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            cv2.drawContours(cleaned, [cnt], -1, 0, thickness=cv2.FILLED)
            removed += 1

    print(f"  Contours found: {len(contours)}")
    print(f"  Blobs removed (area < {min_area}px): {removed}")
    return cleaned


def reconstruct_map(
    original: np.ndarray,
    clean_obstacles: np.ndarray,
    unknown: np.ndarray,
    free_value: int = 254,
    occupied_value: int = 0,
    unknown_value: int = 205,
) -> np.ndarray:
    """
    Reconstructs the map with standard ROS values.
    """
    result = np.full_like(original, free_value)
    result[unknown > 0] = unknown_value
    result[clean_obstacles > 0] = occupied_value
    return result


def clean_map(
    input_path: str,
    min_area: int = 30,
    free_thresh: int = 230,
    occupied_thresh: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Complete cleaning pipeline.

    Returns:
        (original, cleaned) for comparison
    """
    print(f"Loading map: {input_path}")
    original = load_map(input_path)
    print(f"  Size: {original.shape[1]}x{original.shape[0]} px")

    print("Binarizing obstacles...")
    obstacles, unknown = binarize_obstacles(original, free_thresh, occupied_thresh)

    print("Removing small blobs (area filtering)...")
    filtered = remove_small_blobs(obstacles, min_area)

    print("Reconstructing map...")
    cleaned = reconstruct_map(original, filtered, unknown)

    return original, cleaned


def create_comparison(original: np.ndarray, cleaned: np.ndarray) -> np.ndarray:
    """Creates a side-by-side image + diff for visualization."""
    # Diff: red = what was removed
    diff_color = cv2.cvtColor(original, cv2.COLOR_GRAY2BGR)
    removed = (original < 50) & (cleaned >= 200)  # was obstacle, now free
    diff_color[removed] = [0, 0, 255]  # Red = removed

    orig_color = cv2.cvtColor(original, cv2.COLOR_GRAY2BGR)
    clean_color = cv2.cvtColor(cleaned, cv2.COLOR_GRAY2BGR)

    # Labels (text overlays)
    font = cv2.FONT_HERSHEY_SIMPLEX
    h = original.shape[0]
    cv2.putText(orig_color, "Original", (10, 30), font, 0.5, (0, 0, 255), 1)
    cv2.putText(clean_color, "Clean", (10, 30), font, 0.5, (0, 180, 0), 1)
    cv2.putText(diff_color, "Removed (red)", (10, 30), font, 0.5, (0, 0, 255), 1)

    comparison = np.hstack([orig_color, clean_color, diff_color])
    return comparison


def main():
    parser = argparse.ArgumentParser(
        description="Cleans ROS occupancy maps by removing isolated points"
    )
    parser.add_argument("input", help="Path to the map (PNG/PGM)")
    parser.add_argument(
        "-o", "--output",
        help="Output path (default: <input>_clean.<ext>)",
    )
    parser.add_argument(
        "--min-area",
        type=int,
        default=30,
        help="Minimum area in pixels to keep an obstacle (default: 30)",
    )
    parser.add_argument(
        "--free-thresh",
        type=int,
        default=230,
        help="Threshold for free space (default: 230)",
    )
    parser.add_argument(
        "--occupied-thresh",
        type=int,
        default=50,
        help="Threshold for occupied space (default: 50)",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Generate before/after comparison image",
    )

    args = parser.parse_args()

    original, cleaned = clean_map(
        args.input,
        min_area=args.min_area,
        free_thresh=args.free_thresh,
        occupied_thresh=args.occupied_thresh,
    )

    # Output path
    input_path = Path(args.input)
    if args.output:
        output_path = args.output
    else:
        output_path = str(input_path.parent / f"{input_path.stem}_clean{input_path.suffix}")

    cv2.imwrite(output_path, cleaned)
    print(f"\nClean map saved to: {output_path}")

    if args.preview:
        comp = create_comparison(original, cleaned)
        comp_path = str(input_path.parent / f"{input_path.stem}_comparison.png")
        cv2.imwrite(comp_path, comp)
        print(f"Comparison saved to: {comp_path}")

    print("Done!")


if __name__ == "__main__":
    main()