from __future__ import annotations

from typing import Any


def cronjob_service_account(cronjob: dict[str, Any]) -> tuple[str, str]:
    meta = cronjob.get("metadata", {})
    namespace = meta.get("namespace", "default")
    sa_name = (
        cronjob.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("serviceAccountName", "default")
    )
    return sa_name, namespace


def cronjob_concurrency_policy(cronjob: dict[str, Any]) -> str:
    return cronjob.get("spec", {}).get("concurrencyPolicy", "Allow")


def simulate_overlapping_runs(
    cronjob: dict[str, Any],
    *,
    first_start_minute: int,
    second_start_minute: int,
    job_duration_minutes: int,
    billing_window_id: str,
) -> dict[str, Any]:
    policy = cronjob_concurrency_policy(cronjob)
    first_end = first_start_minute + job_duration_minutes
    overlap = second_start_minute < first_end

    started_jobs = [{"job": "job-1", "start_minute": first_start_minute, "window_id": billing_window_id}]
    skipped_jobs: list[dict[str, Any]] = []

    if overlap:
        if policy == "Forbid":
            skipped_jobs.append(
                {
                    "job": "job-2",
                    "start_minute": second_start_minute,
                    "window_id": billing_window_id,
                    "reason": "concurrencyPolicy=Forbid",
                }
            )
        else:
            started_jobs.append(
                {"job": "job-2", "start_minute": second_start_minute, "window_id": billing_window_id}
            )

    published = [job["window_id"] for job in started_jobs]
    duplicate_windows = sorted({window for window in published if published.count(window) > 1})

    return {
        "concurrency_policy": policy,
        "overlap_detected": overlap,
        "started_jobs": started_jobs,
        "skipped_jobs": skipped_jobs,
        "published_window_ids": published,
        "duplicate_window_ids": duplicate_windows,
        "single_publication_per_window": len(duplicate_windows) == 0,
    }
