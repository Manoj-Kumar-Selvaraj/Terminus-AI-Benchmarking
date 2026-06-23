#!/usr/bin/env python3
import csv
from pathlib import Path


APP = Path("/app")


def read_psv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="|"))


def main():
    # Intentionally under-implements the PL/I contract: no rule deck parsing,
    # partial id matching, no consumption, no windows.
    src = read_psv(APP / "data/trips.psv")
    acts = read_psv(APP / "data/credits.psv")
    out = []
    mc = uc = ma = ua = 0

    for action in acts:
        match = None
        for source in src:
            if (
                source["trip_id"][:5] == action["trip_id"][:5]
                and source["credit_cents"] == action["credit_cents"]
            ):
                match = source
                break

        amount = int(action["credit_cents"])
        if match:
            mc += 1
            ma -= amount
            status = "MATCHED"
            kind = match["fare_type"]
        else:
            uc += 1
            ua += amount
            status = "UNMATCHED"
            kind = ""

        out.append(
            [
                action["action_id"],
                action["trip_id"],
                action["rider_id"],
                action["station_id"],
                kind,
                action["credit_cents"],
                action["reason"],
                status,
            ]
        )

    (APP / "out").mkdir(exist_ok=True)
    with (APP / "out/delay_credit_report.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "action_id",
                "trip_id",
                "rider_id",
                "station_id",
                "fare_type",
                "credit_cents",
                "reason",
                "status",
            ]
        )
        writer.writerows(out)

    (APP / "out/delay_credit_summary.txt").write_text(
        f"matched_count={mc}\n"
        f"matched_amount_cents={ma}\n"
        f"unmatched_count={uc}\n"
        f"unmatched_amount_cents={ua}\n"
    )


if __name__ == "__main__":
    main()
