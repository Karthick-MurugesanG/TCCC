from __future__ import annotations

from typing import Any
from sqlalchemy.orm import Session

from models import (
    DashboardSummary,
    BrandPerformance,
    RegionalAnalysis,
    ChannelAnalysis,
    CustomerAnalysis,
    RootCauseAnalysis,
)


class AnalyticsStorage:
    @staticmethod
    def store_ui_analytics(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        AnalyticsStorage.store_dashboard_summary(db, dataset_reference, payload)
        AnalyticsStorage.store_brand_performance(db, dataset_reference, payload)
        AnalyticsStorage.store_channel_analysis(db, dataset_reference, payload)
        AnalyticsStorage.store_customer_analysis(db, dataset_reference, payload)
        AnalyticsStorage.store_regional_analysis(db, dataset_reference, payload)
        AnalyticsStorage.store_root_cause_analysis(db, dataset_reference, payload)

    @staticmethod
    def store_dashboard_summary(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        portfolio = payload["portfolio"]

        row = DashboardSummary(
            dataset_reference=dataset_reference,
            period_label=selections["period_label"],
            year=selections["year"],
            month_name=selections["month"],
            country=selections["country"],
            total_sales_value=portfolio.get("market_size_value"),
            total_sales_volume=portfolio.get("market_size_volume"),
            average_price=portfolio.get("avg_price"),
            market_share=portfolio.get("brand_value_share_pct"),
            distribution=portfolio.get("portfolio_value_share_pct"),
        )
        db.add(row)
        db.commit()

    @staticmethod
    def is_dashboard_summary_present(db: Session, dataset_reference: str) -> bool:
        """Return True if a dashboard_summary row exists for dataset_reference."""
        try:
            return (
                db.query(DashboardSummary)
                .filter(DashboardSummary.dataset_reference == dataset_reference)
                .limit(1)
                .count()
                > 0
            )
        except Exception:
            return False
        
    @staticmethod
    def get_dashboard_summary_from_db(db: Session, dataset_reference: str, filters: dict[str, Any] | None = None) -> dict | None:
        """
        Reconstruct a dashboard-style payload for the given dataset_reference.
        If an exact match by dataset_reference+period/year isn't found, attempt:
         - legacy dataset_reference (md5 of filters)
         - fallback by matching period_label/year across any dataset_reference
        Returns None if nothing suitable is found.
        """
        import json
        import hashlib
        try:
            from sqlalchemy import func
            from services.ai_insights import build_bootstrap_payload
        except Exception:
            from services.ai_insights import build_bootstrap_payload  # fallback

        try:
            # Normalize filters
            filters = filters or {}
            req_period = filters.get("period")
            req_year = filters.get("year")

            # Helper to find a DashboardSummary by dataset_reference + period/year (if available)
            def find_summary_by_ref(ref: str):
                q = db.query(DashboardSummary).filter(DashboardSummary.dataset_reference == ref)
                if req_period:
                    q = q.filter(DashboardSummary.period_label == req_period)
                if req_year:
                    try:
                        q = q.filter(DashboardSummary.year == int(req_year))
                    except Exception:
                        pass
                return q.order_by(DashboardSummary.created_at.desc()).first()

            # 1) Try exact dataset_reference match
            summary = find_summary_by_ref(dataset_reference)
            if not summary:
                # 2) Try legacy md5(dataset_filters) dataset_reference if filters provided
                if filters:
                    legacy_ref = hashlib.md5(json.dumps(filters, sort_keys=True, default=str).encode()).hexdigest()
                    summary = find_summary_by_ref(legacy_ref)

            # 3) Fallback: find any DashboardSummary that matches period/year
            if not summary and req_period:
                q = db.query(DashboardSummary)
                q = q.filter(DashboardSummary.period_label == req_period)
                if req_year:
                    try:
                        q = q.filter(DashboardSummary.year == int(req_year))
                    except Exception:
                        pass
                summary = q.order_by(DashboardSummary.created_at.desc()).first()

            if not summary:
                return None

            # Build payload using the selected summary's period_label/year
            base = build_bootstrap_payload()
            filters_meta = base.get("filters", {})
            ai_meta = base.get("ai", {"pandasai_available": False, "gemini_configured": False, "gemini_key_count": 0})

            period_label = summary.period_label
            year = summary.year

            total_market_value = float(summary.total_sales_value) if summary.total_sales_value is not None else 0.0
            total_market_volume = float(summary.total_sales_volume) if summary.total_sales_volume is not None else 0.0

            # Reconstruct channels
            from services.ai_insights import CHANNEL_DEFINITIONS
            ch_rows = (
                db.query(ChannelAnalysis)
                .filter(ChannelAnalysis.dataset_reference == summary.dataset_reference, ChannelAnalysis.period_label == period_label)
                .all()
            )
            channels = []
            for r in ch_rows:
                # Find definition for this key to get correct label/title/desc
                defn = next((d for d in CHANNEL_DEFINITIONS if d["key"] == r.channel), {"label": r.channel, "title": "", "description": ""})
                channels.append(
                    {
                        "key": r.channel,
                        "label": defn["label"],
                        "title": defn["title"],
                        "description": defn["description"],
                        "value_share": float(r.share) if r.share is not None else 0.0,
                        "volume_share": float(r.sales_volume) if r.sales_volume is not None else 0.0,
                        "growth": float(r.growth_rate) if r.growth_rate is not None else 0.0,
                        "revenue": float(r.sales_value) if r.sales_value is not None else 0.0,
                        "volume": float(r.sales_volume) if r.sales_volume is not None else 0.0,
                        "share_of_brand": float(r.distribution) if getattr(r, "distribution", None) is not None else 0.0,
                    }
                )

            # Brand cards (top brands)
            brand_rows = (
                db.query(BrandPerformance)
                .filter(BrandPerformance.dataset_reference == summary.dataset_reference, BrandPerformance.period_label == period_label)
                .order_by(BrandPerformance.sales_value.desc())
                .limit(8)
                .all()
            )
            brand_cards = []
            for idx, r in enumerate(brand_rows, start=1):
                brand_cards.append(
                    {
                        "brand": r.brand,
                        "value": float(r.sales_value or 0.0),
                        "volume": float(r.sales_volume or 0.0),
                        "value_share_pct": (float(r.sales_value or 0.0) / max(total_market_value, 1) * 100) if total_market_value else 0.0,
                        "volume_share_pct": (float(r.sales_volume or 0.0) / max(total_market_volume, 1) * 100) if total_market_volume else 0.0,
                        "rank": int(idx),
                    }
                )

            # Customers
            cust_rows = (
                db.query(CustomerAnalysis)
                .filter(CustomerAnalysis.dataset_reference == summary.dataset_reference, CustomerAnalysis.period_label == period_label)
                .order_by(CustomerAnalysis.sales_value.desc())
                .all()
            )
            customers = []
            for r in cust_rows:
                customers.append(
                    {
                        "name": r.customer,
                        "value_share": (float(r.sales_value or 0.0) / max(total_market_value, 1) * 100) if total_market_value else 0.0,
                        "volume_share": (float(r.sales_volume or 0.0) / max(total_market_volume, 1) * 100) if total_market_volume else 0.0,
                        "revenue": float(r.sales_value or 0.0),
                        "volume": float(r.sales_volume or 0.0),
                    }
                )

            # Regions
            region_rows = (
                db.query(RegionalAnalysis)
                .filter(RegionalAnalysis.dataset_reference == summary.dataset_reference, RegionalAnalysis.period_label == period_label)
                .order_by(RegionalAnalysis.sales_value.desc())
                .all()
            )
            regions = []
            for r in region_rows:
                regions.append(
                    {
                        "name": r.region,
                        "market_share": float(r.share or 0.0),
                        "growth": float(r.growth_rate or 0.0),
                        "revenue": float(r.sales_value or 0.0),
                        "volume": float(r.sales_volume or 0.0),
                        "distribution": float(r.distribution or 0.0),
                    }
                )

            # Root cause (latest if present)
            root_row = (
                db.query(RootCauseAnalysis)
                .filter(RootCauseAnalysis.dataset_reference == summary.dataset_reference, RootCauseAnalysis.period_label == period_label)
                .order_by(RootCauseAnalysis.created_at.desc())
                .first()
            )
            root_cause = {}
            if root_row:
                root_cause = {"summary": root_row.root_cause or "", "reasons": [], "drivers": [], "actions": []}

            # Periods list
            period_rows = (
                db.query(DashboardSummary.period_label, DashboardSummary.month_name, DashboardSummary.year)
                .filter(DashboardSummary.dataset_reference == summary.dataset_reference)
                .group_by(DashboardSummary.period_label, DashboardSummary.month_name, DashboardSummary.year)
                .order_by(DashboardSummary.year.desc())
                .all()
            )
            periods = [{"key": pr.period_label, "short": pr.month_name or pr.period_label, "year": pr.year} for pr in period_rows]

            # Selections inferred: keep brand/channel empty unless we can detect a single brand
            selections = {
                "brand": "",
                "brand_label": "",
                "brand_subject": "",
                "country": summary.country,
                "period": period_label,
                "period_label": period_label,
                "month": summary.month_name,
                "year": year,
                "channel": "",
                "channel_label": "",
                "channel_title": "",
                "channel_description": "",
                "customer": "",
                "region": "",
            }

            portfolio = {
                "market_size_value": total_market_value,
                "market_size_volume": total_market_volume,
                "portfolio_value_share_pct": float(summary.distribution) if summary.distribution is not None else 0.0,
                "portfolio_volume_share_pct": 0.0,
                "brand_value_share_pct": float(summary.market_share) if summary.market_share is not None else 0.0,
                "brand_volume_share_pct": 0.0,
                "brand_growth_pct": 0.0,
                "selected_brand_rank": None,
                "brand_cards": brand_cards,
            }

            payload = {
                "country": summary.country,
                "filters": filters_meta,
                "selections": selections,
                "portfolio": portfolio,
                "periods": periods,
                "channels": channels,
                "customers": customers,
                "regions": regions,
                "root_cause": root_cause,
                "ai": ai_meta,
            }
            return payload
        except Exception as exc:
            print(f"[DB] Error reconstructing dashboard payload for {dataset_reference}: {exc}")
            return None

    @staticmethod
    def ensure_ui_analytics_persisted(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        """
        Ensure the structured analytics tables contain rows for this dataset_reference.
        If not present, persist payload to the per-tab tables.
        """
        try:
            if not AnalyticsStorage.is_dashboard_summary_present(db, dataset_reference):
                AnalyticsStorage.store_ui_analytics(db, dataset_reference, payload)
        except Exception as exc:
            print(f"[DB] Error persisting UI analytics for {dataset_reference}: {exc}")
            # do not re-raise to avoid breaking UI response

    @staticmethod
    def store_brand_performance(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        brand = selections["brand"] or selections["brand_label"]
        period_label = selections["period_label"]
        year = selections["year"]

        rows = []
        for item in payload["channels"]:
            rows.append(
                BrandPerformance(
                    dataset_reference=dataset_reference,
                    period_label=period_label,
                    year=year,
                    month_name=selections["month"],
                    brand=brand,
                    channel=item.get("key"),
                    country=selections["country"],
                    sales_value=item.get("revenue"),
                    sales_volume=item.get("volume"),
                    price=None,
                    distribution=item.get("share_of_brand"),
                    growth_rate=item.get("growth"),
                    market_share=item.get("value_share"),
                )
            )
        db.add_all(rows)
        db.commit()

    @staticmethod
    def store_channel_analysis(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        period_label = selections["period_label"]
        year = selections["year"]

        rows = []
        for item in payload["channels"]:
            rows.append(
                ChannelAnalysis(
                    dataset_reference=dataset_reference,
                    period_label=period_label,
                    year=year,
                    month_name=selections["month"],
                    country=selections["country"],
                    channel=item.get("key"),
                    brand=selections["brand"],
                    sales_value=item.get("revenue"),
                    sales_volume=item.get("volume"),
                    distribution=item.get("share_of_brand"),
                    price=None,
                    share=item.get("value_share"),
                    growth_rate=item.get("growth"),
                )
            )
        db.add_all(rows)
        db.commit()

    @staticmethod
    def store_customer_analysis(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        period_label = selections["period_label"]
        year = selections["year"]

        rows = []
        for item in payload["customers"]:
            rows.append(
                CustomerAnalysis(
                    dataset_reference=dataset_reference,
                    period_label=period_label,
                    year=year,
                    month_name=selections["month"],
                    country=selections["country"],
                    customer=item.get("name"),
                    region=None,
                    channel=selections["channel"],
                    brand=selections["brand"],
                    sales_value=item.get("revenue"),
                    sales_volume=item.get("volume"),
                    average_price=None,
                    transaction_count=None,
                    churn_rate=None,
                )
            )
        db.add_all(rows)
        db.commit()

    @staticmethod
    def store_regional_analysis(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        period_label = selections["period_label"]
        year = selections["year"]

        rows = []
        for item in payload["regions"]:
            rows.append(
                RegionalAnalysis(
                    dataset_reference=dataset_reference,
                    period_label=period_label,
                    year=year,
                    month_name=selections["month"],
                    country=selections["country"],
                    region=item.get("name"),
                    brand=selections["brand"],
                    channel=selections["channel"],
                    sales_value=item.get("revenue"),
                    sales_volume=item.get("volume"),
                    distribution=item.get("distribution"),
                    price=None,
                    share=item.get("market_share"),
                    growth_rate=item.get("growth"),
                )
            )
        db.add_all(rows)
        db.commit()

    @staticmethod
    def store_root_cause_analysis(db: Session, dataset_reference: str, payload: dict[str, Any]) -> None:
        selections = payload["selections"]
        root_cause = payload.get("root_cause") or {}
        if not root_cause:
            return

        row = RootCauseAnalysis(
            dataset_reference=dataset_reference,
            analysis_key=f"{dataset_reference}::{selections['brand']}::{selections['channel']}::{selections['customer']}::{selections['region']}",
            period_label=selections["period_label"],
            year=selections["year"],
            month_name=selections["month"],
            country=selections["country"],
            brand=selections["brand"],
            region=selections["region"],
            channel=selections["channel"],
            root_cause=root_cause.get("summary", ""),
            impact_score=None,
            metric_name=None,
            metric_value=None,
            explanation=str(root_cause),
        )
        db.add(row)
        db.commit()