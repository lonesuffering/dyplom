"""Method 2: Raster Grid / DSM Void & Elevation Segmentation."""

import time
import numpy as np
from scipy.ndimage import binary_closing, binary_opening, label
from shapely import box, unary_union
from shapely.geometry import Polygon

from src.domain.models import DetectionResult, LASClass, PointCloudData


def detect_grid_contour(
    cloud: PointCloudData,
    cell_size_m: float = 2.0,
) -> DetectionResult:
    """Detect shoreline by rasterizing point cloud density/elevation onto a 2D regular grid.

    Simulates standard GIS raster workflows (DSM/point-density thresholding).
    Susceptible to grid staircase artifacts, overhanging canopy occlusion, and sparse ground voids.
    """
    t0 = time.perf_counter()

    min_x, min_y, max_x, max_y = cloud.bounds
    nx = int(np.ceil((max_x - min_x) / cell_size_m))
    ny = int(np.ceil((max_y - min_y) / cell_size_m))

    # Exclude only explicit Class 9 water points
    non_water = cloud.classification != LASClass.WATER
    x_nw = cloud.x[non_water]
    y_nw = cloud.y[non_water]

    ix = np.clip(((x_nw - min_x) / cell_size_m).astype(int), 0, nx - 1)
    iy = np.clip(((y_nw - min_y) / cell_size_m).astype(int), 0, ny - 1)

    land_grid = np.zeros((ny, nx), dtype=bool)
    land_grid[iy, ix] = True

    # Close 1-cell gaps on land, then invert to find water cavity
    land_closed = binary_closing(land_grid, structure=np.ones((2, 2), dtype=bool))
    water_grid = ~land_closed

    # Remove border cells and small isolated speckles
    water_grid[0, :] = False
    water_grid[-1, :] = False
    water_grid[:, 0] = False
    water_grid[:, -1] = False
    water_grid = binary_opening(water_grid, structure=np.ones((2, 2), dtype=bool))

    labeled, num_features = label(water_grid)
    if num_features == 0:
        return DetectionResult(
            method_name="Metoda rastrowa (Grid 2m)",
            dataset_name=cloud.name,
            polygon=Polygon(),
            execution_time_ms=(time.perf_counter() - t0) * 1000.0,
            parameters={"cell_size_m": cell_size_m},
        )

    # Keep the largest connected water component
    counts = np.bincount(labeled.ravel())
    counts[0] = 0
    best_label = int(np.argmax(counts))
    iy_w, ix_w = np.where(labeled == best_label)

    x0 = min_x + ix_w * cell_size_m
    y0 = min_y + iy_w * cell_size_m
    cells = box(x0, y0, x0 + cell_size_m, y0 + cell_size_m)
    merged = unary_union(cells)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return DetectionResult(
        method_name="Metoda rastrowa (Grid 2m)",
        dataset_name=cloud.name,
        polygon=merged if isinstance(merged, Polygon) else Polygon(),
        execution_time_ms=elapsed_ms,
        parameters={"cell_size_m": cell_size_m},
    )
