from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from services.data_sources import load_data_catalog
from services.data_sources import _normalize_text

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parents[1]
ALL_BRAND_LABEL = "All Brands"

CHANNEL_DEFINITIONS = [
    {
        "key": "TEG",
        "label": "TEG",
        "title": "TEG Analytics",
        "description": "Specialized analytics-as-a-service focused on fast, automated business insights.",
    },
    {
        "key": "PFM",
        "label": "PMF",
        "title": "Personal Finance Management",
        "description": "Digital tooling used to track, understand, and optimize spending behavior.",
    },
    {
        "key": "L&T",
        "label": "L&T",
        "title": "Larsen & Toubro",
        "description": "Engineering and enterprise operations environments using advanced analytics.",
    },
    {
        "key": "HORECA",
        "label": "HoReCa",
        "title": "Hotel, Restaurant, Cafe",
        "description": "Food service and hospitality outlets where margin and consumer behavior matter.",
    },
]


def _channel_definition(channel: str | None) -> dict[str, Any]:
    desired = _normalize_text(channel)
    if not desired:
        return CHANNEL_DEFINITIONS[0]

    for definition in CHANNEL_DEFINITIONS:
        if desired in {_normalize_text(definition["key"]), _normalize_text(definition["label"])}:
            return definition

    return CHANNEL_DEFINITIONS[0]


def _normalize_channel(channel: str | None) -> str:
    return _channel_definition(channel)["key"]

DATA_CATALOG = load_data_catalog(BASE_DIR)
DF = DATA_CATALOG.frame


try:
    from pandasai import SmartDataframe

    PANDASAI_AVAILABLE = True
except Exception:
    SmartDataframe = None
    PANDASAI_AVAILABLE = False


def _safe_float(value: Any) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def _round(value: Any, digits: int = 2) -> float:
    return round(_safe_float(value), digits)


def _share(part: Any, total: Any) -> float:
    total_value = _safe_float(total)
    if total_value == 0:
        return 0.0
    return round(_safe_float(part) / total_value * 100, 2)


def _growth(current: Any, previous: Any) -> float:
    previous_value = _safe_float(previous)
    if previous_value == 0:
        return 0.0
    return round((_safe_float(current) - previous_value) / previous_value * 100, 2)


def _delta(current: Any, previous: Any) -> float:
    return round(_safe_float(current) - _safe_float(previous), 2)


def _is_all_brand(brand: str | None) -> bool:
    if brand is None:
        return True
    text = str(brand).strip()
    return text == "" or text.upper() == "ALL"


def _brand_label(brand: str | None) -> str:
    return ALL_BRAND_LABEL if _is_all_brand(brand) else str(brand)


def _brand_subject(brand: str | None) -> str:
    return "the market" if _is_all_brand(brand) else str(brand)


def _parse_period(period: Any) -> dict[str, Any]:
    text = str(period)
    prefix = text.split(" - ")[0].strip()
    parsed = pd.to_datetime(prefix, format="%b %y", errors="coerce")

    end_match = re.search(r"(\d{2}/\d{2}/\d{2})\s*$", text)
    end_date = pd.NaT
    if end_match:
        end_date = pd.to_datetime(end_match.group(1), format="%d/%m/%y", errors="coerce")

    sort_date = end_date if pd.notna(end_date) else parsed
    if pd.isna(sort_date):
        sort_date = pd.to_datetime(text, errors="coerce")
    if pd.isna(sort_date):
        sort_date = pd.Timestamp.min

    month_date = parsed if pd.notna(parsed) else sort_date
    if pd.isna(month_date) or month_date == pd.Timestamp.min:
        return {
            "key": text,
            "label": text,
            "short": text[:3],
            "month": text,
            "year": "Unknown",
            "sort": sort_date,
        }

    return {
        "key": text,
        "label": month_date.strftime("%b %Y"),
        "short": month_date.strftime("%b"),
        "month": month_date.strftime("%B"),
        "year": int(month_date.year),
        "sort": sort_date,
    }


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()

    for column in ("Brand", "Period", "Customer", "Region", "Category"):
        if column not in prepared.columns:
            prepared[column] = "Unknown"
        prepared[column] = prepared[column].fillna("Unknown").astype(str)

    for column in ("SalesValue", "SalesVolume", "Distribution", "Price", "PricePerCase"):
        if column not in prepared.columns:
            prepared[column] = 0
        prepared[column] = pd.to_numeric(prepared[column], errors="coerce").fillna(0)

    period_meta = prepared["Period"].map(_parse_period)
    prepared["PeriodKey"] = period_meta.map(lambda item: item["key"])
    prepared["PeriodLabel"] = period_meta.map(lambda item: item["label"])
    prepared["PeriodShort"] = period_meta.map(lambda item: item["short"])
    prepared["MonthName"] = period_meta.map(lambda item: item["month"])
    prepared["Year"] = period_meta.map(lambda item: item["year"])
    prepared["PeriodSort"] = period_meta.map(lambda item: item["sort"])
    prepared["BrandKey"] = prepared["Brand"].str.upper()

    if "Channel" not in prepared.columns:
        prepared["Channel"] = "TEG"
    else:
        prepared["Channel"] = prepared["Channel"].fillna("TEG").map(lambda value: str(value).strip().upper() or "TEG")

    if "IsPortfolio" not in prepared.columns:
        prepared["IsPortfolio"] = False
    else:
        prepared["IsPortfolio"] = prepared["IsPortfolio"].map(lambda value: bool(value))

    if "Country" not in prepared.columns:
        prepared["Country"] = DATA_CATALOG.country
    else:
        prepared["Country"] = prepared["Country"].fillna(DATA_CATALOG.country)

    return prepared


DF = _prepare_dataframe(DATA_CATALOG.frame)

GEMINI_MODEL = "gemini/gemini-2.5-flash"
GEMINI_MAX_KEYS = 5
_GEMINI_KEY_INDEX = 0
_GEMINI_KEY_LOCK = Lock()
ANALYTICS_COLUMNS = [
    "PeriodLabel",
    "MonthName",
    "Year",
    "Country",
    "Brand",
    "Channel",
    "Customer",
    "Region",
    "SalesValue",
    "SalesVolume",
    "Distribution",
    "Price",
]


def _split_key_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r"[,\s]+", value) if item.strip()]


def _validate_gemini_key(api_key: str) -> bool:
    """Validate if a Gemini API key has the correct format"""
    if not api_key:
        return False
    # Gemini API keys start with AIzaSy and are typically 39 characters
    if not api_key.startswith("AIzaSy"):
        return False
    return True

def _configured_gemini_keys() -> list[str]:
    list_value = os.getenv("GEMINI_API_KEYS") or os.getenv("GOOGLE_API_KEYS")
    keys = _split_key_values(list_value)
    if keys:
        # Validate each key
        valid_keys = [k for k in keys[:GEMINI_MAX_KEYS] if _validate_gemini_key(k)]
        if valid_keys:
            return valid_keys
        print(f"Warning: Found {len(keys)} keys but none have valid format")

    numbered_keys: list[str] = []
    for index in range(1, GEMINI_MAX_KEYS + 1):
        candidate = os.getenv(f"GEMINI_API_KEY_{index}") or os.getenv(f"GOOGLE_API_KEY_{index}")
        if candidate:
            candidate = candidate.strip()
        if candidate and candidate not in numbered_keys and _validate_gemini_key(candidate):
            numbered_keys.append(candidate)

    fallback_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    if numbered_keys:
        if fallback_key and fallback_key not in numbered_keys and _validate_gemini_key(fallback_key):
            numbered_keys.insert(0, fallback_key)
        return numbered_keys[:GEMINI_MAX_KEYS]

    if fallback_key and _validate_gemini_key(fallback_key):
        return [fallback_key]
    
    print("No valid Gemini API keys found. Please check your environment variables.")
    return []

def load_data_with_retry(max_retries: int = 3) -> pd.DataFrame:
    """Load data catalog with retry logic"""
    for attempt in range(max_retries):
        try:
            return load_data_catalog(BASE_DIR)
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Data loading attempt {attempt + 1} failed: {e}. Retrying...")
            import time
            time.sleep(2 ** attempt)  # Exponential backoff

# Replace the global DF assignment
try:
    DATA_CATALOG = load_data_with_retry()
    DF = _prepare_dataframe(DATA_CATALOG.frame)
except Exception as e:
    print(f"FATAL: Could not load data catalog: {e}")
    # Create empty dataframe as fallback
    DF = pd.DataFrame()

from functools import lru_cache
from datetime import datetime, timedelta

# Simple time-based cache
_cache_store = {}
_cache_ttl = {}

def cached(func):
    """Simple cache decorator with TTL"""
    def wrapper(*args, **kwargs):
        key = f"{func.__name__}:{args}:{kwargs}"
        if key in _cache_store and datetime.now() < _cache_ttl.get(key, datetime.min):
            return _cache_store[key]
        
        result = func(*args, **kwargs)
        _cache_store[key] = result
        _cache_ttl[key] = datetime.now() + timedelta(minutes=5)
        return result
    return wrapper

# Apply to expensive functions
@cached
def _period_options() -> list[dict[str, Any]]:
    # existing code...
    pass

@cached  
def _brand_options() -> list[dict[str, Any]]:
    # existing code...
    pass



def _gemini_rotation_start(total_keys: int) -> int:
    if total_keys <= 0:
        return 0
    with _GEMINI_KEY_LOCK:
        return _GEMINI_KEY_INDEX % total_keys


def _gemini_rotation_set(next_index: int, total_keys: int) -> None:
    if total_keys <= 0:
        return
    global _GEMINI_KEY_INDEX
    with _GEMINI_KEY_LOCK:
        _GEMINI_KEY_INDEX = next_index % total_keys


def _gemini_answer_prompt(prompt: str) -> str:
    instructions = [
        "Answer the user's question using the workbook data.",
        "Ignore the dashboard header filters and do not widen the answer to all brands unless the question explicitly asks for the full market.",
        "If the question names a specific brand, focus only on that brand.",
        "Do not mention the UI filters unless the user asks about them.",
        f"Question: {prompt}",
    ]
    return "\n".join(instructions)


def _smart_dataframe(api_key: str):
    if not (PANDASAI_AVAILABLE and api_key):
        return None

    try:
        from pandasai_litellm.litellm import LiteLLM
    except Exception:
        return None

    llm = LiteLLM(model=GEMINI_MODEL, api_key=api_key, max_retries=0)
    analytics_df = DF[ANALYTICS_COLUMNS].copy()
    return SmartDataframe(analytics_df, config={"llm": llm})


def _ask_with_gemini(prompt: str) -> tuple[str, dict[str, Any]]:
    keys = _configured_gemini_keys()
    status = {
        "pandasai_available": PANDASAI_AVAILABLE,
        "gemini_configured": bool(keys),
        "gemini_key_count": len(keys),
        "gemini_attempts": 0,
        "ask_mode": True,
    }
    if not keys or not PANDASAI_AVAILABLE:
        return (
            "Gemini is not configured for this environment, so the Ask Gemini tab cannot answer right now.",
            status,
        )

    start_index = _gemini_rotation_start(len(keys))
    errors: list[str] = []
    query = _gemini_answer_prompt(prompt)

    for offset in range(len(keys)):
        slot = (start_index + offset) % len(keys)
        sdf = _smart_dataframe(keys[slot])
        if sdf is None:
            errors.append(f"Key {slot + 1}: PandasAI or LiteLLM is unavailable.")
            continue

        try:
            answer = str(sdf.chat(query)).strip()
            if not answer:
                raise ValueError("Gemini returned an empty response.")
        except Exception as exc:
            errors.append(f"Key {slot + 1}: {exc}")
            continue

        status.update({
            "gemini_attempts": offset + 1,
            "gemini_key_slot": slot + 1,
        })
        _gemini_rotation_set(slot + 1, len(keys))
        return answer, status

    _gemini_rotation_set(0, len(keys))
    last_error = errors[-1] if errors else "Unknown error."
    return (
        f"Gemini could not complete this prompt after trying all configured keys. Last error: {last_error}",
        status,
    )


def _period_options() -> list[dict[str, Any]]:
    periods = (
        DF[["PeriodKey", "PeriodLabel", "PeriodShort", "MonthName", "Year", "PeriodSort"]]
        .drop_duplicates()
        .sort_values("PeriodSort")
    )
    return [
        {
            "key": row.PeriodKey,
            "label": row.PeriodLabel,
            "short": row.PeriodShort,
            "month": row.MonthName,
            "year": row.Year,
        }
        for row in periods.itertuples()
    ]


def _year_options() -> list[Any]:
    years = sorted(value for value in DF["Year"].dropna().unique().tolist() if value != "Unknown")
    return years or ["Unknown"]


def _default_year() -> Any:
    years = _year_options()
    current_year = date.today().year
    if current_year in years:
        return current_year
    return years[-1] if years else current_year


def _brand_options() -> list[dict[str, Any]]:
    branded = DF[DF["BrandKey"] != "UNKNOWN"].copy()
    grouped = (
        branded.groupby("BrandKey", dropna=False)
        .agg({"Brand": "first", "SalesValue": "sum"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
    )
    return [
        {"name": ALL_BRAND_LABEL, "value": ""},
        *[{"name": row.Brand, "value": row.Brand} for row in grouped.itertuples()],
    ]


def _default_period(year: Any | None = None) -> str:
    periods = _period_options()
    selected_year = year if year is not None else _default_year()
    if selected_year is not None:
        filtered = [period for period in periods if str(period["year"]) == str(selected_year)]
        if filtered:
            return filtered[-1]["key"]
    return periods[-1]["key"] if periods else ""


def _normalize_brand(brand: str | None) -> str:
    if not _is_all_brand(brand):
        match = DF[DF["BrandKey"] == str(brand).upper()]
        if not match.empty:
            return str(match.iloc[0]["Brand"])
    return ""


def _normalize_period(period: str | None, year: Any | None = None) -> str:
    available = {item["key"] for item in _period_options()}
    selected_year = year if year is not None else _default_year()
    if period in available:
        if year:
            selected = next((item for item in _period_options() if item["key"] == period), None)
            if selected and str(selected["year"]) != str(year):
                return _default_period(year)
        return str(period)
    return _default_period(selected_year)


def _previous_period(period: str) -> str | None:
    periods = [item["key"] for item in _period_options()]
    if period not in periods:
        return None
    index = periods.index(period)
    if index == 0:
        return None
    return periods[index - 1]


def _period_meta(period: str) -> dict[str, Any]:
    return next((item for item in _period_options() if item["key"] == period), _parse_period(period))


def _brand_period_df(brand: str, period: str) -> pd.DataFrame:
    if _is_all_brand(brand):
        return DF[DF["PeriodKey"] == period].copy()
    return DF[(DF["BrandKey"] == brand.upper()) & (DF["PeriodKey"] == period)].copy()


def _period_df(period: str) -> pd.DataFrame:
    return DF[DF["PeriodKey"] == period].copy()


def _slice(
    period: str,
    brand: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> pd.DataFrame:
    data = DF[DF["PeriodKey"] == period].copy()
    if not _is_all_brand(brand):
        data = data[data["BrandKey"] == brand.upper()]
    if channel:
        data = data[data["Channel"] == channel]
    if customer:
        data = data[data["Customer"] == customer]
    if region:
        data = data[data["Region"] == region]
    return data


def _market_slice(period: str, channel: str | None = None, customer: str | None = None, region: str | None = None) -> pd.DataFrame:
    return _slice(period=period, channel=channel, customer=customer, region=region)


def _weighted_average(data: pd.DataFrame, column: str) -> float:
    if data.empty or column not in data.columns:
        return 0.0
    weights = data["SalesValue"].clip(lower=0)
    if weights.sum() == 0:
        return _round(data[column].mean())
    return _round((data[column] * weights).sum() / weights.sum())


def _price_gap(period: str, brand: str, channel: str | None, customer: str | None, region: str | None) -> float:
    brand_data = _slice(period, brand=brand, channel=channel, customer=customer, region=region)
    market = _market_slice(period, channel=channel, customer=customer, region=region)
    competitors = market[market["BrandKey"] != brand.upper()]
    brand_price = _weighted_average(brand_data, "Price")
    competitor_price = _weighted_average(competitors, "Price")
    if competitor_price == 0:
        return 0.0
    return round((brand_price - competitor_price) / competitor_price * 100, 2)


def _portfolio_overview(period: str, brand: str) -> dict[str, Any]:
    period_data = _period_df(period)
    portfolio = period_data[period_data["IsPortfolio"]]
    if portfolio.empty:
        portfolio = period_data[period_data["BrandKey"] != "UNKNOWN"]
    market_value = period_data["SalesValue"].sum()
    market_volume = period_data["SalesVolume"].sum()
    brand_data = _brand_period_df(brand, period)
    previous = _previous_period(period)
    previous_brand = _brand_period_df(brand, previous) if previous else pd.DataFrame()

    brand_rank_frame = (
        period_data[period_data["BrandKey"] != "UNKNOWN"]
        .groupby("Brand", dropna=False)
        .agg({"SalesValue": "sum", "SalesVolume": "sum"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
    )
    brand_rank_frame["rank"] = range(1, len(brand_rank_frame) + 1)
    selected = brand_rank_frame[brand_rank_frame["Brand"].str.upper() == brand.upper()] if not _is_all_brand(brand) else pd.DataFrame()
    selected_rank = int(selected.iloc[0]["rank"]) if not selected.empty else None

    card_frame = (
        portfolio.groupby("Brand", dropna=False)
        .agg({"SalesValue": "sum", "SalesVolume": "sum"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
        .head(8)
    )
    card_frame["rank"] = range(1, len(card_frame) + 1)

    return {
        "market_size_value": _round(market_value),
        "market_size_volume": _round(market_volume),
        "portfolio_value_share_pct": 100.0 if _is_all_brand(brand) else _share(portfolio["SalesValue"].sum(), market_value),
        "portfolio_volume_share_pct": 100.0 if _is_all_brand(brand) else _share(portfolio["SalesVolume"].sum(), market_volume),
        "brand_value_share_pct": 100.0 if _is_all_brand(brand) else _share(brand_data["SalesValue"].sum(), market_value),
        "brand_volume_share_pct": 100.0 if _is_all_brand(brand) else _share(brand_data["SalesVolume"].sum(), market_volume),
        "brand_growth_pct": _growth(brand_data["SalesValue"].sum(), previous_brand["SalesValue"].sum() if not previous_brand.empty else 0),
        "selected_brand_rank": selected_rank,
        "brand_cards": [
            {
                "brand": row.Brand,
                "value": _round(row.SalesValue),
                "volume": _round(row.SalesVolume),
                "value_share_pct": _share(row.SalesValue, market_value),
                "volume_share_pct": _share(row.SalesVolume, market_volume),
                "rank": int(row.rank),
            }
            for row in card_frame.itertuples()
        ],
    }


def _period_trend(brand: str, year: Any | None = None) -> list[dict[str, Any]]:
    periods = [item for item in _period_options() if not year or str(item["year"]) == str(year)]
    rows = []
    for item in periods:
        period = item["key"]
        period_data = _period_df(period)
        brand_data = _brand_period_df(brand, period)
        previous = _previous_period(period)
        previous_brand = _brand_period_df(brand, previous) if previous else pd.DataFrame()
        is_all = _is_all_brand(brand)
        market_value = period_data["SalesValue"].sum()
        market_volume = period_data["SalesVolume"].sum()
        rows.append(
            {
                **item,
                "market_value": _round(market_value),
                "market_volume": _round(market_volume),
                "brand_value": _round(brand_data["SalesValue"].sum()),
                "brand_volume": _round(brand_data["SalesVolume"].sum()),
                "value_share": 100.0 if is_all else _share(brand_data["SalesValue"].sum(), period_data["SalesValue"].sum()),
                "volume_share": 100.0 if is_all else _share(brand_data["SalesVolume"].sum(), period_data["SalesVolume"].sum()),
                "growth": _growth(
                    brand_data["SalesValue"].sum(),
                    previous_brand["SalesValue"].sum() if not previous_brand.empty else 0,
                ),
            }
        )
    return rows


def _channel_rows(brand: str, period: str) -> list[dict[str, Any]]:
    previous = _previous_period(period)
    rows = []
    total_brand_value = _slice(period, brand=brand)["SalesValue"].sum()

    for definition in CHANNEL_DEFINITIONS:
        channel = definition["key"]
        brand_data = _slice(period, brand=brand, channel=channel)
        market_data = _market_slice(period, channel=channel)
        previous_brand = _slice(previous, brand=brand, channel=channel) if previous else pd.DataFrame()
        rows.append(
            {
                **definition,
                "name": channel,
                "value_share": _share(brand_data["SalesValue"].sum(), market_data["SalesValue"].sum()),
                "volume_share": _share(brand_data["SalesVolume"].sum(), market_data["SalesVolume"].sum()),
                "growth": _growth(
                    brand_data["SalesValue"].sum(),
                    previous_brand["SalesValue"].sum() if not previous_brand.empty else 0,
                ),
                "revenue": _round(brand_data["SalesValue"].sum()),
                "volume": _round(brand_data["SalesVolume"].sum()),
                "share_of_brand": _share(brand_data["SalesValue"].sum(), total_brand_value),
            }
        )
    return rows


def _customer_rows(brand: str, period: str, channel: str) -> list[dict[str, Any]]:
    previous = _previous_period(period)
    brand_data = _slice(period, brand=brand, channel=channel)
    if brand_data.empty:
        return []

    customers = (
        brand_data.groupby("Customer", dropna=False)
        .agg({"SalesValue": "sum", "SalesVolume": "sum"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
    )

    rows = []
    for row in customers.itertuples():
        customer = row.Customer
        market = _market_slice(period, channel=channel, customer=customer)
        previous_brand = _slice(previous, brand=brand, channel=channel, customer=customer) if previous else pd.DataFrame()
        rows.append(
            {
                "name": customer,
                "value_share": _share(row.SalesValue, market["SalesValue"].sum()),
                "volume_share": _share(row.SalesVolume, market["SalesVolume"].sum()),
                "growth": _growth(row.SalesValue, previous_brand["SalesValue"].sum() if not previous_brand.empty else 0),
                "revenue": _round(row.SalesValue),
                "volume": _round(row.SalesVolume),
            }
        )
    return rows


def _customer_for_region(brand: str, period: str, channel: str, region: str) -> str:
    region_data = _slice(period, brand=brand, channel=channel, region=region)
    if region_data.empty:
        return ""

    customers = (
        region_data.groupby("Customer", dropna=False)
        .agg({"SalesValue": "sum"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
    )
    return str(customers.iloc[0]["Customer"]) if not customers.empty else ""


def _region_rows(brand: str, period: str, channel: str, customer: str) -> list[dict[str, Any]]:
    previous = _previous_period(period)
    brand_data = _slice(period, brand=brand, channel=channel, customer=customer)
    if brand_data.empty:
        return []

    regions = (
        brand_data.groupby("Region", dropna=False)
        .agg({"SalesValue": "sum", "SalesVolume": "sum", "Distribution": "mean"})
        .reset_index()
        .sort_values("SalesValue", ascending=False)
    )

    rows = []
    for row in regions.itertuples():
        region = row.Region
        market = _market_slice(period, channel=channel, customer=customer, region=region)
        previous_brand = _slice(previous, brand=brand, channel=channel, customer=customer, region=region) if previous else pd.DataFrame()
        rows.append(
            {
                "name": region,
                "market_share": _share(row.SalesValue, market["SalesValue"].sum()),
                "volume_share": _share(row.SalesVolume, market["SalesVolume"].sum()),
                "growth": _growth(row.SalesValue, previous_brand["SalesValue"].sum() if not previous_brand.empty else 0),
                "revenue": _round(row.SalesValue),
                "volume": _round(row.SalesVolume),
                "distribution": _round(row.Distribution),
            }
        )
    return rows


def _selected_or_first(value: str | None, rows: list[dict[str, Any]], key: str = "name") -> str:
    names = [row[key] for row in rows]
    if value in names:
        return str(value)
    return names[0] if names else ""


def _root_cause(brand: str, period: str, channel: str, customer: str, region: str) -> dict[str, Any]:
    previous = _previous_period(period)
    current_brand = _slice(period, brand=brand, channel=channel, customer=customer, region=region)
    current_market = _market_slice(period, channel=channel, customer=customer, region=region)
    previous_brand = _slice(previous, brand=brand, channel=channel, customer=customer, region=region) if previous else pd.DataFrame()
    previous_market = _market_slice(previous, channel=channel, customer=customer, region=region) if previous else pd.DataFrame()

    current_value = current_brand["SalesValue"].sum()
    previous_value = previous_brand["SalesValue"].sum() if not previous_brand.empty else 0
    current_volume = current_brand["SalesVolume"].sum()
    previous_volume = previous_brand["SalesVolume"].sum() if not previous_brand.empty else 0
    current_share = _share(current_value, current_market["SalesValue"].sum())
    previous_share = _share(previous_value, previous_market["SalesValue"].sum() if not previous_market.empty else 0)
    current_distribution = _weighted_average(current_brand, "Distribution")
    previous_distribution = _weighted_average(previous_brand, "Distribution") if not previous_brand.empty else 0
    current_price = _weighted_average(current_brand, "Price")
    previous_price = _weighted_average(previous_brand, "Price") if not previous_brand.empty else 0
    current_price_gap = _price_gap(period, brand, channel, customer, region)
    previous_price_gap = _price_gap(previous, brand, channel, customer, region) if previous else 0

    share_delta = _delta(current_share, previous_share)
    distribution_delta = _delta(current_distribution, previous_distribution)
    price_delta = _delta(current_price, previous_price)
    price_gap_delta = _delta(current_price_gap, previous_price_gap)
    volume_growth = _growth(current_volume, previous_volume)

    reasons = []
    if share_delta < -0.5:
        reasons.append(
            {
                "label": "Share declined",
                "detail": f"Value share moved from {previous_share:.2f}% to {current_share:.2f}%.",
                "impact": "High",
            }
        )
    if distribution_delta < -3:
        reasons.append(
            {
                "label": "Distribution loss",
                "detail": f"Distribution moved from {previous_distribution:.2f}% to {current_distribution:.2f}%.",
                "impact": "High",
            }
        )
    if price_delta > 1:
        reasons.append(
            {
                "label": "Price increase",
                "detail": f"Average price increased by {price_delta:.2f} versus the prior period.",
                "impact": "Medium",
            }
        )
    if price_gap_delta > 2:
        reasons.append(
            {
                "label": "Competitive price pressure",
                "detail": f"Brand price gap versus competitors widened by {price_gap_delta:.2f} points.",
                "impact": "Medium",
            }
        )
    if volume_growth < -5:
        reasons.append(
            {
                "label": "Volume softness",
                "detail": f"Sales unit cases changed by {volume_growth:.2f}% versus the prior period.",
                "impact": "Medium",
            }
        )
    if not reasons:
        reasons.append(
            {
                "label": "No severe dragger detected",
                "detail": "The selected cut is broadly stable versus the previous available period.",
                "impact": "Low",
            }
        )

    channel_customers = _customer_rows(brand, period, channel)
    positive_customers = [row for row in channel_customers if row["growth"] > 0]
    drivers = [
        {
            "label": row["name"],
            "detail": f"Growth of {row['growth']:.2f}% with value share at {row['value_share']:.2f}%.",
        }
        for row in positive_customers[:2]
    ]
    if not drivers:
        drivers = [
            {
                "label": "Base demand",
                "detail": "Revenue is still present in the selected cut, so recovery can focus on execution levers.",
            }
        ]

    actions = [
        {"label": "Recover availability", "detail": "Prioritize distribution and shelf checks in the selected customer-region pocket."},
        {"label": "Review price gap", "detail": "Compare pack pricing against competitors where the price gap widened."},
        {"label": "Focus field execution", "detail": "Use the strongest growing customers as execution benchmarks."},
    ]

    period_label = _period_meta(period)["label"]
    previous_label = _period_meta(previous)["label"] if previous else "previous period"
    brand_label = _brand_subject(brand).title() if _is_all_brand(brand) else str(brand)
    summary = (
        f"{brand_label} has {current_share:.2f}% value share in {region} for {customer} during {period_label}. "
        f"That is {share_delta:+.2f} points versus {previous_label}."
    )

    return {
        "brand": brand,
        "brand_label": _brand_label(brand),
        "brand_subject": _brand_subject(brand),
        "period": period,
        "channel": channel,
        "customer": customer,
        "region": region,
        "summary": summary,
        "metrics": [
            {"label": "Value share", "current": f"{current_share:.2f}%", "previous": f"{previous_share:.2f}%", "delta": f"{share_delta:+.2f}pp"},
            {"label": "Distribution", "current": f"{current_distribution:.2f}%", "previous": f"{previous_distribution:.2f}%", "delta": f"{distribution_delta:+.2f}pp"},
            {"label": "Avg price", "current": f"{current_price:.2f}", "previous": f"{previous_price:.2f}", "delta": f"{price_delta:+.2f}"},
            {"label": "Price gap", "current": f"{current_price_gap:.2f}%", "previous": f"{previous_price_gap:.2f}%", "delta": f"{price_gap_delta:+.2f}pp"},
        ],
        "reasons": reasons,
        "drivers": drivers,
        "actions": actions,
    }


def build_dashboard_payload(
    brand: str | None = None,
    period: str | None = None,
    year: Any | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    selected_brand = _normalize_brand(brand)
    selected_period = _normalize_period(period, year)
    selected_year = _period_meta(selected_period)["year"]
    selected_channel = _normalize_channel(channel)
    selected_channel_definition = _channel_definition(selected_channel)
    selected_brand_label = _brand_label(selected_brand)
    selected_brand_subject = _brand_subject(selected_brand)
    gemini_keys = _configured_gemini_keys()

    customers = _customer_rows(selected_brand, selected_period, selected_channel)
    selected_customer = _selected_or_first(customer, customers)
    if not customer and region:
        inferred_customer = _customer_for_region(selected_brand, selected_period, selected_channel, region)
        if inferred_customer:
            selected_customer = inferred_customer
            customers = _customer_rows(selected_brand, selected_period, selected_channel)
    regions = _region_rows(selected_brand, selected_period, selected_channel, selected_customer) if selected_customer else []
    selected_region = _selected_or_first(region, regions)

    return {
        "country": DATA_CATALOG.country,
        "filters": {
            "brands": _brand_options(),
            "years": _year_options(),
            "periods": _period_options(),
            "channels": CHANNEL_DEFINITIONS,
        },
        "selections": {
            "brand": selected_brand,
            "brand_label": selected_brand_label,
            "brand_subject": selected_brand_subject,
            "country": DATA_CATALOG.country,
            "period": selected_period,
            "period_label": _period_meta(selected_period)["label"],
            "month": _period_meta(selected_period)["month"],
            "year": selected_year,
            "channel": selected_channel,
            "channel_label": selected_channel_definition["label"],
            "channel_title": selected_channel_definition["title"],
            "channel_description": selected_channel_definition["description"],
            "customer": selected_customer,
            "region": selected_region,
        },
        "portfolio": _portfolio_overview(selected_period, selected_brand),
        "periods": _period_trend(selected_brand, selected_year),
        "channels": _channel_rows(selected_brand, selected_period),
        "customers": customers,
        "regions": regions,
        "root_cause": _root_cause(selected_brand, selected_period, selected_channel, selected_customer, selected_region)
        if selected_customer and selected_region
        else {},
        "ai": {
            "pandasai_available": PANDASAI_AVAILABLE,
            "gemini_configured": bool(gemini_keys),
            "gemini_key_count": len(gemini_keys),
        },
    }


def build_bootstrap_payload() -> dict[str, Any]:
    return build_dashboard_payload()


def generate_brand_summary(brand: str | None = None, period: str | None = None) -> dict[str, Any]:
    payload = build_dashboard_payload(brand=brand, period=period)
    portfolio = payload["portfolio"]
    selections = payload["selections"]
    brand_subject = selections["brand_subject"]
    if selections["brand"]:
        summary = (
            f"{selections['brand_label']} is ranked #{portfolio['selected_brand_rank']} in "
            f"{selections['period_label']} with {portfolio['brand_value_share_pct']:.2f}% value share."
        )
    else:
        summary = (
            f"{brand_subject.title()} in {selections['period_label']} represents the full market "
            f"with {portfolio['market_size_value']:.2f} value."
        )
    return {
        "summary": summary,
        **portfolio,
    }


def generate_channel_summary(brand: str | None = None, month: str | None = None, period: str | None = None) -> dict[str, Any]:
    payload = build_dashboard_payload(brand=brand, period=period or month)
    return {
        "summary": f"Channel view for {payload['selections']['brand_label']} / {payload['selections']['channel_label']}.",
        "channel_rows": payload["channels"],
    }


def generate_customer_summary(brand: str | None = None, month: str | None = None, channel: str = "TEG") -> dict[str, Any]:
    payload = build_dashboard_payload(brand=brand, period=month, channel=channel)
    return {
        "summary": f"Customer view for {payload['selections']['brand_label']} / {payload['selections']['channel_label']}.",
        "customer_rows": payload["customers"],
    }


def generate_region_summary(
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
    customer: str | None = None,
) -> dict[str, Any]:
    payload = build_dashboard_payload(brand=brand, period=month, channel=channel, customer=customer)
    customer_label = payload["selections"]["customer"] or "selected customer"
    return {
        "summary": f"Region view for {customer_label} in {payload['selections']['channel_label']}.",
        "region_rows": payload["regions"],
    }


def generate_root_cause_analysis(
    brand: str | None = None,
    month: str | None = None,
    channel: str = "TEG",
    customer: str | None = None,
    region: str | None = None,
) -> dict[str, Any]:
    payload = build_dashboard_payload(brand=brand, period=month, channel=channel, customer=customer, region=region)
    return payload["root_cause"]


def generate_executive_summary(
    prompt: str,
    brand: str | None = None,
    month: str | None = None,
    year: str | None = None,
    channel: str | None = None,
    customer: str | None = None,
    region: str | None = None,
    country: str | None = None,
    ask_mode: bool = False,
) -> dict[str, Any]:
    if ask_mode:
        ai_answer, ai_status = _ask_with_gemini(prompt)
        return {
            "summary": ai_answer,
            "draggers": [],
            "drivers": [],
            "actions": [],
            "root_cause": "",
            "pandasai_answer": ai_answer,
            "ask_mode": True,
            "ai_status": ai_status,
        }

    payload = build_dashboard_payload(brand=brand, period=month, year=year, channel=channel, customer=customer, region=region)
    selections = payload["selections"]
    root = payload["root_cause"]
    strongest_dragger = min(payload["channels"], key=lambda row: row["growth"]) if payload["channels"] else None
    strongest_driver = max(payload["channels"], key=lambda row: row["growth"]) if payload["channels"] else None
    brand_subject = selections["brand_subject"].title() if selections["brand"] == "" else selections["brand_label"]
    channel_label = selections.get("channel_label", selections["channel"])
    country_label = country or payload.get("country") or ""
    country_suffix = f" for {country_label}" if country_label and country_label != "Unknown market" else ""

    summary = (
        f"{brand_subject} is at {payload['portfolio']['brand_value_share_pct']:.2f}% value share and "
        f"{payload['portfolio']['brand_volume_share_pct']:.2f}% volume share in {selections['period_label']}{country_suffix}. "
        f"The selected channel is {channel_label} with {next((row['value_share'] for row in payload['channels'] if row['key'] == selections['channel']), 0):.2f}% value share."
    )
    draggers = []
    drivers = []
    if strongest_dragger:
        draggers.append(f"{strongest_dragger['label']} is the weakest channel at {strongest_dragger['growth']:.2f}% growth.")
    if root:
        draggers.extend([item["label"] for item in root.get("reasons", [])[:3]])
    if strongest_driver:
        drivers.append(f"{strongest_driver['label']} is the strongest channel at {strongest_driver['growth']:.2f}% growth.")
    drivers.extend([item["label"] for item in root.get("drivers", [])[:2]])

    ai_answer = None
    gemini_keys = _configured_gemini_keys()
    ai_status = {
        "pandasai_available": PANDASAI_AVAILABLE,
        "gemini_configured": bool(gemini_keys),
        "gemini_key_count": len(gemini_keys),
        "ask_mode": False,
    }
    if prompt:
        contextual_prompt = (
            f"{prompt}\nUse these filters if relevant: brand={selections['brand']}, "
            f"country={country_label or payload.get('country', '')}, period={selections['period_label']}, channel={selections['channel']}, "
            f"customer={selections['customer']}, region={selections['region']}."
        )
        ai_answer, ai_status = _ask_with_gemini(contextual_prompt)

    return {
        "summary": summary,
        "draggers": draggers,
        "drivers": drivers,
        "actions": root.get("actions", []) if root else [],
        "root_cause": root.get("summary") if root else "",
        "pandasai_answer": ai_answer,
        "ask_mode": False,
        "ai_status": ai_status,
    }
