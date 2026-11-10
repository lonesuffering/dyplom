"""Vectorized Delaunay triangulation and circumradius geometry helpers."""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay
from shapely import make_valid, polygons, unary_union
from shapely.geometry import MultiPolygon, Polygon


def compute_triangle_circumradii(points_xy: np.ndarray, simplices: np.ndarray) -> np.ndarray:
    """Compute the circumradius R = (a * b * c) / (4 * Area) for each Delaunay triangle."""
    pts = points_xy[simplices]  # shape: (N_tri, 3, 2)
    a = np.linalg.norm(pts[:, 1] - pts[:, 0], axis=1)
    b = np.linalg.norm(pts[:, 2] - pts[:, 1], axis=1)
    c = np.linalg.norm(pts[:, 0] - pts[:, 2], axis=1)

    # Cross product in 2D gives 2 * Area
    double_area = np.abs(
        (pts[:, 1, 0] - pts[:, 0, 0]) * (pts[:, 2, 1] - pts[:, 0, 1])
        - (pts[:, 2, 0] - pts[:, 0, 0]) * (pts[:, 1, 1] - pts[:, 0, 1])
    )
    double_area = np.maximum(double_area, 1e-12)
    return (a * b * c) / (2.0 * double_area)


def extract_cavity_polygon(
    points_xy: np.ndarray,
    simplices: np.ndarray,
    is_water_triangle: np.ndarray,
    bounds: tuple[float, float, float, float],
    min_water_area_m2: float = 200.0,
    min_island_area_m2: float = 40.0,
    border_margin_m: float = 3.0,
) -> Polygon | MultiPolygon:
    """Construct the water body polygon from Delaunay triangles classified as water voids.

    Excludes outer bounding-box border artifacts, selects water bodies above `min_water_area_m2`,
    and preserves genuine islands above `min_island_area_m2`.
    """
    min_x, min_y, max_x, max_y = bounds
    tri_coords = points_xy[simplices]  # (N_tri, 3, 2)
    tri_centroids = np.mean(tri_coords, axis=1)

    # Exclude triangles touching the outer tile border
    inside_border = (
        (tri_centroids[:, 0] > min_x + border_margin_m)
        & (tri_centroids[:, 0] < max_x - border_margin_m)
        & (tri_centroids[:, 1] > min_y + border_margin_m)
        & (tri_centroids[:, 1] < max_y - border_margin_m)
    )

    valid_mask = is_water_triangle & inside_border
    selected_coords = tri_coords[valid_mask]
    if len(selected_coords) == 0:
        return Polygon()

    tri_polys = polygons(selected_coords)
    merged = unary_union(tri_polys)

    def _clean_single_polygon(poly: Polygon) -> Polygon:
        # Keep only interior holes (islands) whose area exceeds min_island_area_m2
        kept_holes = [
            ring for ring in poly.interiors if Polygon(ring).area >= min_island_area_m2
        ]
        cleaned = make_valid(Polygon(poly.exterior, kept_holes))
        if isinstance(cleaned, Polygon):
            return cleaned
        if isinstance(cleaned, MultiPolygon):
            return max(cleaned.geoms, key=lambda g: g.area)
        return Polygon(poly.exterior)

    if isinstance(merged, Polygon):
        if merged.area < min_water_area_m2:
            return Polygon()
        return _clean_single_polygon(merged)

    if isinstance(merged, MultiPolygon):
        valid_parts = [
            _clean_single_polygon(p) for p in merged.geoms if p.area >= min_water_area_m2
        ]
        if not valid_parts:
            return Polygon()
        # Return largest water body or MultiPolygon if multiple major bodies exist
        valid_parts.sort(key=lambda p: p.area, reverse=True)
        return valid_parts[0] if len(valid_parts) == 1 else MultiPolygon(valid_parts[:1])

    return Polygon()
