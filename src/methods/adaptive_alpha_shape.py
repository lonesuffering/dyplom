"""Method 4 (Proposed): Modified Adaptive Alpha-Shape with Hydro-LiDAR Filtering.

Implements the author's modified shoreline detection algorithm (Chapter 4.2):
1. Multi-criteria Hydro-LiDAR Point Filtering:
   - Estimates water mirror elevation Z_water from Class 9 / lowest ground returns.
   - Retains only true Ground (Class 2) returns above (Z_water + delta_z_shore) with
     dry-terrain laser intensity, removing overhanging canopy (Class 5) and littoral
     reed beds (Class 3 & misclassified wet ground returns).
2. Local Density-Adaptive Alpha Criterion:
   - Computes k-NN distance d_k(p) for each vertex via 2D cKDTree.
   - Replaces constant global alpha with triangle-adaptive threshold:
     alpha_local(T) = clip(alpha_scale * mean(d_k(v_a), d_k(v_b), d_k(v_c)), alpha_min, alpha_max).
   - Prevents shoreline leakage in sparse forest ground zones while preserving fine bays.
3. Topological & Morphological Regularization:
   - Preserves interior islands above minimum area and regularizes sawtooth triangle edges.
"""

from __future__ import annotations

import time
import numpy as np
from scipy.spatial import Delaunay, cKDTree
from shapely.geometry import MultiPolygon, Polygon

from src.domain.models import DetectionResult, LASClass, PointCloudData
from src.io.lidar_io import estimate_water_level
from src.methods.triangulation_utils import compute_triangle_circumradii, extract_cavity_polygon


def filter_true_land_points(
    cloud: PointCloudData,
    delta_z_shore_m: float = 0.24,
    min_land_intensity: float = 750.0,
) -> np.ndarray:
    """Filter point cloud to retain only genuine dry-land ground points around the shore."""
    water_z = (
        cloud.water_level_z
        if cloud.water_level_z is not None
        else estimate_water_level(cloud.z, cloud.classification, cloud.intensity)
    )

    is_ground = cloud.classification == LASClass.GROUND
    above_water = cloud.z >= (water_z + delta_z_shore_m)
    dry_reflectance = cloud.intensity >= min_land_intensity

    valid_land = is_ground & above_water & dry_reflectance
    return cloud.xy[valid_land]


def regularize_shoreline_polygon(
    poly: Polygon | MultiPolygon,
    buffer_smooth_m: float = 0.65,
    simplify_tol_m: float = 0.22,
    min_island_area_m2: float = 40.0,
) -> Polygon | MultiPolygon:
    """Smooth triangulation sawtooth artifacts while preserving islands and concavities."""
    if poly.is_empty:
        return poly

    # Morphological closing-opening in vector space + Douglas-Peucker simplification
    smoothed = poly.buffer(buffer_smooth_m).buffer(-buffer_smooth_m)
    simplified = smoothed.simplify(simplify_tol_m, preserve_topology=True)

    def _keep_valid_islands(p: Polygon) -> Polygon:
        holes = [ring for ring in p.interiors if Polygon(ring).area >= min_island_area_m2]
        return Polygon(p.exterior, holes)

    if isinstance(simplified, Polygon):
        return _keep_valid_islands(simplified)
    if isinstance(simplified, MultiPolygon):
        parts = [_keep_valid_islands(g) for g in simplified.geoms if g.area >= 200.0]
        parts.sort(key=lambda g: g.area, reverse=True)
        return parts[0] if parts else Polygon()
    return simplified


def detect_adaptive_alpha_shape(
    cloud: PointCloudData,
    k_neighbors: int = 12,
    alpha_scale: float = 1.65,
    alpha_min_m: float = 2.0,
    alpha_max_m: float = 8.5,
    delta_z_shore_m: float = 0.24,
    min_land_intensity: float = 750.0,
) -> DetectionResult:
    """Run the proposed Adaptive Alpha-Shape shoreline detection algorithm."""
    t0 = time.perf_counter()

    pts_xy = filter_true_land_points(
        cloud,
        delta_z_shore_m=delta_z_shore_m,
        min_land_intensity=min_land_intensity,
    )

    # 1. Estimate local point spacing via k-NN in 2D
    tree = cKDTree(pts_xy)
    dists, _ = tree.query(pts_xy, k=k_neighbors + 1)
    local_spacing = dists[:, -1]  # distance to k-th neighbor

    # 2. Delaunay triangulation & circumradii
    tri = Delaunay(pts_xy)
    radii = compute_triangle_circumradii(pts_xy, tri.simplices)

    # 3. Spatially adaptive threshold per triangle
    tri_spacing = np.mean(local_spacing[tri.simplices], axis=1)
    alpha_local = np.clip(alpha_scale * tri_spacing, alpha_min_m, alpha_max_m)

    raw_poly = extract_cavity_polygon(
        pts_xy,
        tri.simplices,
        is_water_triangle=(radii > alpha_local),
        bounds=cloud.bounds,
    )

    final_poly = regularize_shoreline_polygon(raw_poly)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return DetectionResult(
        method_name="Autorski Adaptive Alpha-Shape",
        dataset_name=cloud.name,
        polygon=final_poly,
        execution_time_ms=elapsed_ms,
        parameters={
            "k_neighbors": k_neighbors,
            "alpha_scale": alpha_scale,
            "alpha_min_m": alpha_min_m,
            "alpha_max_m": alpha_max_m,
            "delta_z_shore_m": delta_z_shore_m,
            "min_land_intensity": min_land_intensity,
        },
    )
