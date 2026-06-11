from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

import pandas as pd

DEFAULT_CONFIG_NAME = "tccc_source.json"

def _normalize_text(value: Any) -> str:
    """Normalize text by removing special characters and converting to lowercase"""
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).strip().lower())


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    text = str(value).strip()
    return text or None


def _mapping_or_empty(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def _sequence_or_empty(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _resolve_path(value: str | None, base_dir: Path) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme and parsed.scheme not in {"file"}:
        return value

    path = Path(parsed.path if parsed.scheme == "file" else value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def _load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Datasource config must be a JSON object: {path}")
    return payload


def _select_config_path(base_dir: Path) -> Path:
    candidates = [
        base_dir / "datas" / DEFAULT_CONFIG_NAME,
        base_dir / DEFAULT_CONFIG_NAME,
    ]
    for path in candidates:
        if path.exists():
            return path
    expected = candidates[0]
    raise FileNotFoundError(f"No datasource configuration found. Expected {expected}.")


def _first_non_empty(series: pd.Series) -> str | None:
    if series.empty:
        return None
    cleaned = series.dropna().astype(str).map(str.strip)
    cleaned = cleaned[cleaned != ""]
    if cleaned.empty:
        return None
    try:
        mode = cleaned.mode(dropna=True)
        if not mode.empty:
            return str(mode.iloc[0])
    except Exception:
        pass
    return str(cleaned.iloc[0])


def _normalize_value(value: Any) -> str:
    return str(value).strip().upper()


def _normalize_channel_value(value: Any) -> str:
    text = _string_or_none(value)
    if not text:
        return "TEG"

    normalized = _normalize_text(text)
    if normalized in {"pmf", "pfm"}:
        return "PFM"
    if normalized == "horeca":
        return "HORECA"
    if normalized == "lt":
        return "L&T"
    if normalized == "teg":
        return "TEG"
    return text.strip().upper()


@dataclass(frozen=True)
class SourceSpec:
    kind: str = "excel"
    uri: str | None = None
    sheet: str | int | None = None
    table: str | None = None
    query: str | None = None
    api_key: str | None = None
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    timeout: int = 30
    country: str | None = None
    column_aliases: dict[str, tuple[str, ...]] = field(default_factory=dict)
    customer_channel_map: dict[str, str] = field(default_factory=dict)
    portfolio_brands: tuple[str, ...] = field(default_factory=tuple)
    lookups: dict[str, "SourceSpec"] = field(default_factory=dict)
    name: str | None = None
    default: bool = False

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "SourceSpec":
        raw_lookups = _mapping_or_empty(mapping.get("lookups"))
        lookups = {
            str(key): cls.from_mapping(value)
            for key, value in raw_lookups.items()
            if isinstance(value, Mapping)
        }

        alias_map: dict[str, tuple[str, ...]] = {}
        for canonical, aliases in _mapping_or_empty(mapping.get("column_aliases")).items():
            canonical_name = _string_or_none(canonical)
            if not canonical_name:
                continue
            alias_values: list[str] = []
            for alias in _sequence_or_empty(aliases):
                alias_text = _string_or_none(alias)
                if alias_text and alias_text not in alias_values:
                    alias_values.append(alias_text)
            if canonical_name not in alias_values:
                alias_values.insert(0, canonical_name)
            alias_map[canonical_name] = tuple(alias_values)

        channel_map: dict[str, str] = {}
        for customer, channel in _mapping_or_empty(mapping.get("customer_channel_map")).items():
            customer_text = _string_or_none(customer)
            channel_text = _string_or_none(channel)
            if customer_text and channel_text:
                channel_map[_normalize_text(customer_text)] = _normalize_channel_value(channel_text)

        portfolio_brands: list[str] = []
        for item in _sequence_or_empty(mapping.get("portfolio_brands")):
            brand = _string_or_none(item)
            if brand:
                brand_key = _normalize_text(brand)
                if brand_key not in {_normalize_text(existing) for existing in portfolio_brands}:
                    portfolio_brands.append(brand)

        return cls(
            kind=str(mapping.get("kind") or "excel").strip().lower(),
            uri=_string_or_none(mapping.get("uri")),
            sheet=mapping.get("sheet"),
            table=_string_or_none(mapping.get("table")),
            query=_string_or_none(mapping.get("query")),
            api_key=_string_or_none(mapping.get("api_key")),
            method=str(mapping.get("method") or "GET").strip().upper(),
            headers={str(key): str(value) for key, value in _mapping_or_empty(mapping.get("headers")).items()},
            params=_mapping_or_empty(mapping.get("params")),
            timeout=int(mapping.get("timeout") or 30),
            country=_string_or_none(mapping.get("country")),
            column_aliases=alias_map,
            customer_channel_map=channel_map,
            portfolio_brands=tuple(portfolio_brands),
            lookups=lookups,
            name=_string_or_none(mapping.get("name")),
            default=bool(mapping.get("default", False)),
        )


@dataclass(frozen=True)
class DataCatalog:
    spec: SourceSpec
    frame: pd.DataFrame
    country: str
    customer_channel_map: dict[str, str]
    portfolio_brands: frozenset[str]

    def infer_channel(self, customer: Any) -> str:
        customer_text = _string_or_none(customer)
        if not customer_text:
            return "TEG"

        mapped = self.customer_channel_map.get(_normalize_text(customer_text))
        if mapped:
            return mapped

        lower = customer_text.lower()
        if "liquor" in lower or "tops" in lower:
            return "L&T"
        if any(word in lower for word in ("outdoor", "foodworld", "restaurant", "cafe", "hotel")):
            return "HORECA"
        if any(
            word in lower
            for word in (
                "clicks",
                "medirite",
                "express",
                "mini",
                "urban",
                "kwikspar",
                "sparexpress",
                "buying partner",
            )
        ):
            return "PFM"
        return "TEG"

    def is_portfolio_brand(self, brand: Any) -> bool:
        brand_text = _string_or_none(brand)
        if not brand_text:
            return False
        if not self.portfolio_brands:
            return False
        return _normalize_text(brand_text) in self.portfolio_brands


def _resolve_source_spec(base_dir: Path, env: Mapping[str, str] | None = None) -> tuple[SourceSpec, Path]:
    config_path = _select_config_path(base_dir)
    payload = _load_json_file(config_path)
    return SourceSpec.from_mapping(payload), config_path.parent


def _resolve_url(uri: str, params: Mapping[str, Any]) -> str:
    parsed = urlparse(uri)
    query_params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    for key, value in params.items():
        if value is not None and str(value).strip():
            query_params[str(key)] = str(value)
    return urlunparse(parsed._replace(query=urlencode(query_params)))


def _read_sql_frame(spec: SourceSpec, base_dir: Path) -> pd.DataFrame:
    if not spec.uri:
        raise ValueError("SQL datasource requires a URI.")
    query = spec.query or (f"SELECT * FROM {spec.table}" if spec.table else None)
    if not query:
        raise ValueError("SQL datasource requires a query or table name.")

    uri = _resolve_path(spec.uri, base_dir) or spec.uri
    try:
        from sqlalchemy import create_engine  # type: ignore
    except Exception:
        create_engine = None

    if create_engine is not None and "sqlite://" not in uri:
        engine = create_engine(uri)
        try:
            return pd.read_sql_query(query, engine)
        finally:
            engine.dispose()

    if uri.startswith("sqlite:///"):
        sqlite_path = uri.removeprefix("sqlite:///")
        connection = sqlite3.connect(sqlite_path)
    elif Path(uri).exists():
        connection = sqlite3.connect(uri)
    else:
        raise RuntimeError("SQL datasources require SQLAlchemy or a SQLite URI/path.")

    try:
        return pd.read_sql_query(query, connection)
    finally:
        connection.close()


def _read_api_frame(spec: SourceSpec, base_dir: Path) -> pd.DataFrame:
    if not spec.uri:
        raise ValueError("API datasource requires a URI.")

    uri = _resolve_url(_resolve_path(spec.uri, base_dir) or spec.uri, spec.params)
    headers = dict(spec.headers)
    if spec.api_key:
        has_auth_header = any(header.lower() in {"authorization", "x-api-key"} for header in headers)
        if not has_auth_header:
            headers["Authorization"] = f"Bearer {spec.api_key}"

    request = Request(uri, headers=headers, method=spec.method)
    with urlopen(request, timeout=spec.timeout) as response:  # nosec: B310
        payload = json.loads(response.read().decode("utf-8"))

    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return pd.DataFrame(value)
        return pd.json_normalize(payload)

    return pd.DataFrame(payload)


def _read_json_frame(spec: SourceSpec, base_dir: Path) -> pd.DataFrame:
    if not spec.uri:
        raise ValueError("JSON datasource requires a URI.")
    resolved = _resolve_path(spec.uri, base_dir)
    if resolved and Path(resolved).exists():
        with Path(resolved).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        payload = json.loads(spec.uri)
    if isinstance(payload, dict):
        for key in ("data", "rows", "results", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return pd.DataFrame(value)
        return pd.json_normalize(payload)
    return pd.DataFrame(payload)


def load_dataframe(spec: SourceSpec, base_dir: Path) -> pd.DataFrame:
    kind = spec.kind.lower()
    resolved_uri = _resolve_path(spec.uri, base_dir) if spec.uri else None

    if kind in {"excel", "xlsx", "xls"}:
        if not resolved_uri:
            raise ValueError("Excel datasource requires a URI.")
        return pd.read_excel(resolved_uri, sheet_name=spec.sheet or 0)

    if kind == "csv":
        if not resolved_uri:
            raise ValueError("CSV datasource requires a URI.")
        return pd.read_csv(resolved_uri)

    if kind == "parquet":
        if not resolved_uri:
            raise ValueError("Parquet datasource requires a URI.")
        return pd.read_parquet(resolved_uri)

    if kind == "json":
        return _read_json_frame(spec, base_dir)

    if kind in {"api", "http", "https"}:
        return _read_api_frame(spec, base_dir)

    if kind in {"sql", "database", "db"}:
        return _read_sql_frame(spec, base_dir)

    if resolved_uri and Path(resolved_uri).suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(resolved_uri, sheet_name=spec.sheet or 0)
    if resolved_uri and Path(resolved_uri).suffix.lower() == ".csv":
        return pd.read_csv(resolved_uri)
    if resolved_uri and Path(resolved_uri).suffix.lower() == ".parquet":
        return pd.read_parquet(resolved_uri)
    if resolved_uri and Path(resolved_uri).suffix.lower() == ".json":
        return _read_json_frame(spec, base_dir)

    raise ValueError(f"Unsupported datasource kind: {spec.kind}")


def _build_alias_lookup(column_aliases: Mapping[str, tuple[str, ...]]) -> dict[str, str]:
    alias_lookup: dict[str, str] = {}
    for canonical, aliases in column_aliases.items():
        canonical_name = _string_or_none(canonical)
        if not canonical_name:
            continue
        for candidate in aliases:
            candidate_text = _string_or_none(candidate)
            if candidate_text:
                alias_lookup[_normalize_text(candidate_text)] = canonical_name
    return alias_lookup


def _rename_frame_columns(frame: pd.DataFrame, spec: SourceSpec) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    alias_lookup = _build_alias_lookup(spec.column_aliases)
    rename_map: dict[str, str] = {}
    seen_targets: set[str] = set()
    for column in frame.columns:
        normalized = _normalize_text(column)
        target = alias_lookup.get(normalized)
        if target and target != column and target not in seen_targets:
            rename_map[column] = target
            seen_targets.add(target)

    if not rename_map:
        return frame.copy()
    return frame.rename(columns=rename_map).copy()


def _resolve_country(frame: pd.DataFrame, spec: SourceSpec) -> str:
    normalized_lookup = {_normalize_text(column): column for column in frame.columns}
    for candidate in ("country", "market"):
        column = normalized_lookup.get(candidate)
        if column:
            country = _first_non_empty(frame[column])
            if country:
                return country
    return spec.country or "Unknown market"


def _load_lookup_frame(base_dir: Path, lookup_spec: SourceSpec | None) -> pd.DataFrame:
    if lookup_spec is None:
        return pd.DataFrame()
    return load_dataframe(lookup_spec, base_dir)


def _extract_customer_channel_map(frame: pd.DataFrame) -> dict[str, str]:
    if frame.empty:
        return {}

    normalized_lookup = {_normalize_text(column): column for column in frame.columns}
    customer_column = (
        normalized_lookup.get("customer")
        or normalized_lookup.get("retailerbanner")
        or normalized_lookup.get("banner")
    )
    channel_column = normalized_lookup.get("channel")
    if not customer_column or not channel_column:
        return {}

    mapping: dict[str, str] = {}
    for customer, channel in frame[[customer_column, channel_column]].dropna().itertuples(index=False):
        customer_text = _string_or_none(customer)
        channel_text = _string_or_none(channel)
        if customer_text and channel_text:
            mapping[_normalize_text(customer_text)] = _normalize_channel_value(channel_text)
    return mapping


def _extract_portfolio_brands(frame: pd.DataFrame) -> frozenset[str]:
    if frame.empty:
        return frozenset()

    normalized_lookup = {_normalize_text(column): column for column in frame.columns}
    brand_column = normalized_lookup.get("brand")
    if not brand_column:
        return frozenset()

    values = {
        _normalize_text(value)
        for value in frame[brand_column].dropna().astype(str)
        if _string_or_none(value)
    }
    return frozenset(value for value in values if value)


def _truthy_portfolio_column(frame: pd.DataFrame) -> bool:
    normalized_lookup = {_normalize_text(column): column for column in frame.columns}
    flag_column = normalized_lookup.get("isportfolio") or normalized_lookup.get("portfolio")
    return bool(flag_column)


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _string_or_none(value)
    return bool(text) and text.lower() in {"1", "true", "yes", "y", "t"}


def load_data_catalog(base_dir: Path, env: Mapping[str, str] | None = None) -> DataCatalog:
    spec, source_base_dir = _resolve_source_spec(base_dir, env)

    raw_frame = load_dataframe(spec, source_base_dir)
    frame = _rename_frame_columns(raw_frame, spec)

    country = _resolve_country(frame, spec)

    channel_map: dict[str, str] = {}
    if spec.customer_channel_map:
        channel_map.update(spec.customer_channel_map)

    channel_lookup_spec = spec.lookups.get("customer_channel_map") or spec.lookups.get("channel_map")
    if channel_lookup_spec is not None:
        channel_lookup_frame = _load_lookup_frame(source_base_dir, channel_lookup_spec)
        channel_map.update(_extract_customer_channel_map(channel_lookup_frame))

    def _infer_channel_value(customer: Any) -> str:
        customer_text = _string_or_none(customer)
        if not customer_text:
            return "TEG"
        mapped = channel_map.get(_normalize_text(customer_text))
        if mapped:
            return mapped
        lower = customer_text.lower()
        if "liquor" in lower or "tops" in lower:
            return "L&T"
        if any(word in lower for word in ("outdoor", "foodworld", "restaurant", "cafe", "hotel")):
            return "HORECA"
        if any(
            word in lower
            for word in (
                "clicks",
                "medirite",
                "express",
                "mini",
                "urban",
                "kwikspar",
                "sparexpress",
                "buying partner",
            )
        ):
            return "PFM"
        return "TEG"

    if "Channel" in frame.columns:
        frame["Channel"] = frame["Channel"].map(_string_or_none)
    else:
        frame["Channel"] = pd.NA

    if "Customer" in frame.columns:
        inferred_channels = frame["Customer"].map(_infer_channel_value)
        existing_channels = frame["Channel"].map(_string_or_none)
        canonical_channels = {"TEG", "PFM", "L&T", "HORECA"}
        resolved_channels: list[str | None] = []
        for existing_value, inferred_value in zip(existing_channels, inferred_channels):
            existing_normalized = _normalize_channel_value(existing_value) if existing_value else ""
            if inferred_value and (
                not existing_value
                or existing_normalized not in canonical_channels
                or (existing_normalized == "TEG" and inferred_value != "TEG")
            ):
                resolved_channels.append(inferred_value)
            else:
                resolved_channels.append(existing_value)
        frame["Channel"] = resolved_channels

    frame["Channel"] = frame["Channel"].fillna("TEG").map(_normalize_channel_value)

    portfolio_brands = set(spec.portfolio_brands)
    portfolio_lookup_spec = spec.lookups.get("portfolio_brands") or spec.lookups.get("portfolio")
    if portfolio_lookup_spec is not None:
        portfolio_lookup_frame = _load_lookup_frame(source_base_dir, portfolio_lookup_spec)
        portfolio_brands.update(_extract_portfolio_brands(portfolio_lookup_frame))

    if "IsPortfolio" in frame.columns:
        frame["IsPortfolio"] = frame["IsPortfolio"].map(_coerce_bool)
    elif _truthy_portfolio_column(frame):
        normalized_lookup = {_normalize_text(column): column for column in frame.columns}
        flag_column = normalized_lookup.get("isportfolio") or normalized_lookup.get("portfolio")
        frame["IsPortfolio"] = frame[flag_column].map(_coerce_bool)
    elif portfolio_brands and "Brand" in frame.columns:
        normalized_portfolio = {_normalize_text(value) for value in portfolio_brands}
        frame["IsPortfolio"] = frame["Brand"].map(lambda value: _normalize_text(value or "") in normalized_portfolio)
    elif "Brand" in frame.columns:
        frame["IsPortfolio"] = True
    else:
        frame["IsPortfolio"] = False

    if "Country" not in frame.columns:
        frame["Country"] = country
    else:
        frame["Country"] = frame["Country"].fillna(country)

    return DataCatalog(
        spec=spec,
        frame=frame,
        country=country,
        customer_channel_map=channel_map,
        portfolio_brands=frozenset(_normalize_text(value) for value in portfolio_brands if _string_or_none(value)),
    )