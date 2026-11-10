"""I/O utilities for reading/writing ASPRS LAS/LAZ point clouds and BDOT10k reference polygons."""

from __future__ import annotations

from pathlib import Path
import geopandas as gpd
import laspy
import numpy as np
from shapely.geometry import Polygon, MultiPolygon

from src.domain.models import LASClass, PointCloudData


def estimate_water_level(
    z: np.ndarray,
    classification: np.ndarray,
    intensity: np.ndarray,
) -> float:
    """Estimate the water surface elevation Z_water from Class 9 (Water) or lowest ground returns."""
    water_mask = classification == LASClass.WATER
    if np.sum(water_mask) >= 10:
        return float(np.median(z[water_mask]))

    ground_mask = classification == LASClass.GROUND
    if np.sum(ground_mask) > 0:
        return float(np.percentile(z[ground_mask], 2.0))

    return float(np.percentile(z, 2.0))


def read_point_cloud(path: str | Path, name: str | None = None) -> PointCloudData:
    """Read a LAS or LAZ file into a PointCloudData object."""
    file_path = Path(path)
    las = laspy.read(file_path)

    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    z = np.asarray(las.z, dtype=np.float64)
    classification = np.asarray(las.classification, dtype=np.uint8)
    intensity = np.asarray(las.intensity, dtype=np.float32)

    water_z = estimate_water_level(z, classification, intensity)
    return PointCloudData(
        name=name or file_path.stem,
        x=x,
        y=y,
        z=z,
        classification=classification,
        intensity=intensity,
        water_level_z=water_z,
    )


def write_point_cloud(data: PointCloudData, path: str | Path) -> Path:
    """Write a PointCloudData instance to an ASPRS LAS 1.4 file."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    header = laspy.LasHeader(point_format=6, version="1.4")
    header.offsets = [np.min(data.x), np.min(data.y), np.min(data.z)]
    header.scales = [0.001, 0.001, 0.001]

    las = laspy.LasData(header)
    las.x = data.x
    las.y = data.y
    las.z = data.z
    las.classification = data.classification.astype(np.uint8)
    las.intensity = np.clip(data.intensity, 0, 65535).astype(np.uint16)

    las.write(file_path)
    return file_path


def save_polygon(
    polygon: Polygon | MultiPolygon,
    path: str | Path,
    crs_epsg: int = 2180,
    properties: dict | None = None,
) -> Path:
    """Save a Shapely Polygon/MultiPolygon to GeoJSON, GeoPackage, or Shapefile."""
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(properties or {})
    record["geometry"] = polygon
    gdf = gpd.GeoDataFrame([record], crs=f"EPSG:{crs_epsg}")
    gdf.to_file(file_path)
    return file_path


def load_polygon(path: str | Path) -> Polygon | MultiPolygon:
    """Load a reference water body polygon (e.g., BDOT10k OT_PTWP_A) from vector file."""
    gdf = gpd.read_file(path)
    geom = gdf.geometry.unary_union
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise ValueError(f"Expected Polygon or MultiPolygon in {path}, got {type(geom)}")
    return geom
