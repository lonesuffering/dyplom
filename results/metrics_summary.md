# Zestawienie wyników porównania metod detekcji linii brzegowej

| Zbiór danych | Metoda | IoU | F1 | RMSE [m] | Odległość Hausdorffa [m] | Błąd powierzchni [%] | Czas [ms] |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Zbiornik_1_Regularny` | **Convex Hull (Baseline)** | 0.9788 | 0.9893 | 0.83 | 2.52 | +2.17% | 152.1 |
| `Zbiornik_1_Regularny` | **Metoda rastrowa (Grid 2m)** | 0.9783 | 0.9890 | 0.82 | 2.47 | -1.54% | 70.6 |
| `Zbiornik_1_Regularny` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.9875 | 0.9937 | 0.49 | 1.71 | +1.27% | 146.9 |
| `Zbiornik_1_Regularny` | **Autorski Adaptive Alpha-Shape** | 0.9858 | 0.9928 | 0.54 | 1.67 | +1.44% | 227.9 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Convex Hull (Baseline)** | 0.7749 | 0.8732 | 20.12 | 69.57 | +29.04% | 208.5 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Metoda rastrowa (Grid 2m)** | 0.9689 | 0.9842 | 0.81 | 2.39 | -2.21% | 84.3 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.9816 | 0.9907 | 0.53 | 1.88 | +1.88% | 205.2 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Autorski Adaptive Alpha-Shape** | 0.9821 | 0.9910 | 0.50 | 1.47 | +1.82% | 304.1 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Convex Hull (Baseline)** | 0.8441 | 0.9155 | 5.58 | 9.10 | -13.72% | 122.3 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Metoda rastrowa (Grid 2m)** | 0.7835 | 0.8786 | 6.71 | 11.61 | -21.63% | 62.5 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.8269 | 0.9053 | 6.46 | 22.24 | -14.60% | 140.8 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Autorski Adaptive Alpha-Shape** | 0.9880 | 0.9940 | 0.46 | 1.68 | +1.19% | 149.4 |
| `GUGiK_1_Jezioro_Szmaragdowe` | **Convex Hull (Baseline)** | 0.8407 | 0.9135 | 8.81 | 21.88 | -0.91% | 281.9 |
| `GUGiK_1_Jezioro_Szmaragdowe` | **Metoda rastrowa (Grid 2m)** | 0.7896 | 0.8824 | 8.84 | 24.45 | -21.04% | 95.8 |
| `GUGiK_1_Jezioro_Szmaragdowe` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.8291 | 0.9066 | 8.40 | 35.28 | +0.26% | 251.5 |
| `GUGiK_1_Jezioro_Szmaragdowe` | **Autorski Adaptive Alpha-Shape** | 0.9186 | 0.9575 | 4.32 | 16.35 | -3.82% | 278.9 |
| `GUGiK_2_Staw_Brodowski` | **Convex Hull (Baseline)** | 0.7804 | 0.8766 | 8.49 | 27.95 | -15.59% | 290.8 |
| `GUGiK_2_Staw_Brodowski` | **Metoda rastrowa (Grid 2m)** | 0.6843 | 0.8126 | 9.23 | 29.01 | -31.57% | 31.0 |
| `GUGiK_2_Staw_Brodowski` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.7267 | 0.8417 | 8.78 | 28.14 | -27.03% | 300.8 |
| `GUGiK_2_Staw_Brodowski` | **Autorski Adaptive Alpha-Shape** | 0.8734 | 0.9324 | 6.15 | 26.38 | -11.40% | 366.2 |
