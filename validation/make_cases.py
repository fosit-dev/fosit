"""Generate the synthetic validation cases that both GeoLift and FOSIT analyse.

Each case is a folder with data.csv (date, geo_id, orders) and case.json
(treated geos, period boundaries, injected truth). Deterministic: the same
seeds always produce the same files.

    python validation/make_cases.py validation/cases
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "core"))
from fosit import synthetic  # noqa: E402

N_DAYS, N_PRE, TEST_DAYS = 119, 84, 28   # 7 cooldown days at the end
CASES = [
    # name, seed, n_geos, n_treated, lift
    ("null_a", 101, 80, 8, 0.0),
    ("null_b", 102, 120, 12, 0.0),
    ("lift10_a", 103, 80, 8, 0.10),
    ("lift10_b", 104, 120, 12, 0.10),
    ("lift20_a", 105, 100, 10, 0.20),
    ("single_geo", 106, 60, 1, 0.15),
]


def main(out_dir: str) -> None:
    for name, seed, n_geos, n_treated, lift in CASES:
        rng = np.random.default_rng(seed)
        geos = [f"g{i:04d}" for i in range(n_geos)]   # lower-case: GeoLift lower-cases location names
        treated = sorted(rng.choice(geos, n_treated, replace=False).tolist())
        df, truth = synthetic.make_panel(n_geos=n_geos, n_days=N_DAYS, seed=seed, geo_prefix="g",
                                         lifts={"cell": (treated, N_PRE, N_PRE + TEST_DAYS - 1, lift)})
        folder = os.path.join(out_dir, name)
        os.makedirs(folder, exist_ok=True)
        df[["date", "geo_id", "orders"]].to_csv(os.path.join(folder, "data.csv"), index=False)
        case = {
            "name": name, "kpi": "orders", "treated": treated,
            "n_days": N_DAYS, "n_pre": N_PRE, "n_post": N_DAYS - N_PRE,
            # GeoLift time indices are 1-based; the measurement window includes the cooldown
            "treatment_start_time": N_PRE + 1, "treatment_end_time": N_DAYS,
            "true_incremental": truth.incremental_orders["cell"], "lift": lift,
        }
        with open(os.path.join(folder, "case.json"), "w") as f:
            json.dump(case, f, indent=2)
        print("wrote", folder)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "cases"))
