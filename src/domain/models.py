"""Domain data models for LiDAR point clouds, shoreline detection results, and evaluation metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np
from shapely.geometry import Polygon, MultiPolygon


class LASClass:
    """Standard ASPRS LAS 1.4 point classification codes (used in Polish GUGiK ISOK data)."""
    CREATED_NEVER_CLASSIFIED = 0
    UNCLASSIFIED = 1
    GROUND = 2              # Grunt
    LOW_VEGETATION = 3      # Roślinność niska (0 - 0.4 m, np. trzcina, trawa)
    MEDIUM_VEGETATION = 4   # Roślinność średnia (0.4 - 2.0 m, krzewy)
    HIGH_VEGETATION = 5     # Roślinność wysoka (> 2.0 m, drzewa)
    BUILDING = 6            # Budynki
    LOW_POINT_NOISE = 7     # Szum niski
    WATER = 9               # Woda


@dataclass
class PointCloudData:
    """Container for 3D LiDAR point cloud attributes in EPSG:2180."""
    name: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    classification: np.ndarray
    intensity: np.ndarray
    crs_epsg: int = 2180
    water_level_z: Optional[float] = None

    @property
    def num_points(self) -> int:
        return len(self.x)

    @property
    def xy(self) -> np.ndarray:
        return np.column_stack((self.x, self.y))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Return (min_x, min_y, max_x, max_y)."""
        return (
            float(np.min(self.x)),
            float(np.min(self.y)),
            float(np.max(self.x)),
            float(np.max(self.y)),
        )


@dataclass
class DetectionResult:
    """Output of a shoreline detection algorithm."""
    method_name: str
    dataset_name: str
    polygon: Polygon | MultiPolygon
    execution_time_ms: float
    parameters: Dict[str, float | int | str] = field(default_factory=dict)


@dataclass
class MetricsResult:
    """Quantitative comparison between detected shoreline and reference BDOT10k polygon."""
    dataset_name: str
    method_name: str
    iou: float                      # Intersection over Union [0..1]
    f1_score: float                 # Dice / F1 coefficient [0..1]
    hausdorff_dist_m: float         # Maximum boundary deviation [m]
    rmse_boundary_m: float          # Root Mean Square Error of shoreline boundary [m]
    area_detected_m2: float         # Detected water surface area [m^2]
    area_reference_m2: float        # Reference BDOT10k water surface area [m^2]
    area_rel_error_pct: float       # Relative area error [%]
    execution_time_ms: float        # Processing runtime [ms]
