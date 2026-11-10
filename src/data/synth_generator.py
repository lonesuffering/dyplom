"""Generator of realistic ASPRS LAS 1.4 point clouds and BDOT10k reference polygons.

Simulates airborne LiDAR (ISOK Standard I/II, EPSG:2180) over three representative
water bodies in the Szczecin region:
1. Zbiornik_1_Regularny: Simple retention pond with clean banks and uniform point density.
2. Zbiornik_2_Nieregularny_Wyspa: Irregular post-glacial lake with deep bays and an island.
3. Zbiornik_3_Roslinnosc_ZmiennaGestosc: Forest lake with coastal reed beds (Class 3),
   overhanging tree canopy (Class 5), and variable ground point density under trees.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple
import numpy as np
from shapely.geometry import Point, Polygon
from shapely.prepared import prep

from src.domain.models import LASClass, PointCloudData
from src.io.lidar_io import save_polygon, write_point_cloud

# Base coordinates in EPSG:2180 (PUWG 1992) near Szczecin
BASE_X = 212500.0
BASE_Y = 624500.0
WATER_Z = 14.20  # meters above sea level (m n.p.m.)


def _make_polar_polygon(
    center_x: float,
    center_y: float,
    r_func,
    num_vertices: int = 360,
    hole_polygon: Polygon | None = None,
) -> Polygon:
    angles = np.linspace(0, 2 * np.pi, num_vertices, endpoint=False)
    radii = r_func(angles)
    xs = center_x + radii * np.cos(angles)
    ys = center_y + radii * np.sin(angles)
    shell = list(zip(xs, ys))
    if hole_polygon is not None:
        return Polygon(shell, [list(hole_polygon.exterior.coords)])
    return Polygon(shell)


def _contains_xy(polygon: Polygon, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Vectorized point-in-polygon mask using Shapely 2.0 or prepared geometry."""
    try:
        import shapely
        return shapely.contains_xy(polygon, x, y)
    except AttributeError:
        prepared = prep(polygon)
        return np.array([prepared.contains(Point(px, py)) for px, py in zip(x, y)], dtype=bool)


def _distance_to_boundary(polygon: Polygon, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute signed distance to water boundary (positive on land, negative in water)."""
    import shapely
    pts = shapely.points(x, y)
    dist = shapely.distance(pts, polygon.boundary)
    inside = _contains_xy(polygon, x, y)
    return np.where(inside, -dist, dist)


def generate_dataset_1_regular(rng: np.random.Generator) -> Tuple[PointCloudData, Polygon]:
    """Dataset 1: Regular retention reservoir with clean banks and uniform density."""
    cx, cy = BASE_X, BASE_Y
    poly = _make_polar_polygon(
        cx,
        cy,
        lambda theta: 65.0 + 12.0 * np.cos(2 * theta) + 4.0 * np.sin(3 * theta),
    )

    # Bounding box 220m x 220m, uniform density ~3.5 pts/m^2
    span = 115.0
    n_land = 42000
    x = rng.uniform(cx - span, cx + span, n_land)
    y = rng.uniform(cy - span, cy + span, n_land)

    signed_d = _distance_to_boundary(poly, x, y)
    land_mask = signed_d >= 0.0
    x_land, y_land, d_land = x[land_mask], y[land_mask], signed_d[land_mask]

    # Bank elevation rises smoothly with distance from shore
    z_land = WATER_Z + 0.25 + 0.06 * d_land + rng.normal(0, 0.05, len(x_land))
    cls_land = np.full(len(x_land), LASClass.GROUND, dtype=np.uint8)
    int_land = rng.normal(2400, 300, len(x_land)).clip(500, 5000)

    # Sparse water surface returns (Class 9)
    n_water = 400
    xw = rng.uniform(cx - 60, cx + 60, n_water)
    yw = rng.uniform(cy - 60, cy + 60, n_water)
    in_water = _contains_xy(poly.buffer(-2.0), xw, yw)
    xw, yw = xw[in_water], yw[in_water]
    zw = np.full(len(xw), WATER_Z) + rng.normal(0, 0.02, len(xw))
    cls_w = np.full(len(xw), LASClass.WATER, dtype=np.uint8)
    int_w = rng.normal(180, 40, len(xw)).clip(30, 400)

    cloud = PointCloudData(
        name="Zbiornik_1_Regularny",
        x=np.concatenate([x_land, xw]),
        y=np.concatenate([y_land, yw]),
        z=np.concatenate([z_land, zw]),
        classification=np.concatenate([cls_land, cls_w]),
        intensity=np.concatenate([int_land, int_w]).astype(np.float32),
        water_level_z=WATER_Z,
    )
    return cloud, poly


def generate_dataset_2_irregular_island(rng: np.random.Generator) -> Tuple[PointCloudData, Polygon]:
    """Dataset 2: Irregular lake with narrow bays, peninsulas, and a central island."""
    cx, cy = BASE_X + 500.0, BASE_Y
    island = _make_polar_polygon(
        cx - 4.0,
        cy + 4.0,
        lambda theta: 14.5 + 2.0 * np.cos(3 * theta),
    )
    poly = _make_polar_polygon(
        cx,
        cy,
        lambda theta: (
            72.0
            + 26.0 * np.sin(3 * theta)
            + 14.0 * np.cos(5 * theta - 0.4)
            + 8.0 * np.sin(2 * theta)
        ),
        hole_polygon=island,
    )

    span = 135.0
    n_pts = 58000
    x = rng.uniform(cx - span, cx + span, n_pts)
    y = rng.uniform(cy - span, cy + span, n_pts)

    signed_d = _distance_to_boundary(poly, x, y)
    land_mask = signed_d >= 0.0
    x_land, y_land, d_land = x[land_mask], y[land_mask], signed_d[land_mask]

    z_land = WATER_Z + 0.30 + 0.07 * d_land + rng.normal(0, 0.06, len(x_land))
    cls_land = np.full(len(x_land), LASClass.GROUND, dtype=np.uint8)
    int_land = rng.normal(2300, 320, len(x_land)).clip(500, 5000)

    # Sparse water reflections
    n_water = 500
    xw = rng.uniform(cx - 90, cx + 90, n_water)
    yw = rng.uniform(cy - 90, cy + 90, n_water)
    in_water = _contains_xy(poly.buffer(-2.0), xw, yw)
    xw, yw = xw[in_water], yw[in_water]
    zw = np.full(len(xw), WATER_Z) + rng.normal(0, 0.02, len(xw))
    cls_w = np.full(len(xw), LASClass.WATER, dtype=np.uint8)
    int_w = rng.normal(160, 35, len(xw)).clip(30, 400)

    cloud = PointCloudData(
        name="Zbiornik_2_Nieregularny_Wyspa",
        x=np.concatenate([x_land, xw]),
        y=np.concatenate([y_land, yw]),
        z=np.concatenate([z_land, zw]),
        classification=np.concatenate([cls_land, cls_w]),
        intensity=np.concatenate([int_land, int_w]).astype(np.float32),
        water_level_z=WATER_Z,
    )
    return cloud, poly


def generate_dataset_3_vegetation_density(rng: np.random.Generator) -> Tuple[PointCloudData, Polygon]:
    """Dataset 3: Forest lake with coastal reeds (Class 3), overhanging canopy (Class 5),
    and strongly varying ground point density under trees on the western bank.
    """
    cx, cy = BASE_X + 1000.0, BASE_Y
    poly = _make_polar_polygon(
        cx,
        cy,
        lambda theta: 68.0 + 18.0 * np.cos(2 * theta - 0.5) + 12.0 * np.sin(4 * theta),
    )

    span = 130.0
    n_pts = 55000
    x = rng.uniform(cx - span, cx + span, n_pts)
    y = rng.uniform(cy - span, cy + span, n_pts)

    signed_d = _distance_to_boundary(poly, x, y)
    land_mask = signed_d >= 0.0
    x_land, y_land, d_land = x[land_mask], y[land_mask], signed_d[land_mask]

    # Simulate dense forest canopy on the western side (x < cx - 10):
    # Only 12% of laser pulses reach the ground under thick trees!
    west_forest_zone = (x_land < cx - 15.0) & (d_land > 1.5)
    keep_prob = np.where(west_forest_zone, 0.11, 1.0)
    keep_mask = rng.random(len(x_land)) < keep_prob
    x_land, y_land, d_land = x_land[keep_mask], y_land[keep_mask], d_land[keep_mask]

    z_land = WATER_Z + 0.30 + 0.065 * d_land + rng.normal(0, 0.06, len(x_land))
    cls_land = np.full(len(x_land), LASClass.GROUND, dtype=np.uint8)
    int_land = rng.normal(2200, 300, len(x_land)).clip(500, 5000)

    # Add littoral reed bed (trzcinowisko) inside shallow water along NE shore (-9m < signed_d < 0m)
    reed_band = poly.difference(poly.buffer(-9.5))
    n_reeds = 4500
    xr = rng.uniform(cx - 90, cx + 90, n_reeds)
    yr = rng.uniform(cy - 90, cy + 90, n_reeds)
    in_reeds = _contains_xy(reed_band, xr, yr) & ((xr > cx - 10.0) | (yr > cy))
    xr, yr = xr[in_reeds], yr[in_reeds]
    zr = WATER_Z + rng.uniform(0.04, 0.22, len(xr))
    # Half of reed points are classified as Class 3 (Low Veg), half misclassified as Class 2 (Ground) with low Z & low intensity
    cls_r = np.where(
        rng.random(len(xr)) < 0.55,
        LASClass.LOW_VEGETATION,
        LASClass.GROUND,
    ).astype(np.uint8)
    int_r = rng.normal(420, 80, len(xr)).clip(150, 700)

    # Add overhanging tree canopy (Class 5) extending 7m over the water on the western & southern shore
    overhang_zone = poly.buffer(15.0).difference(poly.buffer(-7.5))
    n_trees = 5000
    xt = rng.uniform(cx - 105, cx + 105, n_trees)
    yt = rng.uniform(cy - 105, cy + 105, n_trees)
    in_trees = _contains_xy(overhang_zone, xt, yt) & ((xt < cx) | (yt < cy - 20.0))
    xt, yt = xt[in_trees], yt[in_trees]
    zt = WATER_Z + rng.uniform(6.0, 16.0, len(xt))
    cls_t = np.full(len(xt), LASClass.HIGH_VEGETATION, dtype=np.uint8)
    int_t = rng.normal(1400, 250, len(xt)).clip(400, 3000)

    # Sparse water points (Class 9)
    n_water = 350
    xw = rng.uniform(cx - 60, cx + 60, n_water)
    yw = rng.uniform(cy - 60, cy + 60, n_water)
    in_water = _contains_xy(poly.buffer(-10.0), xw, yw)
    xw, yw = xw[in_water], yw[in_water]
    zw = np.full(len(xw), WATER_Z) + rng.normal(0, 0.02, len(xw))
    cls_w = np.full(len(xw), LASClass.WATER, dtype=np.uint8)
    int_w = rng.normal(170, 35, len(xw)).clip(30, 400)

    cloud = PointCloudData(
        name="Zbiornik_3_Roslinnosc_ZmiennaGestosc",
        x=np.concatenate([x_land, xr, xt, xw]),
        y=np.concatenate([y_land, yr, yt, yw]),
        z=np.concatenate([z_land, zr, zt, zw]),
        classification=np.concatenate([cls_land, cls_r, cls_t, cls_w]),
        intensity=np.concatenate([int_land, int_r, int_t, int_w]).astype(np.float32),
        water_level_z=WATER_Z,
    )
    return cloud, poly


def generate_all_datasets(output_dir: str | Path) -> list[Tuple[Path, Path]]:
    """Generate and save all three benchmark LiDAR datasets and reference BDOT10k polygons."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed=53867)  # Album number as reproducible seed!

    generators = [
        generate_dataset_1_regular,
        generate_dataset_2_irregular_island,
        generate_dataset_3_vegetation_density,
    ]

    saved_pairs: list[Tuple[Path, Path]] = []
    for gen_fn in generators:
        cloud, ref_poly = gen_fn(rng)
        las_path = write_point_cloud(cloud, out / f"{cloud.name}.las")
        ref_path = save_polygon(
            ref_poly,
            out / f"{cloud.name}_BDOT10k.geojson",
            crs_epsg=cloud.crs_epsg,
            properties={"id": cloud.name, "source": "BDOT10k_OT_PTWP_A", "water_z": cloud.water_level_z},
        )
        saved_pairs.append((las_path, ref_path))

    return saved_pairs
