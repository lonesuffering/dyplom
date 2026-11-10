"""Automated downloader and extractor for real GUGiK LiDAR (.laz) and BDOT10k data in Szczecin.

Usage examples:
  1. List available water bodies in Szczecin BDOT10k:
     .venv/bin/python src/data/fetch_gugik.py --list

  2. Download and crop any water body from Szczecin by its BDOT10k index (e.g., 17 = Rusałka, 215 = Jezioro Goplany):
     .venv/bin/python src/data/fetch_gugik.py --fetch-id 17
"""

from __future__ import annotations

import argparse
import re
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import geopandas as gpd
import laspy
import numpy as np

from src.domain.models import LASClass, PointCloudData
from src.io.lidar_io import estimate_water_level, save_polygon, write_point_cloud

WMS_LIDAR_URLS = [
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK/DanePomiaroweNMT/WMS/SkorowidzeUkladEVRF2007",
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK/DanePomiaroweNMT/WMS/SkorowidzeUkladKRON86",
]


def _make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def query_gugik_laz_urls(x_2180: float, y_2180: float) -> list[str]:
    """Query GUGiK WMS GetFeatureInfo around (x_2180, y_2180) in EPSG:2180 to find .laz URLs."""
    ctx = _make_ssl_context()
    bbox_str = f"{x_2180 - 50:.1f},{y_2180 - 50:.1f},{x_2180 + 50:.1f},{y_2180 + 50:.1f}"

    found_urls: list[str] = []
    for base_wms in WMS_LIDAR_URLS:
        cap_url = f"{base_wms}?SERVICE=WMS&REQUEST=GetCapabilities&VERSION=1.1.1"
        try:
            req = urllib.request.Request(cap_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                xml_text = resp.read().decode("utf-8", errors="ignore")
            layer_names = re.findall(r"<Layer[^>]*>\s*<Name>([^<]+)</Name>", xml_text)
            query_layers = [ln for ln in layer_names if "Skorowidze" in ln or "DanePomiarowe" in ln]
            if not query_layers and layer_names:
                query_layers = layer_names[1:]
        except Exception:
            continue

        if not query_layers:
            continue

        layers_param = ",".join(query_layers)
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": layers_param,
            "QUERY_LAYERS": layers_param,
            "SRS": "EPSG:2180",
            "BBOX": bbox_str,
            "WIDTH": "101",
            "HEIGHT": "101",
            "X": "50",
            "Y": "50",
            "INFO_FORMAT": "text/html",
        }
        full_url = f"{base_wms}?{urllib.parse.urlencode(params)}"
        try:
            req = urllib.request.Request(full_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            laz_links = re.findall(r"https?://[^\s\"'<>]+?\.(?:laz|las)", body, flags=re.IGNORECASE)
            # Prefer newest campaign (e.g. 80222) and deduplicate by sheet code (N-33-...)
            seen_sheets = set()
            for link in laz_links:
                sheet_match = re.search(r"(N-\d+-[A-Za-z0-9-]+)\.(?:laz|las)", link)
                sheet_id = sheet_match.group(1) if sheet_match else link
                if sheet_id not in seen_sheets:
                    seen_sheets.add(sheet_id)
                    found_urls.append(link)
            if found_urls:
                break
        except Exception:
            continue

    return found_urls


def download_file(url: str, dest: Path) -> Path:
    """Download a file over HTTPS with progress logging."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 10_000:
        print(f"  [Plik w pamięci podręcznej]: {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
        return dest

    print(f"  Pobieranie z GUGiK: {url} -> {dest.name} ...")
    ctx = _make_ssl_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, context=ctx, timeout=180) as resp, open(dest, "wb") as out_f:
        while True:
            chunk = resp.read(512 * 1024)
            if not chunk:
                break
            out_f.write(chunk)
    print(f"  Pobrano {dest.name} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


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


def _load_bdot10k_gdf(root: Path) -> gpd.GeoDataFrame:
    ptwp_shp = root / "data" / "raw" / "bdot10k_3262" / "PL.PZGiK.339.BDOT10k.3262__OT_PTWP_A.shp"
    if not ptwp_shp.exists():
        raise FileNotFoundError(f"Brak pliku BDOT10k: {ptwp_shp}")
    gdf = gpd.read_file(ptwp_shp)
    if gdf.crs is not None and gdf.crs.to_epsg() != 2180:
        gdf = gdf.to_crs(epsg=2180)
    return gdf


def list_szczecin_lakes(base_dir: str | Path = PROJECT_ROOT) -> None:
    """Print a table of named water bodies in Szczecin from BDOT10k."""
    gdf = _load_bdot10k_gdf(Path(base_dir).resolve())
    gdf["area"] = gdf.geometry.area
    sub = gdf[(gdf["NAZWA"].notna()) & (gdf["area"] > 3000) & (gdf["area"] < 120000)].sort_values(
        "area", ascending=False
    )
    print(f"{'ID':>4} | {'Nazwa zbiornika (BDOT10k)':<26} | {'Powierzchnia [m²]':>17} | {'Wyspy':>5} | {'Środek (EPSG:2180)':<22}")
    print("-" * 85)
    for idx, row in sub.iterrows():
        c = row.geometry.centroid
        holes = len(row.geometry.interiors) if row.geometry.geom_type == "Polygon" else 0
        print(f"{idx:4d} | {str(row['NAZWA']):<26} | {row['area']:17,.1f} | {holes:5d} | X={c.x:.1f}, Y={c.y:.1f}")


def fetch_lake_by_bdot_id(bdot_idx: int, custom_name: str | None = None, base_dir: str | Path = PROJECT_ROOT) -> tuple[Path, Path]:
    """Download GUGiK LiDAR tiles for a specific BDOT10k lake ID in Szczecin, crop, and save to data/real/."""
    root = Path(base_dir).resolve()
    raw_dir = root / "data" / "raw"
    real_dir = root / "data" / "real"
    real_dir.mkdir(parents=True, exist_ok=True)

    gdf = _load_bdot10k_gdf(root)
    if bdot_idx not in gdf.index:
        raise ValueError(f"Nie znaleziono obiektu o ID={bdot_idx} w BDOT10k.")

    row = gdf.loc[bdot_idx]
    poly = row.geometry
    raw_title = str(row.get("NAZWA") or f"Zbiornik_{bdot_idx}")
    safe_title = (
        raw_title.replace(" ", "_")
        .replace("ą", "a").replace("ć", "c").replace("ę", "e")
        .replace("ł", "l").replace("ń", "n").replace("ó", "o")
        .replace("ś", "s").replace("ź", "z").replace("ż", "z")
        .replace("Ł", "L").replace("Ś", "S").replace("Ż", "Z")
    )
    name = custom_name or f"GUGiK_ID{bdot_idx}_{safe_title}"

    minx, miny, maxx, maxy = poly.bounds
    margin_m = 35.0
    sample_pts = [
        ((minx + maxx) / 2, (miny + maxy) / 2),
        (minx, miny),
        (maxx, maxy),
        (minx, maxy),
        (maxx, miny),
    ]

    laz_urls: list[str] = []
    seen_sheets = set()
    for sx, sy in sample_pts:
        for u in query_gugik_laz_urls(sx, sy):
            sheet_match = re.search(r"(N-\d+-[A-Za-z0-9-]+)\.(?:laz|las)", u)
            sheet_id = sheet_match.group(1) if sheet_match else u
            if sheet_id not in seen_sheets:
                seen_sheets.add(sheet_id)
                laz_urls.append(u)

    if not laz_urls:
        raise RuntimeError(f"Nie znaleziono arkuszy LiDAR w GUGiK dla {name}")

    xs, ys, zs, cs, ints = [], [], [], [], []
    for url in laz_urls:
        fn = url.split("/")[-1]
        laz_path = download_file(url, raw_dir / fn)
        las = laspy.read(laz_path)
        lx = np.asarray(las.x, dtype=np.float64)
        ly = np.asarray(las.y, dtype=np.float64)
        lc = np.asarray(las.classification, dtype=np.uint8)
        mask = (
            (lx >= minx - margin_m)
            & (lx <= maxx + margin_m)
            & (ly >= miny - margin_m)
            & (ly <= maxy + margin_m)
            & (lc != 12)
        )
        if np.any(mask):
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
        properties={"id": name, "source": "GUGiK_BDOT10k_3262_OT_PTWP_A", "water_z": water_z},
    )
    print(
        f"Gotowe! Zapisano w data/real/: {las_out.name} "
        f"({cloud.num_points:,} pkt, Z_woda={water_z:.2f} m, pow. BDOT10k={poly.area:,.1f} m²)"
    )
    return las_out, ref_out


def build_real_szczecin_datasets(base_dir: str | Path = PROJECT_ROOT) -> list[tuple[Path, Path]]:
    """Build cropped & thinned real GUGiK LiDAR datasets from already downloaded raw tiles in data/raw/."""
    root = Path(base_dir).resolve()
    raw_dir = root / "data" / "raw"
    real_dir = root / "data" / "real"
    real_dir.mkdir(parents=True, exist_ok=True)

    gdf = _load_bdot10k_gdf(root)
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
                & (lc != 12)
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
    parser = argparse.ArgumentParser(description="Narzędzie do pobierania i wycinania jezior z GUGiK (Szczecin)")
    parser.add_argument("--list", action="store_true", help="Wyświetl listę jezior i stawów w Szczecinie z BDOT10k")
    parser.add_argument("--fetch-id", type=int, help="Pobierz z GUGiK i wytnij zbiornik o podanym ID z BDOT10k")
    args = parser.parse_args()

    if args.list:
        list_szczecin_lakes()
    elif args.fetch_id is not None:
        fetch_lake_by_bdot_id(args.fetch_id)
    else:
        build_real_szczecin_datasets()
