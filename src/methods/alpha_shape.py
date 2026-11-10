"""Method 3: Classical Fixed-Parameter Alpha-Shape shoreline detection."""

import time
import numpy as np
from scipy.spatial import Delaunay

from src.domain.models import DetectionResult, LASClass, PointCloudData
from src.methods.triangulation_utils import compute_triangle_circumradii, extract_cavity_polygon


def detect_classical_alpha_shape(
    cloud: PointCloudData,
    alpha_radius_m: float = 3.0,
) -> DetectionResult:
    """Detect shoreline using standard Alpha-Shape with a constant global alpha radius.

    Filters out high vegetation (Class 5) and water (Class 9), then extracts
    Delaunay cavity triangles with circumradius R > alpha_radius_m.
    """
    t0 = time.perf_counter()

    # Standard class filtering: keep Ground (2) and Low/Med Vegetation (3, 4)
    mask = np.isin(
        cloud.classification,
        [LASClass.GROUND, LASClass.LOW_VEGETATION, LASClass.MEDIUM_VEGETATION],
    )
    pts_xy = cloud.xy[mask]

    tri = Delaunay(pts_xy)
    radii = compute_triangle_circumradii(pts_xy, tri.simplices)

    poly = extract_cavity_polygon(
        pts_xy,
        tri.simplices,
        is_water_triangle=(radii > alpha_radius_m),
        bounds=cloud.bounds,
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return DetectionResult(
        method_name=f"Klasyczny Alpha-Shape (α={alpha_radius_m:.1f}m)",
        dataset_name=cloud.name,
        polygon=poly,
        execution_time_ms=elapsed_ms,
        parameters={"alpha_radius_m": alpha_radius_m},
    )
