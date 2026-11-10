"""Quantitative shoreline accuracy metrics against reference BDOT10k polygons."""

from __future__ import annotations

import numpy as np
import shapely
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon

from src.domain.models import DetectionResult, MetricsResult


def _sample_boundary_points(boundary: LineString | MultiLineString, step_m: float = 0.5) -> np.ndarray:
    """Sample equidistant points along a polygon boundary (including inner island rings)."""
    lines = list(boundary.geoms) if isinstance(boundary, MultiLineString) else [boundary]
    coords_list = []
    for line in lines:
        length = line.length
        if length <= 0:
            continue
        num_samples = max(int(np.ceil(length / step_m)), 8)
        distances = np.linspace(0, length, num_samples, endpoint=False)
        pts = [line.interpolate(d) for d in distances]
        coords_list.append(np.array([(p.x, p.y) for p in pts]))
    if not coords_list:
        return np.empty((0, 2))
    return np.vstack(coords_list)


def evaluate_detection(
    result: DetectionResult,
    reference_poly: Polygon | MultiPolygon,
) -> MetricsResult:
    """Compute IoU, F1, Hausdorff distance, and Boundary RMSE relative to BDOT10k."""
    det = shapely.make_valid(result.polygon)
    ref = shapely.make_valid(reference_poly)

    if det.is_empty or ref.is_empty:
        return MetricsResult(
            dataset_name=result.dataset_name,
            method_name=result.method_name,
            iou=0.0,
            f1_score=0.0,
            hausdorff_dist_m=float("inf"),
            rmse_boundary_m=float("inf"),
            area_detected_m2=0.0,
            area_reference_m2=float(ref.area),
            area_rel_error_pct=-100.0,
            execution_time_ms=result.execution_time_ms,
        )

    inter_area = float(det.intersection(ref).area)
    union_area = float(det.union(ref).area)
    det_area = float(det.area)
    ref_area = float(ref.area)

    iou = inter_area / union_area if union_area > 0 else 0.0
    f1 = (2.0 * inter_area) / (det_area + ref_area) if (det_area + ref_area) > 0 else 0.0
    rel_err_pct = ((det_area - ref_area) / ref_area) * 100.0 if ref_area > 0 else 0.0

    # Hausdorff distance between boundaries (sensitive to worst-case excursions/leakage)
    hausdorff = float(det.boundary.hausdorff_distance(ref.boundary))

    # Bidirectional Boundary RMSE (sampled every 0.5m along shoreline)
    pts_det = _sample_boundary_points(det.boundary, step_m=0.5)
    pts_ref = _sample_boundary_points(ref.boundary, step_m=0.5)

    d_det_to_ref = shapely.distance(shapely.points(pts_det[:, 0], pts_det[:, 1]), ref.boundary)
    d_ref_to_det = shapely.distance(shapely.points(pts_ref[:, 0], pts_ref[:, 1]), det.boundary)
    all_sq_errors = np.concatenate([d_det_to_ref**2, d_ref_to_det**2])
    rmse = float(np.sqrt(np.mean(all_sq_errors)))

    return MetricsResult(
        dataset_name=result.dataset_name,
        method_name=result.method_name,
        iou=iou,
        f1_score=f1,
        hausdorff_dist_m=hausdorff,
        rmse_boundary_m=rmse,
        area_detected_m2=det_area,
        area_reference_m2=ref_area,
        area_rel_error_pct=rel_err_pct,
        execution_time_ms=result.execution_time_ms,
    )
