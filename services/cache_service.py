from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from models import (
    CachedAnalyticsResult,
    QueryHistory,
    DashboardSummary,
    BrandPerformance,
    RegionalAnalysis,
    ChannelAnalysis,
    CustomerAnalysis,
    RootCauseAnalysis,
)


class CacheService:
    """Service layer for managing cache operations"""

    @staticmethod
    def _generate_cache_key(
        filters: dict[str, Any],
        analytics_type: str
    ) -> str:
        """Generate deterministic cache key from filters"""
        sorted_filters = json.dumps(filters, sort_keys=True, default=str)
        hash_object = hashlib.sha256(sorted_filters.encode())
        return f"{analytics_type}:{hash_object.hexdigest()}"

    @staticmethod
    def _content_hash(data: Any) -> str:
        """Generate hash of cache content for invalidation detection"""
        content_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()

    @staticmethod
    def get_cached_result(
        db: Session,
        dataset_reference: str,
        analytics_type: str,
        filters: dict[str, Any],
        stale_hours: int = 24
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve cached analytics result if exists and not stale.
        
        Args:
            db: Database session
            dataset_reference: Dataset identifier
            analytics_type: Type of analytics (dashboard, brand, region, etc.)
            filters: Filter parameters used for computation
            stale_hours: Hours before cache is considered stale
        
        Returns:
            Cached result dict or None if not found/stale
        """
        cache_key = CacheService._generate_cache_key(filters, analytics_type)
        
        cached = db.query(CachedAnalyticsResult).filter(
            and_(
                CachedAnalyticsResult.dataset_reference == dataset_reference,
                CachedAnalyticsResult.analytics_type == analytics_type,
                CachedAnalyticsResult.cache_key == cache_key,
                CachedAnalyticsResult.is_stale == False
            )
        ).first()
        
        if not cached:
            return None
        
        # Check if cache is stale based on age
        from datetime import datetime, timezone

        age_hours = (datetime.now(timezone.utc) - cached.updated_at).total_seconds() / 3600
        if age_hours > stale_hours:
            cached.is_stale = True
            db.commit()
            return None
        
        return {
            "result": cached.result,
            "metrics": cached.metrics,
            "record_count": cached.record_count,
            "cached_at": cached.updated_at.isoformat(),
            "from_cache": True,
        }

    @staticmethod
    def set_cached_result(
        db: Session,
        dataset_reference: str,
        analytics_type: str,
        filters: dict[str, Any],
        result: dict[str, Any],
        metrics: Optional[dict[str, Any]] = None,
        record_count: Optional[int] = None,
    ) -> None:
        """
        Store analytics result in cache.
        """
        import logging
        logger = logging.getLogger(__name__)
        cache_key = CacheService._generate_cache_key(filters, analytics_type)
        content_hash = CacheService._content_hash(result)

        try:
            # Check if cache entry exists for this key
            existing = db.query(CachedAnalyticsResult).filter(
                and_(
                    CachedAnalyticsResult.dataset_reference == dataset_reference,
                    CachedAnalyticsResult.analytics_type == analytics_type,
                    CachedAnalyticsResult.cache_key == cache_key,
                )
            ).first()

            if existing:
                # Update existing cache
                existing.result = result
                existing.metrics = metrics
                existing.record_count = record_count
                existing.content_hash = content_hash
                existing.is_stale = False
                existing.updated_at = datetime.utcnow()
            else:
                # Create new cache entry
                cached_result = CachedAnalyticsResult(
                    dataset_reference=dataset_reference,
                    analytics_type=analytics_type,
                    cache_key=cache_key,
                    result=result,
                    metrics=metrics,
                    record_count=record_count,
                    content_hash=content_hash,
                    is_stale=False,
                )
                db.add(cached_result)

            db.commit()
        except Exception as exc:
            # Log the exception with details so writes don't silently fail
            try:
                logger.exception("Failed to write cached result: %s %s", analytics_type, cache_key)
            except Exception:
                print("Failed to write cached result", analytics_type, cache_key, exc, flush=True)
            # Optionally re-raise if you want the calling flow to surface errors:
            raise

    @staticmethod
    def get_query_history(
        db: Session,
        dataset_reference: str,
        user_query: str,
        limit_days: int = 30,
    ) -> Optional[dict[str, Any]]:
        """
        Retrieve similar query from history if exists.
        
        Args:
            db: Database session
            dataset_reference: Dataset identifier
            user_query: User query text
            limit_days: Look back this many days
        
        Returns:
            Query history record or None
        """
        cutoff_date = datetime.utcnow() - timedelta(days=limit_days)
        
        history = db.query(QueryHistory).filter(
            and_(
                QueryHistory.dataset_reference == dataset_reference,
                QueryHistory.user_query == user_query,
                QueryHistory.created_at >= cutoff_date,
            )
        ).order_by(QueryHistory.created_at.desc()).first()
        
        if history:
            # Automatic Cleanup: If this cached response is actually an error or a high-demand message,
            # delete it and act as if it's not in the cache.
            error_indicators = [
                "ServiceUnavailableError", 
                "GeminiException", 
                "Unexpected error", 
                "Unfortunately, I was not able to answer",
                "The AI assistant is currently experiencing high demand"
            ]
            if history.ai_response and any(err in history.ai_response for err in error_indicators):
                print(f"[CACHE] Auto-cleaning stale error record from history: {history.id}")
                db.delete(history)
                db.commit()
                return None

        return history

    @staticmethod
    def store_query_history(
        db: Session,
        user_query: str,
        ai_response: str,
        dataset_reference: Optional[str] = None,
        user_id: Optional[str] = None,
        model_name: Optional[str] = None,
        execution_time_ms: int = 0,
        cached_response: bool = False,
        dataset_snapshot_hash: Optional[str] = None,
    ) -> None:
        """
        Store query and response in history.
        
        Args:
            db: Database session
            user_query: The user's question
            ai_response: The AI's response
            dataset_reference: Dataset used
            user_id: User identifier
            model_name: AI model used
            execution_time_ms: Response time in milliseconds
            cached_response: Whether response was cached
            dataset_snapshot_hash: Hash of dataset used
        """
        query_record = QueryHistory(
            dataset_reference=dataset_reference,
            user_id=user_id,
            user_query=user_query,
            ai_response=ai_response,
            model_name=model_name or "gemini",
            execution_time_ms=execution_time_ms,
            cached_response=cached_response,
            dataset_snapshot_hash=dataset_snapshot_hash,
        )
        db.add(query_record)
        db.commit()

    @staticmethod
    def invalidate_dataset_cache(
        db: Session,
        dataset_reference: str,
    ) -> int:
        """
        Mark all cache entries for a dataset as stale.
        Used when dataset is updated/re-uploaded.
        
        Args:
            db: Database session
            dataset_reference: Dataset identifier
        
        Returns:
            Number of cache entries invalidated
        """
        count = db.query(CachedAnalyticsResult).filter(
            CachedAnalyticsResult.dataset_reference == dataset_reference
        ).update({CachedAnalyticsResult.is_stale: True})
        db.commit()
        return count

    @staticmethod
    def get_cache_stats(db: Session, dataset_reference: str) -> dict[str, Any]:
        """Get cache statistics for a dataset"""
        total_cached = db.query(CachedAnalyticsResult).filter(
            CachedAnalyticsResult.dataset_reference == dataset_reference
        ).count()
        
        fresh_cached = db.query(CachedAnalyticsResult).filter(
            and_(
                CachedAnalyticsResult.dataset_reference == dataset_reference,
                CachedAnalyticsResult.is_stale == False,
            )
        ).count()
        
        total_queries = db.query(QueryHistory).filter(
            QueryHistory.dataset_reference == dataset_reference
        ).count()
        
        cached_queries = db.query(QueryHistory).filter(
            and_(
                QueryHistory.dataset_reference == dataset_reference,
                QueryHistory.cached_response == True,
            )
        ).count()
        
        return {
            "total_cached_analytics": total_cached,
            "fresh_cached_analytics": fresh_cached,
            "total_queries": total_queries,
            "cached_queries": cached_queries,
            "cache_hit_rate": (
                cached_queries / total_queries * 100 if total_queries > 0 else 0
            ),
        }