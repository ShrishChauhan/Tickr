"""
One-time upload of local historical Parquet files to Cloudflare R2 — Phase 7.1 follow-up.

Uploads every file in engine/data_historical/ (produced by backfill_historical.py)
to the R2 bucket configured via R2_* vars in .env, preserving filenames so the
existing DuckDB glob-based query pattern (read_parquet('*.parquet')) works
unchanged once pointed at R2. This is a manual, one-off script (not scheduled).

Run from repo root:
  engine/.venv/Scripts/python.exe engine/scripts/upload_to_r2.py
"""
import sys
import time
from pathlib import Path

import boto3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data_historical"


def r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def upload_one(client, path: Path) -> tuple[bool, str]:
    client.upload_file(str(path), settings.R2_BUCKET_NAME, path.name)
    return True, "uploaded"


def sanity_check(client, expected_count: int, expected_mb: float) -> None:
    paginator = client.get_paginator("list_objects_v2")
    count, total_bytes = 0, 0
    for page in paginator.paginate(Bucket=settings.R2_BUCKET_NAME):
        for obj in page.get("Contents", []):
            count += 1
            total_bytes += obj["Size"]

    total_mb = total_bytes / (1024 * 1024)
    print(f"\nBucket sanity check: {count} objects, {total_mb:.1f} MB total")
    print(f"Expected: {expected_count} objects, ~{expected_mb:.1f} MB (local size)")
    if count != expected_count:
        print(f"MISMATCH — expected {expected_count} objects, found {count}")


def main() -> None:
    files = sorted(DATA_DIR.glob("*.parquet"))
    print(f"Found {len(files)} local Parquet files in {DATA_DIR}")
    if not files:
        print("Nothing to upload — run backfill_historical.py first.")
        return

    local_mb = sum(f.stat().st_size for f in files) / (1024 * 1024)
    client = r2_client()

    ok, failed = 0, []
    start = time.time()
    for i, path in enumerate(files, 1):
        try:
            success, detail = upload_one(client, path)
        except Exception as exc:
            success, detail = False, str(exc)

        if success:
            ok += 1
        else:
            failed.append(path.name)
            print(f"[{i}/{len(files)}] {path.name}: FAIL ({detail})")

        if i % 50 == 0 or i == len(files):
            print(f"[{i}/{len(files)}] uploaded so far: {ok} succeeded, {len(failed)} failed")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s — {ok} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed:", ", ".join(failed))

    sanity_check(client, expected_count=len(files), expected_mb=local_mb)


if __name__ == "__main__":
    main()
