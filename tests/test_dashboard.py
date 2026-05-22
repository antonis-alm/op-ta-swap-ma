from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dashboard.ui import render_custom_dashboard


def _template_config() -> SimpleNamespace:
    return SimpleNamespace(
        base_token="ETH",
        quote_token="USDC",
        chain="optimism",
        protocol="uniswap_v3",
    )


def test_render_custom_dashboard_builds_macd_config_and_renders_template():
    strategy_config = {
        "fast_ema_period": 10,
        "slow_ema_period": 30,
        "signal_period": 7,
        "base_token": "WETH",
        "quote_token": "USDC",
        "chain": "optimism",
        "protocol": "uniswap_v3",
    }
    api_client = MagicMock()
    session_state = {"existing": True}
    cfg = _template_config()
    enriched = {"price_history": [{"time": "t", "price": 1}]}

    with (
        patch("dashboard.ui.get_macd_config", return_value=cfg) as mock_get_macd,
        patch("dashboard.ui.prepare_ta_session_state", return_value=enriched) as mock_prepare,
        patch("dashboard.ui.render_ta_dashboard") as mock_render,
        patch("dashboard.ui.st.title") as mock_title,
    ):
        render_custom_dashboard("strat-1", strategy_config, api_client, session_state)

    mock_get_macd.assert_called_once_with(fast=10, slow=30, signal=7)
    mock_title.assert_called_once_with("OP-TA-Swap-MA")
    mock_prepare.assert_called_once_with(api_client, session_state=session_state, config=cfg)
    mock_render.assert_called_once_with("strat-1", strategy_config, enriched, cfg)
    assert cfg.base_token == "WETH"
    assert cfg.quote_token == "USDC"
    assert cfg.chain == "optimism"
    assert cfg.protocol == "uniswap_v3"


def test_render_custom_dashboard_uses_defaults_when_optional_fields_missing():
    cfg = _template_config()

    with (
        patch("dashboard.ui.get_macd_config", return_value=cfg) as mock_get_macd,
        patch("dashboard.ui.prepare_ta_session_state", return_value={}),
        patch("dashboard.ui.render_ta_dashboard"),
        patch("dashboard.ui.st.title"),
    ):
        render_custom_dashboard("strat-2", {}, MagicMock(), {})

    mock_get_macd.assert_called_once_with(fast=8, slow=21, signal=9)
