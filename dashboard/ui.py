"""Dashboard for OPTASwapMAStrategy."""

from typing import Any

import streamlit as st

from almanak.framework.dashboard.templates import (
    TADashboardConfig,
    prepare_ta_session_state,
    render_ta_dashboard,
)


def _ema_signal_text(session_state: dict[str, Any]) -> str:
    last_signal = str(session_state.get("last_signal_side", "")).strip().lower()
    position_side = str(session_state.get("position_side", "quote")).upper()
    buy_armed = bool(session_state.get("buy_armed", True))
    sell_armed = bool(session_state.get("sell_armed", True))

    if last_signal == "buy":
        return (
            "Bullish crossover executed (BUY). "
            f"Position: {position_side}. Re-arm status — buy: {buy_armed}, sell: {sell_armed}."
        )
    if last_signal == "sell":
        return (
            "Bearish crossover executed (SELL). "
            f"Position: {position_side}. Re-arm status — buy: {buy_armed}, sell: {sell_armed}."
        )

    return f"Waiting for EMA crossover. Position: {position_side}. Re-arm status — buy: {buy_armed}, sell: {sell_armed}."


def _build_ta_config(strategy_config: dict[str, Any]) -> TADashboardConfig:
    fast_period = int(strategy_config.get("fast_ema_period", 8))
    slow_period = int(strategy_config.get("slow_ema_period", 21))

    return TADashboardConfig(
        indicator_name="EMA Crossover",
        indicator_period=fast_period,
        secondary_periods=[slow_period],
        signal_type="momentum",
        custom_signal_fn=_ema_signal_text,
        chain=str(strategy_config.get("chain", "optimism")),
        protocol=str(strategy_config.get("protocol", "uniswap_v3")),
        base_token=str(strategy_config.get("base_token", "WETH")),
        quote_token=str(strategy_config.get("quote_token", "USDC")),
    )


def render_custom_dashboard(
    strategy_id: str,
    strategy_config: dict[str, Any],
    api_client: Any,
    session_state: dict[str, Any],
) -> None:
    st.title("OPTASwapMAStrategy")

    signal_timeframe = str(strategy_config.get("signal_timeframe", "5m"))
    min_trade_value_usd = str(strategy_config.get("min_trade_value_usd", "25"))
    st.caption(
        f"EMA crossover on {signal_timeframe} candles. "
        f"Minimum trade value: ${min_trade_value_usd}."
    )

    config = _build_ta_config(strategy_config)
    enriched_session_state = prepare_ta_session_state(
        api_client,
        session_state=session_state,
        config=config,
    )

    render_ta_dashboard(strategy_id, strategy_config, enriched_session_state, config)
