"""Automated downloader and extractor for real GUGiK LiDAR (.laz) and BDOT10k data in Szczecin.

Builds clean, spatially-thinned ASPRS LAS 1.4 point clouds and reference BDOT10k (OT_PTWP_A)
polygons in EPSG:2180 from official 2023 GUGiK ISOK tiles (`80222_*`) for Szczecin:
1. GUGiK_1_Jezioro_Szmaragdowe (Szczecin Zdroje / Puszcza Bukowa, BDOT10k idx=96)
2. GUGiK_2_Staw_Brodowski (Szczecin Niebuszewo / Drzetowo, BDOT10k idx=82)
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import geopandas as gpd
import laspy
import numpy as np

from src.domain.models import LASClass, PointCloudData
from src.io.lidar_io import estimate_water_level, save_polygon, write_point_cloud


def thin_point_cloud(
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    c: np.ndarray,
    i: np.ndarray,
    grid_ground_m: float = 0.65,
    grid_other_m: float = 2.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Perform 2D spatial grid thinning to preserve shoreline geometry while keeping LAS files compact."""
    g_mask = c == LASClass.GROUND
    o_mask = np.isin(
        c,
        [
            LASClass.LOW_VEGETATION,
            LASClass.MEDIUM_VEGETATION,
            LASClass.HIGH_VEGETATION,
            LASClass.WATER,
        ],
    )

    def _grid_sample(xm, ym, zm, cm, im, step: float):
        if len(xm) == 0:
            return xm, ym, zm, cm, im
        gx = np.floor(xm / step).astype(np.int64)
        gy = np.floor(ym / step).astype(np.int64)
        keys = gx * 10_000_000 + gy
        _, idx = np.unique(keys, return_index=True)
        return xm[idx], ym[idx], zm[idx], cm[idx], im[idx]

    xg, yg, zg, cg, ig = _grid_sample(
        x[g_mask], y[g_mask], z[g_mask], c[g_mask], i[g_mask], grid_ground_m
    )
    xo, yo, zo, co, io = _grid_sample(
        x[o_mask], y[o_mask], z[o_mask], c[o_mask], i[o_mask], grid_other_m
    )
    return (
        np.concatenate([xg, xo]),
        np.concatenate([yg, yo]),
        np.concatenate([zg, zo]),
        np.concatenate([cg, co]),
        np.concatenate([ig, io]),
    )


def build_real_szczecin_datasets(base_dir: str | Path = PROJECT_ROOT) -> list[tuple[Path, Path]]:
    """Build cropped & thinned real GUGiK LiDAR datasets from downloaded raw tiles in data/raw/."""
    root = Path(base_dir).resolve()
    raw_dir = root / "data" / "raw"
    real_dir = root / "data" / "real"
    real_dir.mkdir(parents=True, exist_ok=True)

    # Clean up any old unthinned files in data/real
    for old_f in real_dir.glob("Real_*"):
        old_f.unlink()

    ptwp_shp = raw_dir / "bdot10k_3262" / "PL.PZGiK.339.BDOT10k.3262__OT_PTWP_A.shp"
    if not ptwp_shp.exists():
        raise FileNotFoundError(f"Brak pliku BDOT10k: {ptwp_shp}")

    gdf = gpd.read_file(ptwp_shp)
    if gdf.crs is not None and gdf.crs.to_epsg() != 2180:
        gdf = gdf.to_crs(epsg=2180)

    configs = [
        {
            "name": "GUGiK_1_Jezioro_Szmaragdowe",
            "bdot_idx": 96,
            "laz_files": [
                "80222_1534825_N-33-90-C-c-4-2-2-2.laz",
                "80222_1536197_N-33-90-C-d-3-1-1-1.laz",
            ],
            "margin_m": 35.0,
        },
        {
            "name": "GUGiK_2_Staw_Brodowski",
            "bdot_idx": 82,
            "laz_files": [
                "80222_1535608_N-33-90-C-a-4-1-1-3.laz",
            ],
            "margin_m": 35.0,
        },
    ]

    saved_pairs: list[tuple[Path, Path]] = []
    for cfg in configs:
        name = cfg["name"]
        poly = gdf.loc[cfg["bdot_idx"]].geometry
        minx, miny, maxx, maxy = poly.bounds
        m = cfg["margin_m"]

        xs, ys, zs, cs, ints = [], [], [], [], []
        for fn in cfg["laz_files"]:
            laz_path = raw_dir / fn
            las = laspy.read(laz_path)
            lx = np.asarray(las.x, dtype=np.float64)
            ly = np.asarray(las.y, dtype=np.float64)
            lc = np.asarray(las.classification, dtype=np.uint8)
            mask = (
                (lx >= minx - m)
                & (lx <= maxx + m)
                & (ly >= miny - m)
                & (ly <= maxy + m)
                & (lc != 12)  # Exclude overlap class 12
            )
            xs.append(lx[mask])
            ys.append(ly[mask])
            zs.append(np.asarray(las.z, dtype=np.float64)[mask])
            cs.append(lc[mask])
            ints.append(np.asarray(las.intensity, dtype=np.float32)[mask])

        x, y, z, c, i = thin_point_cloud(
            np.concatenate(xs),
            np.concatenate(ys),
            np.concatenate(zs),
            np.concatenate(cs),
            np.concatenate(ints),
        )
        water_z = estimate_water_level(z, c, i)
        cloud = PointCloudData(
            name=name,
            x=x,
            y=y,
            z=z,
            classification=c,
            intensity=i,
            water_level_z=water_z,
        )
        las_out = write_point_cloud(cloud, real_dir / f"{name}.las")
        ref_out = save_polygon(
            poly,
            real_dir / f"{name}_BDOT10k.geojson",
            crs_epsg=2180,
            properties={
                "id": name,
                "source": "GUGiK_BDOT10k_3262_OT_PTWP_A",
                "water_z": water_z,
            },
        )
        print(
            f"Zbudowano zbiór rzeczywisty GUGiK: {name} "
            f"({cloud.num_points:,} pkt, Z_woda={water_z:.2f} m, pow. BDOT10k={poly.area:,.1f} m²)"
        )
        saved_pairs.append((las_out, ref_out))

    return saved_pairs


if __name__ == "__main__":
    build_real_szczecin_datasets()
