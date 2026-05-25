from unittest.mock import MagicMock, patch

from dashboard.ui import _build_ta_config, _ema_signal_text, render_custom_dashboard


def test_build_ta_config_uses_strategy_fields():
    strategy_config = {
        "fast_ema_period": 10,
        "slow_ema_period": 30,
        "base_token": "WETH",
        "quote_token": "USDC",
        "chain": "optimism",
        "protocol": "uniswap_v3",
    }

    config = _build_ta_config(strategy_config)

    assert config.indicator_name == "EMA Crossover"
    assert config.indicator_period == 10
    assert config.secondary_periods == [30]
    assert config.signal_type == "momentum"
    assert config.base_token == "WETH"
    assert config.quote_token == "USDC"
    assert config.chain == "optimism"
    assert config.protocol == "uniswap_v3"


def test_ema_signal_text_uses_state_defaults():
    message = _ema_signal_text({})
    assert "Waiting for EMA crossover" in message
    assert "Position: QUOTE" in message


def test_render_custom_dashboard_renders_template_with_enriched_state():
    strategy_config = {
        "fast_ema_period": 8,
        "slow_ema_period": 21,
        "signal_timeframe": "5m",
        "min_trade_value_usd": "8",
    }
    api_client = MagicMock()
    session_state = {"last_signal_side": "buy"}
    enriched_state = {"price_history": [{"time": "t", "price": 1}]}

    with (
        patch("dashboard.ui._build_ta_config") as mock_build,
        patch("dashboard.ui.prepare_ta_session_state", return_value=enriched_state) as mock_prepare,
        patch("dashboard.ui.render_ta_dashboard") as mock_render,
        patch("dashboard.ui.st.title") as mock_title,
        patch("dashboard.ui.st.caption") as mock_caption,
    ):
        config = MagicMock()
        mock_build.return_value = config

        render_custom_dashboard("strategy-1", strategy_config, api_client, session_state)

    mock_build.assert_called_once_with(strategy_config)
    mock_title.assert_called_once_with("OPTASwapMAStrategy")
    mock_caption.assert_called_once_with("EMA crossover on 5m candles. Minimum trade value: $8.")
    mock_prepare.assert_called_once_with(api_client, session_state=session_state, config=config)
    mock_render.assert_called_once_with("strategy-1", strategy_config, enriched_state, config)
