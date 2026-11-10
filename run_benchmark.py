"""Main benchmark runner comparing shoreline detection methods on LiDAR datasets."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from src.data.synth_generator import generate_all_datasets
from src.evaluation.metrics import evaluate_detection
from src.evaluation.plotting import plot_dataset_comparison
from src.io.lidar_io import load_polygon, read_point_cloud, save_polygon
from src.methods.adaptive_alpha_shape import detect_adaptive_alpha_shape
from src.methods.alpha_shape import detect_classical_alpha_shape
from src.methods.convex_hull import detect_convex_hull
from src.methods.grid_contour import detect_grid_contour


def run_all_benchmarks(base_dir: str | Path = ".") -> pd.DataFrame:
    root = Path(base_dir).resolve()
    data_dir = root / "data" / "synthetic"
    results_dir = root / "results"
    plots_dir = results_dir / "plots"
    polys_dir = results_dir / "polygons"

    print("1. Generowanie zestawów danych testowych LiDAR (.las) oraz referencji BDOT10k...")
    dataset_pairs = list(generate_all_datasets(data_dir))

    real_dir = root / "data" / "real"
    if real_dir.exists():
        for real_las in sorted(real_dir.glob("*.las")):
            real_ref = real_las.with_name(f"{real_las.stem}_BDOT10k.geojson")
            if real_ref.exists():
                dataset_pairs.append((real_las, real_ref))

    detectors = [
        detect_convex_hull,
        detect_grid_contour,
        detect_classical_alpha_shape,
        detect_adaptive_alpha_shape,
    ]

    all_metrics = []

    for las_path, ref_path in dataset_pairs:
        cloud = read_point_cloud(las_path)
        ref_poly = load_polygon(ref_path)
        print(f"\n2. Przetwarzanie zbioru: {cloud.name} ({cloud.num_points:,} punktów, Z_woda={cloud.water_level_z:.2f} m)")

        ds_results = []
        ds_metrics = []

        for detector_fn in detectors:
            res = detector_fn(cloud)
            met = evaluate_detection(res, ref_poly)
            ds_results.append(res)
            ds_metrics.append(met)
            all_metrics.append(met)

            # Save detected shoreline polygon
            safe_method = (
                res.method_name.lower()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                .replace("=", "")
                .replace("α", "alpha")
            )
            save_polygon(
                res.polygon,
                polys_dir / f"{cloud.name}_{safe_method}.geojson",
                crs_epsg=cloud.crs_epsg,
                properties={
                    "dataset": cloud.name,
                    "method": res.method_name,
                    "iou": round(met.iou, 4),
                    "rmse_m": round(met.rmse_boundary_m, 3),
                    "hausdorff_m": round(met.hausdorff_dist_m, 3),
                },
            )
            print(
                f"   - {res.method_name:<35} | IoU: {met.iou:.4f} | "
                f"RMSE: {met.rmse_boundary_m:5.2f} m | d_H: {met.hausdorff_dist_m:5.2f} m | "
                f"Czas: {met.execution_time_ms:6.1f} ms"
            )

        plot_path = plot_dataset_comparison(
            cloud,
            ref_poly,
            ds_results,
            ds_metrics,
            plots_dir / f"{cloud.name}_porownanie.png",
        )
        print(f"   [Zapisano wykres porównawczy: {plot_path.relative_to(root)}]")

    df = pd.DataFrame([vars(m) for m in all_metrics])
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "metrics_summary.csv"
    df.to_csv(csv_path, index=False)

    # Also write a clean Markdown table for Chapter 5 of the thesis
    md_lines = [
        "# Zestawienie wyników porównania metod detekcji linii brzegowej",
        "",
        "| Zbiór danych | Metoda | IoU | F1 | RMSE [m] | Odległość Hausdorffa [m] | Błąd powierzchni [%] | Czas [ms] |",
        "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
    ]
    for m in all_metrics:
        md_lines.append(
            f"| `{m.dataset_name}` | **{m.method_name}** | {m.iou:.4f} | {m.f1_score:.4f} | "
            f"{m.rmse_boundary_m:.2f} | {m.hausdorff_dist_m:.2f} | {m.area_rel_error_pct:+.2f}% | {m.execution_time_ms:.1f} |"
        )
    (results_dir / "metrics_summary.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    return df


if __name__ == "__main__":
    run_all_benchmarks()
