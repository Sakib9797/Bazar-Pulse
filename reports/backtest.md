# Backtest report

Forecast origins 2026-04-01 to 2026-09-29; horizons 1, 2, 3 and 4 weeks; models refit every 28 days using only data known before each block (last 56 days held out for calibration).

Score = pinball loss of the 10% / 50% / 90% forecasts (lower is better). Skill = improvement over **climatology**: each product's own range of price changes over the previous year.

| Model | Pinball | Skill vs climatology | 80% range covers | Range width | Products better |
|---|---|---|---|---|---|
| baseline: climatology | 3.4414 | - | 82.0% | 10.56% | - |
| qlgbm | 3.3554 | +2.5% | 80.1% | 8.70% | 25 of 59 |
| qlgbm_deep | 3.3958 | +1.3% | 79.6% | 8.50% | 24 of 59 |
| qlgbm_smooth | 3.3336 | +3.1% | 81.3% | 8.73% | 28 of 59 |

## By horizon (qlgbm_smooth)

| Horizon | Skill | 80% range covers |
|---|---|---|
| 1 week | +5.2% | 85.4% |
| 2 weeks | +2.8% | 81.5% |
| 3 weeks | +2.3% | 79.5% |
| 4 weeks | +3.0% | 78.5% |

## Exact-price forecasts

The median forecast's error is 2.78% vs 2.78% for "price stays the same". Most TCB prices do not move in a given week, so exact forecasts do not beat no-change; the useful, measurable signal is in the range.

Champion chosen: **qlgbm_smooth**.


## Per product (qlgbm_smooth), most volatile first

| Product | Model pinball | Climatology | Range covers | Better |
|---|---|---|---|---|
| Green chili | 33.120 | 31.330 | 40% | no |
| Cucumber | 21.921 | 20.536 | 32% | no |
| Eggplant | 13.650 | 17.149 | 64% | yes |
| Lemon | 8.029 | 10.584 | 59% | yes |
| Onion (local) | 8.536 | 9.529 | 79% | yes |
| Ginger (imported) | 8.789 | 8.701 | 56% | no |
| Garlic (local) | 7.353 | 7.337 | 68% | no |
| Garlic (imported) | 6.439 | 6.278 | 66% | no |
| Potato | 5.576 | 5.971 | 85% | yes |
| Eggs (farm) | 4.549 | 5.392 | 75% | yes |
| Ginger (local) | 4.343 | 5.278 | 90% | yes |
| Bay leaf | 5.298 | 5.196 | 79% | no |
| Maida (packet) | 3.616 | 3.863 | 59% | yes |
| Atta (white loose) | 3.514 | 3.540 | 60% | yes |
| Milk powder (Dano) | 3.248 | 3.446 | 61% | yes |
| Chicken (broiler) | 3.126 | 3.119 | 90% | no |
| Chickpea | 2.652 | 2.889 | 79% | yes |
| Maida (loose) | 3.035 | 2.775 | 57% | no |
| Coarse rice (Swarna/China IRRI) | 2.224 | 2.529 | 71% | yes |
| Atta (packet) | 2.756 | 2.289 | 72% | no |
| Mutton (goat) | 1.877 | 2.286 | 86% | yes |
| Coriander seed | 1.976 | 2.018 | 87% | yes |
| Hilsa | 0.801 | 2.014 | 100% | yes |
| Aromatic rice (polao) | 1.563 | 1.958 | 83% | yes |
| Milk powder (Marks) | 1.753 | 1.943 | 77% | yes |
| Milk powder (Fresh) | 1.607 | 1.751 | 71% | yes |
| Dried chili (local) | 1.796 | 1.725 | 95% | no |
| Medium rice (Paijam/BR-28) | 1.655 | 1.702 | 71% | yes |
| Sugar | 1.763 | 1.684 | 85% | no |
| Turmeric (imported) | 1.369 | 1.577 | 92% | yes |
| Chicken (local) | 1.450 | 1.548 | 99% | yes |
| Dates (regular) | 1.370 | 1.534 | 95% | yes |
| Cinnamon | 1.294 | 1.513 | 86% | yes |
| MS rod (40 grade) | 1.637 | 1.470 | 87% | no |
| Dried chili (imported) | 1.522 | 1.405 | 90% | no |
| Mung dal | 1.081 | 1.222 | 87% | yes |
| Anchor dal | 0.790 | 1.156 | 91% | yes |
| Aromatic rice (polao) packet | 1.143 | 1.153 | 97% | yes |
| MS rod (60 grade) | 1.096 | 1.146 | 82% | yes |
| Cumin | 1.339 | 1.110 | 88% | no |
| Red lentil (small grain) | 0.955 | 0.952 | 91% | no |
| Red lentil (large grain) | 1.003 | 0.872 | 78% | no |
| Milk powder (Diploma) | 0.933 | 0.816 | 87% | no |
| Beef | 0.676 | 0.767 | 86% | yes |
| Soybean oil (loose) | 0.835 | 0.748 | 95% | no |
| Turmeric (local) | 1.124 | 0.720 | 97% | no |
| Red lentil (medium grain) | 0.568 | 0.673 | 90% | yes |
| Palm oil (loose) | 0.678 | 0.627 | 96% | no |
| Fine rice (Nazir/Miniket) | 0.623 | 0.554 | 90% | no |
| Super palm oil (loose) | 0.615 | 0.506 | 88% | no |
| Soybean oil (5 L bottle) | 0.593 | 0.493 | 93% | no |
| Rice bran oil (5 L bottle) | 0.485 | 0.472 | 77% | no |
| Soybean oil (1 L bottle) | 0.584 | 0.469 | 85% | no |
| Soybean oil (2 L bottle) | 0.685 | 0.460 | 85% | no |
| Salt (iodized packet) | 0.549 | 0.422 | 84% | no |
| Clove | 0.742 | 0.407 | 100% | no |
| Cardamom (small) | 0.894 | 0.393 | 100% | no |
| Rui fish | 0.570 | 0.377 | 97% | no |
| Writing paper (white) | 0.114 | 0.000 | 100% | no |
