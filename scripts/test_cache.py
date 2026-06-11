"""
Run this script locally to test CacheService writes and reads.
Usage:
    python scripts/test_cache.py
"""

import json
import time
from config.db import SessionLocal
from services.cache_service import CacheService

def main():
    db = SessionLocal()
    try:
        dataset_filters = {"brand": "Coke", "period": "2025-05"}
        dataset_ref = "test_dataset_local"  # choose a stable string for testing
        analytics_type = "dashboard"

        sample_result = {"hello": "world", "ts": int(time.time())}

        print("Writing cache entry...")
        CacheService.set_cached_result(
            db=db,
            dataset_reference=dataset_ref,
            analytics_type=analytics_type,
            filters=dataset_filters,
            result=sample_result,
            metrics={"execution_time_ms": 10},
            record_count=1,
        )
        print("Write complete. Now reading back...")

        cached = CacheService.get_cached_result(
            db=db,
            dataset_reference=dataset_ref,
            analytics_type=analytics_type,
            filters=dataset_filters,
            stale_hours=1000,
        )
        print("Cached read result:", json.dumps(cached, indent=2, default=str))
    finally:
        db.close()

if __name__ == "__main__":
    main()