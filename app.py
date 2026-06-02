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
    generate_channel_summary,
    generate_customer_summary,
    generate_executive_summary,
    generate_region_summary,
    generate_root_cause_analysis,
)


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
    if token in {"PFM", "PMF"}:
        return "PFM"
    if token == "LT":
        return "L&T"
    if token == "HORECA":
        return "HORECA"
    if token == "TEG":
        return "TEG"
    return "TEG"


app = FastAPI(title="TCCC South Africa Market Share Analytics")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _bootstrap(
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> dict:
    return build_dashboard_payload(
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


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

    analysis = generate_executive_summary(
        prompt=f"Summarize {selections.get('brand_label') or brand} performance with draggers, drivers, and actions.",
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


@app.get("/analysis/pmf", response_class=HTMLResponse)
def page_channels_pmf(
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
        target = "/analysis/pmf"
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
        "Ask Gemini",
        brand=brand,
        period=period,
        year=year,
        channel=channel,
        customer=customer,
        region=region,
    )


@app.get("/api/bootstrap")
def api_bootstrap():
    return JSONResponse(content=_bootstrap())


@app.get("/api/dashboard")
def api_dashboard(
    brand: str | None = None,
    period: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
):
    return JSONResponse(
        content=build_dashboard_payload(
            brand=brand,
            period=period,
            year=year,
            channel=channel,
            customer=customer,
            region=region,
        )
    )


@app.get("/api/brands_share")
def brands_share():
    return JSONResponse(content=_bootstrap()["portfolio"]["brand_cards"])


@app.get("/api/brand/{brand}")
def brand_summary(brand: str, period: str | None = None):
    return JSONResponse(content=generate_brand_summary(brand, period=period))


@app.get("/api/month/{month}/brand/{brand}/channels")
def month_brand_channels(month: str, brand: str):
    return JSONResponse(content=generate_channel_summary(brand=brand, period=month)["channel_rows"])


@app.get("/api/channel/{channel}/customers")
def channel_customers(channel: str, brand: str | None = None, month: str | None = None):
    return JSONResponse(content=generate_customer_summary(brand=brand, month=month, channel=channel)["customer_rows"])


@app.get("/api/customer/{customer}/regions")
def customer_regions(
    customer: str,
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
):
    return JSONResponse(content=generate_region_summary(brand=brand, month=month, channel=channel, customer=customer)["region_rows"])


@app.get("/api/region/{region}/drivers")
def region_drivers(
    region: str,
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
    customer: str | None = None,
):
    return JSONResponse(content=generate_root_cause_analysis(brand=brand, month=month, channel=channel, customer=customer, region=region))


@app.get("/api/root-cause")
def root_cause(
    region: str | None = None,
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
    customer: str | None = None,
):
    return JSONResponse(content=generate_root_cause_analysis(brand=brand, month=month, channel=channel, customer=customer, region=region))


@app.get("/api/chart-data")
def chart_data(
    level: str = "overview",
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
    customer: str | None = None,
    region: str | None = None,
):
    if level == "brand":
        return JSONResponse(content=generate_brand_summary(brand))
    if level == "channel":
        return JSONResponse(content=generate_channel_summary(brand=brand, month=month))
    if level == "customer":
        return JSONResponse(content=generate_customer_summary(brand=brand, month=month, channel=channel))
    if level == "region":
        return JSONResponse(content=generate_region_summary(brand=brand, month=month, channel=channel, customer=customer))
    if level == "root_cause":
        return JSONResponse(content=generate_root_cause_analysis(brand=brand, month=month, channel=channel, customer=customer, region=region))
    return JSONResponse(content=_bootstrap())


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
    ask_mode = str(mode or "").strip().lower() == "ask"
    return JSONResponse(
        content=generate_executive_summary(
            prompt=prompt,
            brand=None if ask_mode else brand,
            month=None if ask_mode else month,
            year=None if ask_mode else year,
            channel=None if ask_mode else channel,
            customer=None if ask_mode else customer,
            region=None if ask_mode else region,
            country=None if ask_mode else country,
            ask_mode=ask_mode,
        )
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8022)
