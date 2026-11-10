"""Baseline Method 1: Convex Hull shoreline detection."""

import time
import numpy as np
from scipy.spatial import Delaunay
from shapely.geometry import MultiPoint, Polygon

from src.domain.models import DetectionResult, LASClass, PointCloudData
from src.methods.triangulation_utils import compute_triangle_circumradii, extract_cavity_polygon


def detect_convex_hull(
    cloud: PointCloudData,
    cavity_radius_m: float = 3.5,
) -> DetectionResult:
    """Detect water body boundary using the Convex Hull of water/cavity points.

    Represents the simplest geometric baseline: fast and parameter-light,
    but unable to represent concave bays, peninsulas, or internal islands.
    """
    t0 = time.perf_counter()

    # Use non-water classes to locate the main water void, or Class 9 water points
    non_water = cloud.classification != LASClass.WATER
    pts_xy = cloud.xy[non_water]

    tri = Delaunay(pts_xy)
    radii = compute_triangle_circumradii(pts_xy, tri.simplices)
    raw_cavity = extract_cavity_polygon(
        pts_xy,
        tri.simplices,
        radii > cavity_radius_m,
        cloud.bounds,
    )

    if raw_cavity.is_empty:
        water_pts = cloud.xy[cloud.classification == LASClass.WATER]
        hull_poly = MultiPoint(water_pts).convex_hull if len(water_pts) >= 3 else Polygon()
    else:
        hull_poly = raw_cavity.convex_hull

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return DetectionResult(
        method_name="Convex Hull (Baseline)",
        dataset_name=cloud.name,
        polygon=hull_poly if isinstance(hull_poly, Polygon) else Polygon(),
        execution_time_ms=elapsed_ms,
        parameters={"cavity_radius_m": cavity_radius_m},
    )
