"""Visualization utilities for generating thesis-ready comparison figures."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")
import matplotlib.pyplot as plt
import numpy as np
from shapely.geometry import MultiPolygon, Polygon

from src.domain.models import DetectionResult, LASClass, MetricsResult, PointCloudData


def _plot_polygon_outline(ax, poly: Polygon | MultiPolygon, color: str, label: str, lw: float = 2.0, ls: str = "-"):
    if poly.is_empty:
        return
    polys = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
    for idx, p in enumerate(polys):
        x, y = p.exterior.xy
        ax.plot(x, y, color=color, linewidth=lw, linestyle=ls, label=label if idx == 0 else None)
        for ring in p.interiors:
            rx, ry = ring.xy
            ax.plot(rx, ry, color=color, linewidth=lw, linestyle=ls)


def plot_dataset_comparison(
    cloud: PointCloudData,
    reference_poly: Polygon | MultiPolygon,
    results: Sequence[DetectionResult],
    metrics: Sequence[MetricsResult],
    output_path: str | Path,
) -> Path:
    """Create a 2x2 visual comparison of all four shoreline detection methods on a dataset."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(2, 2, figsize=(13, 12), dpi=160)
    axes_flat = axes.ravel()

    # Subsample background point cloud for fast, clean rendering
    rng = np.random.default_rng(42)
    step = max(1, cloud.num_points // 14000)
    idx = rng.choice(cloud.num_points, size=min(14000, cloud.num_points), replace=False)
    x_s, y_s, cls_s = cloud.x[idx], cloud.y[idx], cloud.classification[idx]

    for ax, res, met in zip(axes_flat, results, metrics):
        # Plot LiDAR classes
        g_mask = cls_s == LASClass.GROUND
        v_low = cls_s == LASClass.LOW_VEGETATION
        v_high = cls_s == LASClass.HIGH_VEGETATION
        w_mask = cls_s == LASClass.WATER

        ax.scatter(x_s[g_mask], y_s[g_mask], s=1.2, c="#c2b280", alpha=0.55, label="Grunt (kl. 2)")
        if np.any(v_low):
            ax.scatter(x_s[v_low], y_s[v_low], s=2.2, c="#66a61e", alpha=0.75, label="Roślinność niska / trzcina (kl. 3)")
        if np.any(v_high):
            ax.scatter(x_s[v_high], y_s[v_high], s=2.5, c="#1b7837", alpha=0.65, label="Drzewa nadbrzeżne (kl. 5)")
        if np.any(w_mask):
            ax.scatter(x_s[w_mask], y_s[w_mask], s=3.0, c="#386cb0", alpha=0.80, label="Woda (kl. 9)")

        # Reference BDOT10k contour vs Detected shoreline
        _plot_polygon_outline(ax, reference_poly, color="#1f78b4", label="Referencja BDOT10k", lw=2.2, ls="--")
        _plot_polygon_outline(ax, res.polygon, color="#e31a1c", label="Wykryta linia brzegowa", lw=2.0, ls="-")

        ax.set_title(
            f"{res.method_name}\n"
            f"IoU = {met.iou:.3f} | RMSE = {met.rmse_boundary_m:.2f} m | d_H = {met.hausdorff_dist_m:.2f} m",
            fontsize=10.5,
            fontweight="bold",
        )
        ax.set_xlabel("X [m] (EPSG:2180)")
        ax.set_ylabel("Y [m] (EPSG:2180)")
        ax.set_aspect("equal")
        ax.grid(True, linestyle=":", alpha=0.4)

    handles, labels = axes_flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=True, fontsize=9.5)
    fig.suptitle(f"Porównanie metod detekcji linii brzegowej — {cloud.name}", fontsize=13, fontweight="bold", y=0.98)
    fig.tight_layout(rect=[0, 0.06, 1, 0.95])
    fig.savefig(out)
    plt.close(fig)
    return out
