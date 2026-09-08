# Carr-S distribution-level comparison vs frozen Carr-R reference

Runs: 5 (3 x E1 v2 24-household, 2 x E3c scale-100). Survey reference sha256 0d899eb35bce3439... (frozen v1_1).

## Channel prevalence (multi-select, among order recipients)
| channel | sim pooled (k/n) | sim share | survey share [Wilson 95] |
|---|---|---|---|
| official_direct | 197/197 | 1.000 | -- |
| community | 182/197 | 0.924 | -- |
| household_dm | 83/197 | 0.421 | -- |
| any_interpersonal | 185/197 | 0.939 | -- |
| survey reverse_911 | 84/234 | -- | 0.359 [0.300, 0.422] |
| survey text | 89/234 | -- | 0.380 [0.321, 0.444] |
| survey interpersonal | 87/234 | -- | 0.372 [0.312, 0.435] |

## Order-to-departure delay CDF (hours from first delivered order to first executed household departure)
| hours | sim pooled | survey main (n=186) |
|---|---|---|
| 0 | 0.570 | 0.446 |
| 0.5 | 0.868 | 0.446 |
| 1 | 0.965 | 0.634 |
| 2 | 1.000 | 0.656 |
| 3 | 1.000 | 0.694 |
| 4 | 1.000 | 0.742 |
| 5 | 1.000 | 0.774 |
| 6 | 1.000 | 0.780 |
| 8 | 1.000 | 0.817 |
| 10 | 1.000 | 0.855 |
| 12 | 1.000 | 0.892 |
| 24 | 1.000 | 0.941 |
| 48 | 1.000 | 0.968 |

sim pooled n=114, mean=0.28 h, median=0.00 h; survey n=186, mean=7.11 h, median=1.0 h.

## Individual departure share
sim pooled (all members): 200/534 = 0.375; sim pooled (order-recipient households): 180/393 = 0.458; survey evacuation proportion: 0.888 [0.849, 0.918] (n=330).

Per-run detail:
```json
{"run": "e1_v2/seed7201", "recipient_households": 17, "channels": {"official_direct": 1.0, "community": 1.0, "household_dm": 0.353, "any_interpersonal": 1.0}, "delay_n": 12, "delay_cdf": {"0": 0.75, "0.5": 1.0, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "8": 1.0, "10": 1.0, "12": 1.0, "24": 1.0, "48": 1.0}, "indiv_departure": 0.432}
{"run": "e1_v2/seed8301", "recipient_households": 17, "channels": {"official_direct": 1.0, "community": 0.647, "household_dm": 0.294, "any_interpersonal": 0.706}, "delay_n": 13, "delay_cdf": {"0": 0.615, "0.5": 0.846, "1": 0.923, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "8": 1.0, "10": 1.0, "12": 1.0, "24": 1.0, "48": 1.0}, "indiv_departure": 0.5}
{"run": "e1_v2/seed9401", "recipient_households": 17, "channels": {"official_direct": 1.0, "community": 1.0, "household_dm": 0.294, "any_interpersonal": 1.0}, "delay_n": 12, "delay_cdf": {"0": 0.667, "0.5": 0.833, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "8": 1.0, "10": 1.0, "12": 1.0, "24": 1.0, "48": 1.0}, "indiv_departure": 0.477}
{"run": "e3c_scale100/seed101", "recipient_households": 73, "channels": {"official_direct": 1.0, "community": 1.0, "household_dm": 0.466, "any_interpersonal": 1.0}, "delay_n": 43, "delay_cdf": {"0": 0.488, "0.5": 0.837, "1": 0.93, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "8": 1.0, "10": 1.0, "12": 1.0, "24": 1.0, "48": 1.0}, "indiv_departure": 0.383}
{"run": "e3c_scale100/seed202", "recipient_households": 73, "channels": {"official_direct": 1.0, "community": 0.877, "household_dm": 0.452, "any_interpersonal": 0.904}, "delay_n": 34, "delay_cdf": {"0": 0.559, "0.5": 0.882, "1": 1.0, "2": 1.0, "3": 1.0, "4": 1.0, "5": 1.0, "6": 1.0, "8": 1.0, "10": 1.0, "12": 1.0, "24": 1.0, "48": 1.0}, "indiv_departure": 0.303}
```
