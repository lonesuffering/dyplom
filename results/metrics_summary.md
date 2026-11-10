# Zestawienie wyników porównania metod detekcji linii brzegowej

| Zbiór danych | Metoda | IoU | F1 | RMSE [m] | Odległość Hausdorffa [m] | Błąd powierzchni [%] | Czas [ms] |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `Zbiornik_1_Regularny` | **Convex Hull (Baseline)** | 0.9788 | 0.9893 | 0.83 | 2.52 | +2.17% | 173.1 |
| `Zbiornik_1_Regularny` | **Metoda rastrowa (Grid 2m)** | 0.9783 | 0.9890 | 0.82 | 2.47 | -1.54% | 89.7 |
| `Zbiornik_1_Regularny` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.9875 | 0.9937 | 0.49 | 1.71 | +1.27% | 167.8 |
| `Zbiornik_1_Regularny` | **Autorski Adaptive Alpha-Shape** | 0.9858 | 0.9928 | 0.54 | 1.67 | +1.44% | 248.9 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Convex Hull (Baseline)** | 0.7749 | 0.8732 | 20.12 | 69.57 | +29.04% | 265.2 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Metoda rastrowa (Grid 2m)** | 0.9689 | 0.9842 | 0.81 | 2.39 | -2.21% | 111.6 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.9816 | 0.9907 | 0.53 | 1.88 | +1.88% | 264.7 |
| `Zbiornik_2_Nieregularny_Wyspa` | **Autorski Adaptive Alpha-Shape** | 0.9821 | 0.9910 | 0.50 | 1.47 | +1.82% | 387.6 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Convex Hull (Baseline)** | 0.8441 | 0.9155 | 5.58 | 9.10 | -13.72% | 154.7 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Metoda rastrowa (Grid 2m)** | 0.7835 | 0.8786 | 6.71 | 11.61 | -21.63% | 80.8 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Klasyczny Alpha-Shape (α=3.0m)** | 0.8269 | 0.9053 | 6.46 | 22.24 | -14.60% | 194.6 |
| `Zbiornik_3_Roslinnosc_ZmiennaGestosc` | **Autorski Adaptive Alpha-Shape** | 0.9880 | 0.9940 | 0.46 | 1.68 | +1.19% | 205.3 |
