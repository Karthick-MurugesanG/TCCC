from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.ai_insights import (
    build_dashboard_payload,
    build_bootstrap_payload,
    generate_brand_summary,
    generate_brand_performance_pandas,
    generate_channel_summary,
    generate_customer_summary,
    generate_executive_summary,
    generate_region_summary,
    generate_root_cause_analysis,
    normalize_entity_value,
    identify_entity_type,
)

from services.analytics_storage import AnalyticsStorage

from config.db import init_db, SessionLocal, get_db
from services.cache_service import CacheService
import time
import json


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATE_DIR = FRONTEND_DIR / "templates"

CHANNEL_TEMPLATE_MAP = {
    "TEG": "channels.html",
    "PFM": "channels_pfm.html",
    "L&T": "channels_lt.html",
    "HORECA": "channels_horeca.html",
}


def _normalize_channel_key(channel: str | None) -> str:
    token = "".join(character for character in str(channel or "").upper() if character.isalnum())
    if token in {"PFM"}:
        return "PFM"
    if token == "LT":
        return "L&T"
    if token == "HORECA":
        return "HORECA"
    if token == "TEG":
        return "TEG"
    return "TEG"


def _dataset_reference() -> str:
    import os
    data_source_uri = os.getenv("TCCC_DATA_SOURCE_URI", "default_dataset")
    return Path(data_source_uri).stem or "default_dataset"

def _get_unique_dataset_ref(dataset_name: str, filters: dict[str, Any]) -> str:
    import json
    import hashlib
    filters_json = json.dumps(filters, sort_keys=True, default=str)
    filters_hash = hashlib.sha256(filters_json.encode()).hexdigest()[:16]
    return f"{dataset_name}:{filters_hash}"


app = FastAPI(title="TCCC South Africa Market Share Analytics")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# Initialize database on application startup
@app.on_event("startup")
async def startup_event():
    """Initialize database and create tables on app start"""
    init_db()
    print("[APP] Application started - PostgreSQL database initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on app shutdown"""
    print("[APP] Application shutting down")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _bootstrap(
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> dict:
    import os
    from pathlib import Path
    from config.db import SessionLocal
    from services.cache_service import CacheService
    from services.analytics_storage import AnalyticsStorage

    # Extract dataset name from TCCC_DATA_SOURCE_URI
    data_source_uri = os.getenv("TCCC_DATA_SOURCE_URI", "default_dataset")
    dataset_name = Path(data_source_uri).stem or "default_dataset"
    dataset_filters = {
        "brand": brand,
        "period": period,
        "year": year,
        "channel": channel,
        "customer": customer,
        "region": region,
    }

    # Generate a unique reference for this filter combination to prevent collisions
    dataset_ref = _get_unique_dataset_ref(dataset_name, dataset_filters)

    db = SessionLocal()
    try:
        # Check if we have cached data for this exact filter combination
        cached = CacheService.get_cached_result(
            db=db,
            dataset_reference=dataset_name,
            analytics_type="dashboard",
            filters=dataset_filters,
        )
        if cached:
            payload = cached.get("result") if isinstance(cached, dict) else cached.get("result")
            
            # Ensure specialized tables are populated for this hashed ref
            try:
                AnalyticsStorage.ensure_ui_analytics_persisted(db, dataset_ref, payload)
            except Exception as e:
                print(f"[DB] Warning: failed to persist cached payload for {dataset_ref}: {e}")

            return payload

        # No cache found - compute new payload
        print(f"[UI] Bootstrap cache miss for dataset {dataset_ref} with filters brand={brand}, period={period}, year={year}")
        payload = build_dashboard_payload(
            brand=brand,
            period=period,
            year=year,
            channel=channel,
            customer=customer,
            region=region,
        )

        # Check if this exact filter combination already exists in DB before storing
        from services.cache_service import CacheService
        cache_key = CacheService._generate_cache_key(dataset_filters, "dashboard")
        from models import CachedAnalyticsResult
        
        existing_record = db.query(CachedAnalyticsResult).filter(
            CachedAnalyticsResult.dataset_reference == dataset_name,
            CachedAnalyticsResult.analytics_type == "dashboard",
            CachedAnalyticsResult.cache_key == cache_key,
        ).first()

        if existing_record:
            # Record already exists - use existing data instead of storing new
            existing_payload = existing_record.result
            AnalyticsStorage.ensure_ui_analytics_persisted(db, dataset_ref, existing_payload)
            return existing_payload

        # Record doesn't exist - store the newly computed data
        CacheService.set_cached_result(
            db=db,
            dataset_reference=dataset_name,
            analytics_type="dashboard",
            filters=dataset_filters,
            result=payload,
            metrics={"source": "ui_bootstrap", "dataset_name": dataset_name},
            record_count=1,
        )

        AnalyticsStorage.store_ui_analytics(db, dataset_ref, payload)

        return payload
    finally:
        db.close()


def _render_page(
    request: Request,
    template_name: str,
    page_key: str,
    page_heading: str,
    *,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> HTMLResponse:
    bootstrap = _bootstrap(
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "page_title": f"TCCC South Africa Market Share Analytics - {page_heading}",
            "page_heading": page_heading,
            "page_key": page_key,
            "active_nav": page_key,
            "bootstrap": bootstrap,
        },
    )


def _render_channel_page(
    request: Request,
    *,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> HTMLResponse:
    bootstrap = _bootstrap(
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )
    selections = bootstrap.get("selections", {})
    selected_channel = _normalize_channel_key(selections.get("channel"))
    template_name = CHANNEL_TEMPLATE_MAP.get(selected_channel, "channels.html")
    channel_label = selections.get("channel_label") or selected_channel
    page_heading = f"{channel_label} Share Drilldown"
    return templates.TemplateResponse(
        template_name,
        {
            "request": request,
            "page_title": f"TCCC South Africa Market Share Analytics - {page_heading}",
            "page_heading": page_heading,
            "page_key": "channels",
            "active_nav": "channels",
            "bootstrap": bootstrap,
            "channel_key": selected_channel,
            "channel_label": channel_label,
            "channel_title": selections.get("channel_title"),
            "channel_description": selections.get("channel_description"),
        },
    )


def _render_brand_detail_page(
    request: Request,
    brand: str,
    *,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> HTMLResponse:
    bootstrap = _bootstrap(
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )
    selections = bootstrap.get("selections", {})
    resolved_brand = selections.get("brand") or brand
    resolved_period = selections.get("period")
    resolved_year = selections.get("year")
    resolved_channel = selections.get("channel")
    resolved_customer = selections.get("customer")
    resolved_region = selections.get("region")
    resolved_country = selections.get("country") or bootstrap.get("country")
    
    # using the pandasai
    # analysis = generate_executive_summary(
    #     prompt=f"Summarize {selections.get('brand_label') or brand} performance with draggers, drivers, and actions.",
    #     brand=resolved_brand,
    #     month=resolved_period,
    #     year=str(resolved_year) if resolved_year is not None else None,
    #     channel=resolved_channel,
    #     customer=resolved_customer,
    #     region=resolved_region,
    #     country=resolved_country,
    # )

    # using the pandas
    analysis = generate_brand_performance_pandas(
        brand=resolved_brand,
        month=resolved_period,
        year=str(resolved_year) if resolved_year is not None else None,
        channel=resolved_channel,
        customer=resolved_customer,
        region=resolved_region,
        country=resolved_country,
    )

    portfolio = bootstrap.get("portfolio", {})
    back_params = {
        key: value
        for key, value in (
            ("brand", resolved_brand),
            ("period", resolved_period),
            ("year", resolved_year),
            ("channel", resolved_channel),
            ("customer", resolved_customer),
            ("region", resolved_region),
        )
        if value not in (None, "")
    }
    back_href = "/brand-performance"
    if back_params:
        back_href = f"{back_href}?{urlencode(back_params)}"

    page_heading = f"{selections.get('brand_label') or brand} Detail"
    return templates.TemplateResponse(
        "brand_detail.html",
        {
            "request": request,
            "page_title": f"TCCC South Africa Market Share Analytics - {page_heading}",
            "page_heading": page_heading,
            "page_key": "brand-detail",
            "active_nav": "brand",
            "bootstrap": bootstrap,
            "analysis": analysis,
            "portfolio": portfolio,
            "selections": selections,
            "customers": bootstrap.get("customers", []),
            "regions": bootstrap.get("regions", []),
            "root_cause": bootstrap.get("root_cause", {}),
            "back_href": back_href,
        },
    )


@app.get("/", include_in_schema=False)
def page_root():
    return RedirectResponse(url="/dashboard", status_code=307)


@app.get("/dashboard", response_class=HTMLResponse)
def page_dashboard(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "index.html",
        "dashboard",
        "Dashboard",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/brand-performance", response_class=HTMLResponse)
def page_brand_performance(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "brand_performance.html",
        "brand",
        "Brand Performance",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/brand-performance/{brand}", response_class=HTMLResponse)
def page_brand_detail(
    request: Request,
    brand: str,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_brand_detail_page(
        request,
        brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/month-filter", response_class=HTMLResponse)
def page_month_filter(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "month_filter.html",
        "month",
        "Month Filter",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/analysis", response_class=HTMLResponse)
def page_analysis(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "analysis.html",
        "analysis",
        "Analysis Hub",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/analysis/customer", response_class=HTMLResponse)
def page_customer_analysis(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "customer_analysis.html",
        "customer",
        "Customer Analysis",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/analysis/regional", response_class=HTMLResponse)
def page_regional_analysis(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "regional_analysis.html",
        "regional",
        "Regional Analysis",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/analysis/channels/teg", response_class=HTMLResponse)
def page_channels(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_channel_page(
        request,
        brand=brand,
        period=period,
        year=year,
        channel="TEG",
        customer=customer,
        region=region,
    )


@app.get("/analysis/pfm", response_class=HTMLResponse)
def page_channels_pfm(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_channel_page(
        request,
        brand=brand,
        period=period,
        year=year,
        channel="PFM",
        customer=customer,
        region=region,
    )


@app.get("/analysis/lt", response_class=HTMLResponse)
def page_channels_lt(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_channel_page(
        request,
        brand=brand,
        period=period,
        year=year,
        channel="L&T",
        customer=customer,
        region=region,
    )


@app.get("/analysis/horeca", response_class=HTMLResponse)
def page_channels_horeca(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_channel_page(
        request,
        brand=brand,
        period=period,
        year=year,
        channel="HORECA",
        customer=customer,
        region=region,
    )


@app.get("/analysis/channels", include_in_schema=False)
def page_channels_redirect():
    return RedirectResponse(url="/analysis/channels/teg", status_code=307)


@app.get("/analysis/channels/{channel}", include_in_schema=False)
def page_channel_detail(channel: str):
    key = _normalize_channel_key(channel)
    if key == "PFM":
        target = "/analysis/pfm"
    elif key == "L&T":
        target = "/analysis/lt"
    elif key == "HORECA":
        target = "/analysis/horeca"
    else:
        target = "/analysis/channels/teg"
    return RedirectResponse(url=target, status_code=307)


@app.get("/root-cause", response_class=HTMLResponse)
def page_root_cause(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "root_cause.html",
        "root",
        "Root Cause",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/ask", response_class=HTMLResponse)
def page_ask(
    request: Request,
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return _render_page(
        request,
        "ask.html",
        "ask",
        "Ask AI",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/api/dashboard")
async def api_dashboard(
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    import os
    from pathlib import Path
    import time
    from config.db import SessionLocal
    from services.cache_service import CacheService
    from services.analytics_storage import AnalyticsStorage
    from models import CachedAnalyticsResult

    # Extract dataset name from TCCC_DATA_SOURCE_URI
    data_source_uri = os.getenv("TCCC_DATA_SOURCE_URI", "default_dataset")
    dataset_name = Path(data_source_uri).stem or "default_dataset"
    
    dataset_filters = {
        "brand": brand,
        "period": period,
        "year": year,
        "channel": channel,
        "customer": customer,
        "region": region,
    }

    # Generate a unique reference for this filter combination to prevent collisions in specialized tables
    dataset_ref = _get_unique_dataset_ref(dataset_name, dataset_filters)

    db = SessionLocal()
    try:
        # Try cache first
        cached_data = CacheService.get_cached_result(
            db=db,
            dataset_reference=dataset_name,
            analytics_type="dashboard",
            filters=dataset_filters,
        )
        if cached_data:
            cached_payload = cached_data.get("result") if isinstance(cached_data, dict) else None
            if isinstance(cached_payload, dict):
                cached_payload["_metadata"] = {
                    "from_cache": True,
                    "cached_at": cached_data.get("cached_at"),
                    "dataset_name": dataset_name,
                    **(cached_data.get("metrics") or {}),
                }
                return JSONResponse(content=cached_payload)

        # Try DB next using the unique filter-aware reference
        db_row = AnalyticsStorage.get_dashboard_summary_from_db(db, dataset_ref, dataset_filters)
        if db_row:
            db_row["_metadata"] = {"from_cache": True, "source": "db_reconstructed", "dataset_name": dataset_name}
            return JSONResponse(content=db_row)

        # No cache and no DB - compute fresh
        print(f"[API] Cache miss and DB miss for dataset {dataset_ref} - computing fresh")
        start_time = time.time()
        result = build_dashboard_payload(
            brand=brand,
            period=period,
            year=year,
            channel=channel,
            customer=customer,
            region=region,
        )
        execution_time = time.time() - start_time

        # Store in specialized tables for future reconstruction
        AnalyticsStorage.store_ui_analytics(db, dataset_ref, result)

        # Also store in general cache
        CacheService.set_cached_result(
            db=db,
            dataset_reference=dataset_name,
            analytics_type="dashboard",
            filters=dataset_filters,
            result=result,
            metrics={
                "source": "api_computed",
                "dataset_name": dataset_name,
                "execution_time_ms": int(execution_time * 1000)
            },
            record_count=1,
        )

        result["_metadata"] = {
            "from_cache": False,
            "dataset_name": dataset_name,
            "execution_time_ms": int(execution_time * 1000),
        }
        return JSONResponse(content=result)
    finally:
        db.close()

@app.post("/api/query")
def query_prompt(
    prompt: str = Form(...),
    mode: str | None = Form(default=None),
    brand: str | None = Form(default=None),
    month: str | None = Form(default=None),
    year: str | None = Form(default=None),
    channel: str | None = Form(default=None),
    customer: str | None = Form(default=None),
    region: str | None = Form(default=None),
    country: str | None = Form(default=None),
):
    """
    Query endpoint with response caching for Ask AI.
    
    Workflow:
    1. Check query history for exact same query
    2. If found & recent → return cached response
    3. If not found → call AI model
    4. Store query and response
    5. Return result
    """
    from config.db import SessionLocal
    from services.cache_service import CacheService
    
    db = SessionLocal()
    try:
        ask_mode = str(mode or "").strip().lower() == "ask"
        dataset_name = _dataset_reference()
        
        # Combine filters for uniqueness
        filters = {
            "brand": brand,
            "period": month,
            "year": year,
            "channel": channel,
            "customer": customer,
            "region": region,
        }
        dataset_ref = _get_unique_dataset_ref(dataset_name, filters)

        # Normalize the input parameters based on their entity types
        normalized_brand = normalize_entity_value(brand, "brand") if brand else None
        normalized_region = normalize_entity_value(region, "region") if region else None
        normalized_customer = normalize_entity_value(customer, "retailer_banner") if customer else None
        normalized_country = normalize_entity_value(country, "country") if country else None

        # Check if this query was asked before
        existing_query = CacheService.get_query_history(
            db=db,
            dataset_reference=dataset_ref,
            user_query=prompt,
            limit_days=30,
        )
        
        if existing_query:
            # Return cached AI response
            response = {
                "summary": existing_query.ai_response,
                "model": existing_query.model_name,
                "execution_time_ms": 0,
                "from_cache": True,
                "cached_at": existing_query.created_at.isoformat(),
            }
            return JSONResponse(content=response)
        
        # Execute fresh query with normalized parameters
        start_time = time.time()
        result = generate_executive_summary(
            prompt=prompt,
            brand=normalized_brand,
            month=month,
            year=year,
            channel=channel,
            customer=normalized_customer,
            region=normalized_region,
            country=normalized_country,
            ask_mode=ask_mode,
        )
        execution_time = int((time.time() - start_time) * 1000)
        
        # Extract AI response text
        ai_response = result.get("summary", "")
        
        # Store in query history only if it's a valid response (not a technical error or high-demand message)
        error_indicators = [
            "ServiceUnavailableError", 
            "GeminiException", 
            "Unexpected error", 
            "Unfortunately, I was not able to answer",
            "The AI assistant is currently experiencing high demand"
        ]
        should_store = ai_response and not any(err in ai_response for err in error_indicators)
        
        if should_store:
            CacheService.store_query_history(
                db=db,
                user_query=prompt,
                ai_response=ai_response,
                dataset_reference=dataset_ref,
                model_name="gemini",
                execution_time_ms=execution_time,
                cached_response=False,
            )
        else:
            print(f"[CACHE] Skipping storage for error/high-demand response: {ai_response[:100]}...")
        
        result["_metadata"] = {
            "from_cache": False,
            "execution_time_ms": execution_time,
        }
        
        return JSONResponse(content=result)
    
    finally:
        db.close()

from fastapi import Request
from fastapi.responses import JSONResponse
import traceback


@app.get("/invalidate-cache")
@app.post("/invalidate-cache")
async def invalidate_cache(
    request: Request,
    dataset_reference: str | None = None
):
    from config.db import SessionLocal
    from services.cache_service import CacheService

    try:

        payload = {}

        if request.headers.get("content-type", "").startswith("application/json"):
            payload = await request.json()

        dataset_reference = (
            dataset_reference
            or request.query_params.get("dataset_reference")
            or payload.get("dataset_reference")
        )

        if not dataset_reference:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "dataset_reference missing",
                    "query_params": dict(request.query_params),
                    "payload": payload
                }
            )

        db = SessionLocal()

        try:
            count = CacheService.invalidate_dataset_cache(
                db,
                dataset_reference
            )

            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Invalidated {count} cache entries",
                    "dataset_reference": dataset_reference
                }
            )

        finally:
            db.close()

    except Exception as e:
        print(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )


from fastapi import Request
from fastapi.responses import JSONResponse
import traceback


@app.get("/cache/stats", response_model=None)
async def cache_stats(
    request: Request,
    dataset_reference: str | None = None
):
    from config.db import SessionLocal
    from services.cache_service import CacheService

    try:

        payload = {}

        if request.headers.get("content-type", "").startswith("application/json"):
            payload = await request.json()

        dataset_reference = (
            dataset_reference
            or request.query_params.get("dataset_reference")
            or payload.get("dataset_reference")
        )

        if not dataset_reference:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "dataset_reference missing",
                    "query_params": dict(request.query_params),
                    "payload": payload
                }
            )

        db = SessionLocal()

        try:
            stats = CacheService.get_cache_stats(
                db,
                dataset_reference
            )

            return JSONResponse(content=stats)

        finally:
            db.close()

    except Exception as e:
        print(traceback.format_exc())

        return JSONResponse(
            status_code=500,
            content={
                "error": str(e),
                "traceback": traceback.format_exc()
            }
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8022)
