from __future__ import annotations

import os
from pathlib import Path

try:
    import pandasai as pai
    from pandasai import SmartDataframe
    from pandasai_litellm.litellm import LiteLLM

    PANDASAI_AVAILABLE = True
except Exception:
    pai = None
    SmartDataframe = None
    
    LiteLLM = None
    PANDASAI_AVAILABLE = False

from services.data_sources import load_data_catalog


BASE_DIR = Path(__file__).resolve().parent


def main() -> None:
    if not PANDASAI_AVAILABLE:
        raise RuntimeError("pandasai is not installed in this environment.")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY before running this script.")

    catalog = load_data_catalog(BASE_DIR)
    df = catalog.frame.copy()

    llm = LiteLLM(model="gemini/gemini-2.5-flash", api_key=api_key)
    pai.config.set({"llm": llm})

    analytics_df = df[
        [
            column
            for column in [
                "PeriodLabel",
                "MonthName",
                "Year",
                "Brand",
                "Channel",
                "Customer",
                "Region",
                "SalesValue",
                "SalesVolume",
                "Distribution",
                "Price",
            ]
            if column in df.columns
        ]
    ].copy()

    sdf = SmartDataframe(analytics_df if not analytics_df.empty else df, config={"llm": llm})
    response = sdf.chat("What is the average revenue by region?")
    print(response)


if __name__ == "__main__":
    main()
