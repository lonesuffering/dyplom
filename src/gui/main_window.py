"""PyQt6 Graphical User Interface for LiDAR Shoreline Detection (Chapter 4.3)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib_cache")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from shapely.geometry import MultiPolygon, Polygon

from src.domain.models import DetectionResult, LASClass, MetricsResult, PointCloudData
from src.evaluation.metrics import evaluate_detection
from src.io.lidar_io import load_polygon, read_point_cloud, save_polygon
from src.methods.adaptive_alpha_shape import detect_adaptive_alpha_shape
from src.methods.alpha_shape import detect_classical_alpha_shape
from src.methods.convex_hull import detect_convex_hull
from src.methods.grid_contour import detect_grid_contour


class ShorelineDetectionWindow(QMainWindow):
    """Main application window for automated LiDAR shoreline detection and BDOT10k comparison."""

    METHOD_ADAPTIVE = 0
    METHOD_CLASSICAL_ALPHA = 1
    METHOD_GRID = 2
    METHOD_CONVEX_HULL = 3
    METHOD_COMPARE_ALL = 4

    def __init__(self, project_root: str | Path = ".") -> None:
        super().__init__()
        self.project_root = Path(project_root).resolve()
        self.cloud: Optional[PointCloudData] = None
        self.reference_poly: Optional[Polygon | MultiPolygon] = None
        self.last_results: List[DetectionResult] = []
        self.last_metrics: List[MetricsResult] = []

        self.setWindowTitle(
            "Detekcja linii brzegowej zbiorników wodnych z chmur punktów LiDAR (BDOT10k) — WI ZUT"
        )
        self.resize(1380, 860)

        self._init_ui()
        self._populate_presets()

    def _init_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(12)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)

        # --- LEFT PANEL: Controls & Parameters ---
        left_panel = QWidget()
        left_panel.setMinimumWidth(360)
        left_panel.setMaximumWidth(420)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        # 1. Input Data Group
        grp_data = QGroupBox("1. Dane wejściowe (LiDAR LAS/LAZ i BDOT10k)")
        grp_data_layout = QVBoxLayout(grp_data)

        lbl_preset = QLabel("Zbiór testowy (szybki wybór):")
        self.cmb_preset = QComboBox()
        self.cmb_preset.currentIndexChanged.connect(self._on_preset_changed)

        btn_row_load = QHBoxLayout()
        self.btn_load_las = QPushButton("Wczytaj .las / .laz...")
        self.btn_load_las.clicked.connect(self._on_browse_las)
        self.btn_load_ref = QPushButton("Wczytaj BDOT10k...")
        self.btn_load_ref.clicked.connect(self._on_browse_ref)
        btn_row_load.addWidget(self.btn_load_las)
        btn_row_load.addWidget(self.btn_load_ref)

        self.lbl_cloud_info = QLabel("Brak wczytanej chmury punktów.")
        self.lbl_cloud_info.setWordWrap(True)
        self.lbl_cloud_info.setStyleSheet(
            "background-color: #f4f6f9; color: #1f2328; border: 1px solid #d0d7de; border-radius: 4px; padding: 6px; font-size: 11px;"
        )

        grp_data_layout.addWidget(lbl_preset)
        grp_data_layout.addWidget(self.cmb_preset)
        grp_data_layout.addLayout(btn_row_load)
        grp_data_layout.addWidget(self.lbl_cloud_info)
        left_layout.addWidget(grp_data)

        # 2. Algorithm Selection & Parameters Group
        grp_algo = QGroupBox("2. Metoda detekcji i parametry algorytmu")
        form_algo = QFormLayout(grp_algo)
        form_algo.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.cmb_method = QComboBox()
        self.cmb_method.addItems([
            "Autorski Adaptive Alpha-Shape (Proponowany)",
            "Klasyczny Alpha-Shape (Stałe α)",
            "Metoda rastrowa (Grid DSM)",
            "Convex Hull (Otoczka wypukła)",
            "Porównaj wszystkie 4 metody (Widok 2x2)",
        ])
        self.cmb_method.currentIndexChanged.connect(self._update_parameter_states)

        self.spn_alpha = QDoubleSpinBox()
        self.spn_alpha.setRange(0.5, 50.0)
        self.spn_alpha.setSingleStep(0.5)
        self.spn_alpha.setValue(3.0)
        self.spn_alpha.setSuffix(" m")

        self.spn_knn = QSpinBox()
        self.spn_knn.setRange(3, 50)
        self.spn_knn.setValue(12)

        self.spn_alpha_scale = QDoubleSpinBox()
        self.spn_alpha_scale.setRange(0.8, 4.0)
        self.spn_alpha_scale.setSingleStep(0.05)
        self.spn_alpha_scale.setValue(1.65)

        self.spn_delta_z = QDoubleSpinBox()
        self.spn_delta_z.setRange(0.0, 2.0)
        self.spn_delta_z.setSingleStep(0.02)
        self.spn_delta_z.setValue(0.24)
        self.spn_delta_z.setSuffix(" m")

        self.spn_intensity = QDoubleSpinBox()
        self.spn_intensity.setRange(0.0, 5000.0)
        self.spn_intensity.setSingleStep(50.0)
        self.spn_intensity.setValue(750.0)

        self.spn_grid_cell = QDoubleSpinBox()
        self.spn_grid_cell.setRange(0.5, 10.0)
        self.spn_grid_cell.setSingleStep(0.5)
        self.spn_grid_cell.setValue(2.0)
        self.spn_grid_cell.setSuffix(" m")

        form_algo.addRow("Tryb / Metoda:", self.cmb_method)
        form_algo.addRow("Promień stały α:", self.spn_alpha)
        form_algo.addRow("Liczba sąsiadów k-NN:", self.spn_knn)
        form_algo.addRow("Współczynnik adaptacji c_α:", self.spn_alpha_scale)
        form_algo.addRow("Próg wysokości brzegu ΔZ:", self.spn_delta_z)
        form_algo.addRow("Min. intensywność gruntu:", self.spn_intensity)
        form_algo.addRow("Rozmiar oczka siatki:", self.spn_grid_cell)
        left_layout.addWidget(grp_algo)

        # 3. Visualization Options Group
        grp_vis = QGroupBox("3. Opcje wizualizacji")
        vis_layout = QVBoxLayout(grp_vis)
        self.chk_show_points = QCheckBox("Pokaż sklasyfikowaną chmurę punktów LiDAR")
        self.chk_show_points.setChecked(True)
        self.chk_show_points.toggled.connect(self._refresh_plot)

        self.chk_show_ref = QCheckBox("Pokaż kontur referencyjny BDOT10k")
        self.chk_show_ref.setChecked(True)
        self.chk_show_ref.toggled.connect(self._refresh_plot)

        self.chk_fill_poly = QCheckBox("Wypełnij obszar wykrytego zbiornika wodnego")
        self.chk_fill_poly.setChecked(True)
        self.chk_fill_poly.toggled.connect(self._refresh_plot)

        vis_layout.addWidget(self.chk_show_points)
        vis_layout.addWidget(self.chk_show_ref)
        vis_layout.addWidget(self.chk_fill_poly)
        left_layout.addWidget(grp_vis)

        # 4. Actions & Export Group
        grp_actions = QGroupBox("4. Wykonanie i eksport wyników")
        act_layout = QVBoxLayout(grp_actions)

        self.btn_run = QPushButton("▶ Uruchom detekcję linii brzegowej")
        self.btn_run.setMinimumHeight(38)
        self.btn_run.setStyleSheet(
            "QPushButton { background-color: #0969da; color: white; font-weight: bold; font-size: 13px; border-radius: 5px; }"
            "QPushButton:hover { background-color: #0550ae; }"
        )
        self.btn_run.clicked.connect(self.run_detection)

        self.btn_export_poly = QPushButton("Eksportuj wektor linii brzegowej (GeoJSON / SHP)...")
        self.btn_export_poly.clicked.connect(self._on_export_polygon)

        btn_row_export2 = QHBoxLayout()
        self.btn_export_plot = QPushButton("Zapisz wykres (PNG)...")
        self.btn_export_plot.clicked.connect(self._on_export_plot)
        self.btn_export_csv = QPushButton("Zapisz metryki (CSV)...")
        self.btn_export_csv.clicked.connect(self._on_export_csv)
        btn_row_export2.addWidget(self.btn_export_plot)
        btn_row_export2.addWidget(self.btn_export_csv)

        act_layout.addWidget(self.btn_run)
        act_layout.addWidget(self.btn_export_poly)
        act_layout.addLayout(btn_row_export2)
        left_layout.addWidget(grp_actions)
        left_layout.addStretch()

        splitter.addWidget(left_panel)

        # --- RIGHT PANEL: Matplotlib Canvas & Metrics Table ---
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.figure = Figure(figsize=(8, 6), dpi=110)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, right_panel)

        right_layout.addWidget(self.toolbar)
        right_layout.addWidget(self.canvas, stretch=4)

        # Metrics Table
        grp_metrics = QGroupBox("Ocena dokładności detekcji względem bazy referencyjnej BDOT10k")
        metrics_layout = QVBoxLayout(grp_metrics)
        self.tbl_metrics = QTableWidget(0, 7)
        self.tbl_metrics.setHorizontalHeaderLabels([
            "Metoda",
            "IoU",
            "F1-score",
            "RMSE [m]",
            "Hausdorff d_H [m]",
            "Błąd pow. [%]",
            "Czas [ms]",
        ])
        self.tbl_metrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tbl_metrics.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_metrics.verticalHeader().setDefaultSectionSize(25)
        self.tbl_metrics.setMinimumHeight(155)
        self.tbl_metrics.setMaximumHeight(185)
        self.tbl_metrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_metrics.setAlternatingRowColors(True)
        metrics_layout.addWidget(self.tbl_metrics)

        right_layout.addWidget(grp_metrics, stretch=1)
        splitter.addWidget(right_panel)
        splitter.setSizes([380, 1000])

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_parameter_states()

    def _populate_presets(self) -> None:
        synth_dir = self.project_root / "data" / "synthetic"
        real_dir = self.project_root / "data" / "real"
        las_files = (
            (sorted(real_dir.glob("*.las")) if real_dir.exists() else [])
            + (sorted(synth_dir.glob("*.las")) if synth_dir.exists() else [])
        )
        self.preset_paths: List[Path] = las_files

        self.cmb_preset.blockSignals(True)
        self.cmb_preset.clear()
        for p in las_files:
            self.cmb_preset.addItem(p.stem)
        self.cmb_preset.blockSignals(False)

        if self.preset_paths:
            # Default to GUGiK_1_Jezioro_Szmaragdowe if available
            default_idx = 0
            self.cmb_preset.setCurrentIndex(default_idx)
            self._load_dataset_pair(self.preset_paths[default_idx])

    def _on_preset_changed(self, idx: int) -> None:
        if 0 <= idx < len(self.preset_paths):
            self._load_dataset_pair(self.preset_paths[idx])

    def _load_dataset_pair(self, las_path: Path) -> None:
        try:
            self.cloud = read_point_cloud(las_path)
            ref_candidate = las_path.with_name(f"{las_path.stem}_BDOT10k.geojson")
            if ref_candidate.exists():
                self.reference_poly = load_polygon(ref_candidate)
            else:
                self.reference_poly = None

            self._update_cloud_info_label()
            self.run_detection()
        except Exception as exc:
            QMessageBox.critical(self, "Błąd wczytywania danych", str(exc))

    def _update_cloud_info_label(self) -> None:
        if self.cloud is None:
            self.lbl_cloud_info.setText("Brak wczytanej chmury punktów.")
            return
        c = self.cloud
        n_ground = int(np.sum(c.classification == LASClass.GROUND))
        n_veg = int(np.sum(np.isin(c.classification, [LASClass.LOW_VEGETATION, LASClass.MEDIUM_VEGETATION, LASClass.HIGH_VEGETATION])))
        n_water = int(np.sum(c.classification == LASClass.WATER))
        ref_str = f"Tak ({self.reference_poly.area:,.0f} m²)" if self.reference_poly is not None else "Brak"
        self.lbl_cloud_info.setText(
            f"<b>Zbiór:</b> {c.name}<br>"
            f"<b>Liczba punktów:</b> {c.num_points:,} (Układ: EPSG:{c.crs_epsg})<br>"
            f"<b>Klasy:</b> Grunt={n_ground:,} | Roślinność={n_veg:,} | Woda={n_water:,}<br>"
            f"<b>Estymowany poziom wody Z_woda:</b> {c.water_level_z:.2f} m n.p.m.<br>"
            f"<b>Poligon referencyjny BDOT10k:</b> {ref_str}"
        )

    def _update_parameter_states(self) -> None:
        mode = self.cmb_method.currentIndex()
        is_adaptive = mode in (self.METHOD_ADAPTIVE, self.METHOD_COMPARE_ALL)
        is_classical = mode in (self.METHOD_CLASSICAL_ALPHA, self.METHOD_CONVEX_HULL, self.METHOD_COMPARE_ALL)
        is_grid = mode in (self.METHOD_GRID, self.METHOD_COMPARE_ALL)

        self.spn_alpha.setEnabled(is_classical)
        self.spn_knn.setEnabled(is_adaptive)
        self.spn_alpha_scale.setEnabled(is_adaptive)
        self.spn_delta_z.setEnabled(is_adaptive)
        self.spn_intensity.setEnabled(is_adaptive)
        self.spn_grid_cell.setEnabled(is_grid)

    def _on_browse_las(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik chmury punktów LiDAR",
            str(self.project_root / "data"),
            "Pliki LAS/LAZ (*.las *.laz)",
        )
        if file_path:
            self._load_dataset_pair(Path(file_path))

    def _on_browse_ref(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik referencyjny BDOT10k",
            str(self.project_root / "data"),
            "Pliki wektorowe (*.geojson *.shp *.gpkg)",
        )
        if file_path:
            self.reference_poly = load_polygon(file_path)
            self._update_cloud_info_label()
            self.run_detection()

    def _execute_single_method(self, method_idx: int) -> DetectionResult:
        assert self.cloud is not None
        if method_idx == self.METHOD_ADAPTIVE:
            return detect_adaptive_alpha_shape(
                self.cloud,
                k_neighbors=self.spn_knn.value(),
                alpha_scale=self.spn_alpha_scale.value(),
                delta_z_shore_m=self.spn_delta_z.value(),
                min_land_intensity=self.spn_intensity.value(),
            )
        if method_idx == self.METHOD_CLASSICAL_ALPHA:
            return detect_classical_alpha_shape(
                self.cloud,
                alpha_radius_m=self.spn_alpha.value(),
            )
        if method_idx == self.METHOD_GRID:
            return detect_grid_contour(
                self.cloud,
                cell_size_m=self.spn_grid_cell.value(),
            )
        return detect_convex_hull(
            self.cloud,
            cavity_radius_m=self.spn_alpha.value(),
        )

    def run_detection(self) -> None:
        if self.cloud is None:
            return

        mode = self.cmb_method.currentIndex()
        if mode == self.METHOD_COMPARE_ALL:
            order = [
                self.METHOD_CONVEX_HULL,
                self.METHOD_GRID,
                self.METHOD_CLASSICAL_ALPHA,
                self.METHOD_ADAPTIVE,
            ]
            self.last_results = [self._execute_single_method(m) for m in order]
        else:
            self.last_results = [self._execute_single_method(mode)]

        self.last_metrics = []
        if self.reference_poly is not None:
            self.last_metrics = [
                evaluate_detection(res, self.reference_poly) for res in self.last_results
            ]

        self._populate_metrics_table()
        self._refresh_plot()

        if self.last_metrics:
            best = max(self.last_metrics, key=lambda m: m.iou)
            self.status_bar.showMessage(
                f"Zakończono detekcję na zbiorze {self.cloud.name}. "
                f"Najlepszy wynik: {best.method_name} (IoU = {best.iou:.4f}, RMSE = {best.rmse_boundary_m:.2f} m)."
            )
        else:
            self.status_bar.showMessage(f"Zakończono detekcję na zbiorze {self.cloud.name}.")

    def _populate_metrics_table(self) -> None:
        self.tbl_metrics.setRowCount(len(self.last_metrics))
        if not self.last_metrics:
            return

        best_iou = max(m.iou for m in self.last_metrics)
        bold_font = QFont()
        bold_font.setBold(True)

        for row, m in enumerate(self.last_metrics):
            values = [
                m.method_name,
                f"{m.iou:.4f}",
                f"{m.f1_score:.4f}",
                f"{m.rmse_boundary_m:.2f}",
                f"{m.hausdorff_dist_m:.2f}",
                f"{m.area_rel_error_pct:+.2f}%",
                f"{m.execution_time_ms:.1f}",
            ]
            is_best = abs(m.iou - best_iou) < 1e-6 and len(self.last_metrics) > 1
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if is_best:
                    item.setFont(bold_font)
                    item.setBackground(QColor("#dafbe1"))
                    item.setForeground(QColor("#116329"))
                self.tbl_metrics.setItem(row, col, item)

    def _draw_subplot(self, ax, res: DetectionResult, met: Optional[MetricsResult], x_s, y_s, cls_s) -> None:
        if self.chk_show_points.isChecked():
            g_mask = cls_s == LASClass.GROUND
            v_low = cls_s == LASClass.LOW_VEGETATION
            v_high = cls_s == LASClass.HIGH_VEGETATION
            w_mask = cls_s == LASClass.WATER

            ax.scatter(x_s[g_mask], y_s[g_mask], s=1.4, c="#c2b280", alpha=0.55, label="Grunt (kl. 2)")
            if np.any(v_low):
                ax.scatter(x_s[v_low], y_s[v_low], s=2.4, c="#66a61e", alpha=0.8, label="Trzcina / rośl. niska (kl. 3)")
            if np.any(v_high):
                ax.scatter(x_s[v_high], y_s[v_high], s=2.6, c="#1b7837", alpha=0.7, label="Drzewa nadbrzeżne (kl. 5)")
            if np.any(w_mask):
                ax.scatter(x_s[w_mask], y_s[w_mask], s=3.2, c="#386cb0", alpha=0.85, label="Woda (kl. 9)")

        if self.chk_fill_poly.isChecked() and not res.polygon.is_empty:
            polys = list(res.polygon.geoms) if isinstance(res.polygon, MultiPolygon) else [res.polygon]
            for p in polys:
                px, py = p.exterior.xy
                ax.fill(px, py, color="#a6cee3", alpha=0.28)
                for ring in p.interiors:
                    hx, hy = ring.xy
                    ax.fill(hx, hy, color="#ffffff", alpha=0.85)

        if self.chk_show_ref.isChecked() and self.reference_poly is not None and not self.reference_poly.is_empty:
            ref_polys = list(self.reference_poly.geoms) if isinstance(self.reference_poly, MultiPolygon) else [self.reference_poly]
            for idx, p in enumerate(ref_polys):
                rx, ry = p.exterior.xy
                ax.plot(rx, ry, color="#1f78b4", lw=2.1, ls="--", label="Referencja BDOT10k" if idx == 0 else None)
                for ring in p.interiors:
                    irx, iry = ring.xy
                    ax.plot(irx, iry, color="#1f78b4", lw=2.1, ls="--")

        if not res.polygon.is_empty:
            det_polys = list(res.polygon.geoms) if isinstance(res.polygon, MultiPolygon) else [res.polygon]
            for idx, p in enumerate(det_polys):
                dx, dy = p.exterior.xy
                ax.plot(dx, dy, color="#e31a1c", lw=2.1, ls="-", label="Wykryta linia brzegowa" if idx == 0 else None)
                for ring in p.interiors:
                    idx_x, idx_y = ring.xy
                    ax.plot(idx_x, idx_y, color="#e31a1c", lw=2.1, ls="-")

        if met is not None:
            ax.set_title(
                f"{res.method_name}\nIoU={met.iou:.3f} | RMSE={met.rmse_boundary_m:.2f}m | d_H={met.hausdorff_dist_m:.1f}m",
                fontsize=9.0,
                fontweight="bold",
            )
        else:
            ax.set_title(f"{res.method_name} (Powierzchnia: {res.polygon.area:,.1f} m²)", fontsize=10, fontweight="bold")

        ax.set_xlabel("X [m] (EPSG:2180)", fontsize=9)
        ax.set_ylabel("Y [m] (EPSG:2180)", fontsize=9)
        ax.set_aspect("equal")
        ax.grid(True, linestyle=":", alpha=0.45)

    def _refresh_plot(self) -> None:
        self.figure.clear()
        if self.cloud is None or not self.last_results:
            self.canvas.draw()
            return

        rng = np.random.default_rng(42)
        idx = rng.choice(self.cloud.num_points, size=min(14000, self.cloud.num_points), replace=False)
        x_s, y_s, cls_s = self.cloud.x[idx], self.cloud.y[idx], self.cloud.classification[idx]

        if len(self.last_results) == 1:
            ax = self.figure.add_subplot(111)
            met = self.last_metrics[0] if self.last_metrics else None
            self._draw_subplot(ax, self.last_results[0], met, x_s, y_s, cls_s)
            ax.legend(loc="upper right", fontsize=9, frameon=True)
            self.figure.tight_layout()
        else:
            axes = self.figure.subplots(2, 2).ravel()
            for i, res in enumerate(self.last_results):
                met = self.last_metrics[i] if i < len(self.last_metrics) else None
                self._draw_subplot(axes[i], res, met, x_s, y_s, cls_s)
            handles, labels = axes[0].get_legend_handles_labels()
            if handles:
                self.figure.legend(handles, labels, loc="lower center", ncol=3, fontsize=8.5, frameon=True)
            self.figure.tight_layout(rect=[0, 0.06, 1, 1])

        self.canvas.draw()

    def _on_export_polygon(self) -> None:
        if not self.last_results or self.cloud is None:
            return
        res = self.last_results[-1]
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz wyekstrahowaną linię brzegową",
            str(self.project_root / "results" / "polygons" / f"{self.cloud.name}_exported.geojson"),
            "GeoJSON (*.geojson);;Shapefile (*.shp);;GeoPackage (*.gpkg)",
        )
        if file_path:
            save_polygon(
                res.polygon,
                file_path,
                crs_epsg=self.cloud.crs_epsg,
                properties={"dataset": self.cloud.name, "method": res.method_name},
            )
            self.status_bar.showMessage(f"Zapisano wektor linii brzegowej: {file_path}")

    def _on_export_plot(self) -> None:
        if self.cloud is None:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz wykres",
            str(self.project_root / "results" / "plots" / f"{self.cloud.name}_gui_plot.png"),
            "Obraz PNG (*.png);;Dokument PDF (*.pdf)",
        )
        if file_path:
            self.figure.savefig(file_path, dpi=180)
            self.status_bar.showMessage(f"Zapisano wykres: {file_path}")

    def _on_export_csv(self) -> None:
        if not self.last_metrics:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Zapisz tabelę metryk CSV",
            str(self.project_root / "results" / "gui_metrics.csv"),
            "Plik CSV (*.csv)",
        )
        if file_path:
            df = pd.DataFrame([vars(m) for m in self.last_metrics])
            df.to_csv(file_path, index=False)
            self.status_bar.showMessage(f"Zapisano tabelę metryk: {file_path}")
