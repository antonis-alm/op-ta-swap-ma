"""OP-TA-Swap-MA dashboard."""

from typing import Any

import streamlit as st

from almanak.framework.dashboard.templates import (
    get_macd_config,
    prepare_ta_session_state,
    render_ta_dashboard,
)


def render_custom_dashboard(
    strategy_id: str,
    strategy_config: dict[str, Any],
    api_client: Any,
    session_state: dict[str, Any],
) -> None:
    config = get_macd_config(
        fast=int(strategy_config.get("fast_ema_period", 8)),
        slow=int(strategy_config.get("slow_ema_period", 21)),
        signal=int(strategy_config.get("signal_period", 9)),
    )
    config.base_token = str(strategy_config.get("base_token", config.base_token))
    config.quote_token = str(strategy_config.get("quote_token", config.quote_token))
    config.chain = str(strategy_config.get("chain", config.chain))
    config.protocol = str(strategy_config.get("protocol", config.protocol))

    st.title("OP-TA-Swap-MA")

    enriched_session_state = prepare_ta_session_state(
        api_client,
        session_state=session_state,
        config=config,
    )

    render_ta_dashboard(strategy_id, strategy_config, enriched_session_state, config)
