"""Utilities and presets for working with real GUGiK (Geoportal) LiDAR and BDOT10k data.

Provides bounding boxes (in EPSG:2180 / PUWG 1992) for recommended test water bodies
in the Szczecin metropolitan area (województwo zachodniopomorskie, powiat m. Szczecin / policki)
and a spatial cropping tool for large GUGiK .laz tiles and BDOT10k OT_PTWP_A layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import geopandas as gpd
import laspy
import numpy as np
from shapely.geometry import box

from src.domain.models import PointCloudData
from src.io.lidar_io import estimate_water_level, save_polygon, write_point_cloud


@dataclass(frozen=True)
class SzczecinReservoirPreset:
    """Recommended real-world water bodies near Szczecin for thesis evaluation."""
    id: str
    name_pl: str
    description: str
    teryt_powiat: str
    bbox_epsg2180: tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)


SZCZECIN_PRESETS: list[SzczecinReservoirPreset] = [
    SzczecinReservoirPreset(
        id="jezioro_szmaragdowe",
        name_pl="Jezioro Szmaragdowe (Szczecin Zdroje)",
        description="Sztuczne jezioro pokopalniane w Puszczy Bukowej o stromych, zalesionych brzegach i charakterystycznym kształcie.",
        teryt_powiat="3262",
        bbox_epsg2180=(213950.0, 617650.0, 214550.0, 618150.0),
    ),
    SzczecinReservoirPreset(
        id="jezioro_glebokie",
        name_pl="Jezioro Głębokie (Szczecin Pogodno/Głębokie)",
        description="Jezioro rynnowe o wydłużonym, nieregularnym kształcie z zatokami, pomostami oraz pasem roślinności szuwarowej.",
        teryt_powiat="3262",
        bbox_epsg2180=(205300.0, 626900.0, 206500.0, 628300.0),
    ),
    SzczecinReservoirPreset(
        id="staw_brodowski",
        name_pl="Staw Brodowski / Rusałka (Szczecin)",
        description="Mniejszy zbiornik miejski o urozmaiconej linii brzegowej, wyspie i zadrzewieniu przybrzeżnym.",
        teryt_powiat="3262",
        bbox_epsg2180=(209700.0, 624400.0, 210450.0, 624850.0),
    ),
]


def crop_real_gugik_dataset(
    laz_path: str | Path,
    bdot10k_ptwp_path: str | Path,
    bbox_epsg2180: tuple[float, float, float, float],
    output_dir: str | Path,
    dataset_name: str,
) -> tuple[Path, Path]:
    """Crop a downloaded GUGiK .laz/.las file and BDOT10k OT_PTWP_A vector layer to a target bounding box."""
    min_x, min_y, max_x, max_y = bbox_epsg2180
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read and crop LAS/LAZ point cloud
    las = laspy.read(laz_path)
    x = np.asarray(las.x, dtype=np.float64)
    y = np.asarray(las.y, dtype=np.float64)
    mask = (x >= min_x) & (x <= max_x) & (y >= min_y) & (y <= max_y)
    if not np.any(mask):
        raise ValueError(f"No LiDAR points found inside bbox {bbox_epsg2180} in {laz_path}")

    z = np.asarray(las.z, dtype=np.float64)[mask]
    cls = np.asarray(las.classification, dtype=np.uint8)[mask]
    intensity = np.asarray(las.intensity, dtype=np.float32)[mask]

    cloud = PointCloudData(
        name=dataset_name,
        x=x[mask],
        y=y[mask],
        z=z,
        classification=cls,
        intensity=intensity,
        water_level_z=estimate_water_level(z, cls, intensity),
    )
    cropped_las_path = write_point_cloud(cloud, out_dir / f"{dataset_name}.las")

    # 2. Read and crop BDOT10k surface water layer (OT_PTWP_A)
    roi_box = box(min_x, min_y, max_x, max_y)
    gdf = gpd.read_file(bdot10k_ptwp_path, bbox=roi_box)
    if gdf.crs is not None and gdf.crs.to_epsg() != 2180:
        gdf = gdf.to_crs(epsg=2180)
    clipped_geom = gdf.geometry.intersection(roi_box).unary_union
    cropped_ref_path = save_polygon(
        clipped_geom,
        out_dir / f"{dataset_name}_BDOT10k.geojson",
        crs_epsg=2180,
        properties={"id": dataset_name, "source": "GUGiK_BDOT10k_OT_PTWP_A"},
    )
    return cropped_las_path, cropped_ref_path
