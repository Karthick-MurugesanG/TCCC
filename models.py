from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class DashboardSummary(Base):
    __tablename__ = "dashboard_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    total_sales_value = Column(Numeric(18, 2), nullable=True)
    total_sales_volume = Column(Numeric(18, 2), nullable=True)
    average_price = Column(Numeric(18, 2), nullable=True)
    market_share = Column(Numeric(8, 4), nullable=True)
    distribution = Column(Numeric(8, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_dashboard_summary_dataset_reference_period", "dataset_reference", "period_label"),
        Index("ix_dashboard_summary_dataset_reference_year", "dataset_reference", "year"),
        Index("ix_dashboard_summary_dataset_reference_country", "dataset_reference", "country"),
    )


class BrandPerformance(Base):
    __tablename__ = "brand_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    brand = Column(Text, nullable=False)
    channel = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    sales_value = Column(Numeric(18, 2), nullable=True)
    sales_volume = Column(Numeric(18, 2), nullable=True)
    price = Column(Numeric(18, 2), nullable=True)
    distribution = Column(Numeric(8, 4), nullable=True)
    growth_rate = Column(Numeric(8, 4), nullable=True)
    market_share = Column(Numeric(8, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_brand_performance_dataset_reference_brand_period",
            "dataset_reference",
            "brand",
            "period_label",
        ),
        Index(
            "ix_brand_performance_dataset_reference_channel_period",
            "dataset_reference",
            "channel",
            "period_label",
        ),
        Index("ix_brand_performance_dataset_reference_year_brand", "dataset_reference", "year", "brand"),
    )


class RegionalAnalysis(Base):
    __tablename__ = "regional_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    region = Column(Text, nullable=False)
    brand = Column(Text, nullable=True)
    channel = Column(Text, nullable=True)
    sales_value = Column(Numeric(18, 2), nullable=True)
    sales_volume = Column(Numeric(18, 2), nullable=True)
    distribution = Column(Numeric(8, 4), nullable=True)
    price = Column(Numeric(18, 2), nullable=True)
    share = Column(Numeric(8, 4), nullable=True)
    growth_rate = Column(Numeric(8, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_regional_analysis_dataset_reference_region_period",
            "dataset_reference",
            "region",
            "period_label",
        ),
        Index(
            "ix_regional_analysis_dataset_reference_country_region",
            "dataset_reference",
            "country",
            "region",
        ),
        Index("ix_regional_analysis_dataset_reference_year_region", "dataset_reference", "year", "region"),
    )


class ChannelAnalysis(Base):
    __tablename__ = "channel_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    channel = Column(Text, nullable=False)
    brand = Column(Text, nullable=True)
    sales_value = Column(Numeric(18, 2), nullable=True)
    sales_volume = Column(Numeric(18, 2), nullable=True)
    distribution = Column(Numeric(8, 4), nullable=True)
    price = Column(Numeric(18, 2), nullable=True)
    share = Column(Numeric(8, 4), nullable=True)
    growth_rate = Column(Numeric(8, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_channel_analysis_dataset_reference_channel_period",
            "dataset_reference",
            "channel",
            "period_label",
        ),
        Index("ix_channel_analysis_dataset_reference_year_channel", "dataset_reference", "year", "channel"),
    )


class CustomerAnalysis(Base):
    __tablename__ = "customer_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    period_label = Column(Text, nullable=False)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    customer = Column(Text, nullable=False)
    region = Column(Text, nullable=True)
    channel = Column(Text, nullable=True)
    brand = Column(Text, nullable=True)
    sales_value = Column(Numeric(18, 2), nullable=True)
    sales_volume = Column(Numeric(18, 2), nullable=True)
    average_price = Column(Numeric(18, 2), nullable=True)
    transaction_count = Column(Integer, nullable=True)
    churn_rate = Column(Numeric(8, 4), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "ix_customer_analysis_dataset_reference_customer_period",
            "dataset_reference",
            "customer",
            "period_label",
        ),
        Index(
            "ix_customer_analysis_dataset_reference_region_customer",
            "dataset_reference",
            "region",
            "customer",
        ),
    )


class RootCauseAnalysis(Base):
    __tablename__ = "root_cause_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    analysis_key = Column(Text, nullable=False)
    period_label = Column(Text, nullable=True)
    year = Column(Integer, nullable=True)
    month_name = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    brand = Column(Text, nullable=True)
    region = Column(Text, nullable=True)
    channel = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=False)
    impact_score = Column(Numeric(6, 4), nullable=True)
    metric_name = Column(Text, nullable=True)
    metric_value = Column(Numeric(18, 2), nullable=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_root_cause_analysis_dataset_reference_key", "dataset_reference", "analysis_key"),
        Index("ix_root_cause_analysis_dataset_reference_root_cause", "dataset_reference", "root_cause"),
        Index("ix_root_cause_analysis_dataset_reference_period", "dataset_reference", "period_label"),
    )


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=True)
    user_id = Column(Text, nullable=True)
    user_query = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    model_name = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=False)
    cached_response = Column(Boolean, nullable=False, default=False)
    dataset_snapshot_hash = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_query_history_dataset_reference_created_at", "dataset_reference", "created_at"),
        Index("ix_query_history_cached_response", "cached_response"),
        Index("ix_query_history_user_query", "user_query"),
    )


class CachedAnalyticsResult(Base):
    __tablename__ = "cached_analytics_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_reference = Column(Text, nullable=False)
    analytics_type = Column(Text, nullable=False)
    cache_key = Column(Text, nullable=False)
    result = Column(JSONB, nullable=False)
    metrics = Column(JSONB, nullable=True)
    record_count = Column(Integer, nullable=True)
    content_hash = Column(Text, nullable=False)
    is_stale = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "dataset_reference",
            "analytics_type",
            "cache_key",
            name="uq_cached_analytics_result_dataset_reference_type_key",
        ),
        Index(
            "ix_cached_analytics_results_dataset_reference_type_stale",
            "dataset_reference",
            "analytics_type",
            "is_stale",
        ),
        Index("ix_cached_analytics_results_dataset_reference_cache_key", "dataset_reference", "cache_key"),
    )