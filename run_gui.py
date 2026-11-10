"""Entry point for the PyQt6 Shoreline Detection GUI application (Chapter 4.3)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="GUI do detekcji linii brzegowej z danych LiDAR")
    parser.add_argument(
        "--save-screenshots",
        action="store_true",
        help="Render GUI views in offscreen mode and save thesis screenshots to results/plots/",
    )
    args = parser.parse_args()

    if args.save_screenshots:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtWidgets import QApplication
    from src.gui.main_window import ShorelineDetectionWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    root = Path(__file__).resolve().parent
    window = ShorelineDetectionWindow(project_root=root)
    window.show()

    if args.save_screenshots:
        plots_dir = root / "results" / "plots"
        plots_dir.mkdir(parents=True, exist_ok=True)

        # 1. Screenshot of Adaptive Alpha-Shape single view on Zbiornik_3
        window.cmb_method.setCurrentIndex(ShorelineDetectionWindow.METHOD_ADAPTIVE)
        window.run_detection()
        app.processEvents()
        out1 = plots_dir / "GUI_widok_autorski_adaptive.png"
        window.grab().save(str(out1))
        print(f"Zapisano zrzut ekranu GUI (widok pojedynczy): {out1.relative_to(root)}")

        # 2. Screenshot of 2x2 comparison mode in GUI on Zbiornik_3
        window.cmb_method.setCurrentIndex(ShorelineDetectionWindow.METHOD_COMPARE_ALL)
        window.run_detection()
        app.processEvents()
        out2 = plots_dir / "GUI_widok_porownanie_4_metod.png"
        window.grab().save(str(out2))
        print(f"Zapisano zrzut ekranu GUI (widok 2x2): {out2.relative_to(root)}")
        return

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
