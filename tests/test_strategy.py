import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from almanak.framework.market import TokenBalance

from strategy import OPTASwapMAStrategy


def _base_config() -> dict:
    return {
        "chain": "optimism",
        "protocol": "uniswap_v3",
        "base_token": "WETH",
        "quote_token": "USDC",
        "signal_timeframe": "5m",
        "fast_ema_period": 2,
        "slow_ema_period": 3,
        "ohlcv_limit": 20,
        "min_trade_value_usd": "25",
        "max_slippage_bps": 50,
        "force_action": "",
    }


@pytest.fixture
def config() -> dict:
    return _base_config()


@pytest.fixture
def strategy(config: dict) -> OPTASwapMAStrategy:
    return OPTASwapMAStrategy(
        config=config,
        chain="optimism",
        wallet_address="0x" + "1" * 40,
    )


def _market(
    closes: list[float],
    *,
    quote_usd: str = "1000",
    base_usd: str = "1000",
    start: str = "2026-01-01 00:00:00",
) -> MagicMock:
    market = MagicMock()
    market.chain = "optimism"
    market.balance.side_effect = lambda token: TokenBalance(
        symbol=token,
        balance=Decimal("1"),
        balance_usd=Decimal(quote_usd if token == "USDC" else base_usd),
        address="",
    )
    timestamps = pd.date_range(start=start, periods=len(closes), freq="5min", tz="UTC")
    market.ohlcv.return_value = pd.DataFrame({"timestamp": timestamps, "close": closes})
    return market


def _intent_code(intent) -> str:
    return getattr(getattr(intent, "intent_type", None), "value", "")


def test_bull_crossover_swaps_usdc_to_weth(strategy: OPTASwapMAStrategy):
    market = _market([6, 6, 6, 6, 8, 6])
    intent = strategy.decide(market)
    assert _intent_code(intent) == "SWAP"
    assert intent.from_token == "USDC"
    assert intent.to_token == "WETH"


def test_bear_crossover_swaps_weth_to_usdc(strategy: OPTASwapMAStrategy):
    strategy.sell_armed = True
    market = _market([6, 6, 6, 8, 6, 6])
    intent = strategy.decide(market)
    assert _intent_code(intent) == "SWAP"
    assert intent.from_token == "WETH"
    assert intent.to_token == "USDC"


def test_no_crossover_holds(strategy: OPTASwapMAStrategy):
    market = _market([6, 6, 6, 6, 6, 6])
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "NO_CROSSOVER"


def test_buy_not_rearmed_holds(strategy: OPTASwapMAStrategy):
    strategy.buy_armed = False
    market = _market([6, 6, 6, 6, 8, 6])
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "NOT_REARMED"


def test_sell_not_rearmed_holds(strategy: OPTASwapMAStrategy):
    strategy.sell_armed = False
    market = _market([6, 6, 6, 8, 6, 6])
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "NOT_REARMED"


def test_buy_rearms_after_fast_below_slow_then_crosses(strategy: OPTASwapMAStrategy):
    strategy.buy_armed = False
    first_market = _market([6, 6, 6, 6, 6, 6], start="2026-01-01 00:00:00")
    hold_intent = strategy.decide(first_market)
    assert _intent_code(hold_intent) == "HOLD"
    assert strategy.buy_armed is True

    second_market = _market([6, 6, 6, 6, 8, 6], start="2026-01-01 00:30:00")
    swap_intent = strategy.decide(second_market)
    assert _intent_code(swap_intent) == "SWAP"
    assert swap_intent.from_token == "USDC"


def test_insufficient_usdc_on_bull_cross_holds(strategy: OPTASwapMAStrategy):
    market = _market([6, 6, 6, 6, 8, 6], quote_usd="10")
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "INSUFFICIENT_BALANCE"


def test_insufficient_weth_on_bear_cross_holds(strategy: OPTASwapMAStrategy):
    market = _market([6, 6, 6, 8, 6, 6], base_usd="10")
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "INSUFFICIENT_BALANCE"


def test_no_new_close_holds(strategy: OPTASwapMAStrategy):
    market = _market([6, 6, 6, 6, 6, 6])
    first = strategy.decide(market)
    second = strategy.decide(market)
    assert _intent_code(first) == "HOLD"
    assert _intent_code(second) == "HOLD"
    assert second.reason_code == "NO_NEW_CLOSE"


def test_ohlcv_unavailable_holds(strategy: OPTASwapMAStrategy):
    market = MagicMock()
    market.balance.side_effect = lambda token: TokenBalance(
        symbol=token,
        balance=Decimal("1"),
        balance_usd=Decimal("1000"),
        address="",
    )
    market.ohlcv.side_effect = ValueError("down")
    intent = strategy.decide(market)
    assert _intent_code(intent) == "HOLD"
    assert intent.reason_code == "DATA_UNAVAILABLE"


def test_force_action_buy_returns_swap(config: dict):
    cfg = {**config, "force_action": "buy"}
    strat = OPTASwapMAStrategy(config=cfg, chain="optimism", wallet_address="0x" + "2" * 40)
    market = _market([6, 6, 6, 6, 6, 6])
    intent = strat.decide(market)
    assert _intent_code(intent) == "SWAP"
    assert intent.from_token == "USDC"


def test_force_action_sell_returns_swap(config: dict):
    cfg = {**config, "force_action": "sell"}
    strat = OPTASwapMAStrategy(config=cfg, chain="optimism", wallet_address="0x" + "3" * 40)
    market = _market([6, 6, 6, 6, 6, 6])
    intent = strat.decide(market)
    assert _intent_code(intent) == "SWAP"
    assert intent.from_token == "WETH"


def test_persistent_state_round_trip(strategy: OPTASwapMAStrategy):
    strategy.buy_armed = False
    strategy.sell_armed = False
    strategy.last_processed_closed_ts = "2026-01-01T00:20:00+00:00"
    strategy.last_signal_side = "buy"
    strategy.position_side = "base"

    saved = strategy.get_persistent_state()
    dumped = json.dumps(saved)

    fresh = OPTASwapMAStrategy(config=_base_config(), chain="optimism", wallet_address="0x" + "4" * 40)
    fresh.load_persistent_state(json.loads(dumped))

    assert fresh.buy_armed is False
    assert fresh.sell_armed is False
    assert fresh.last_processed_closed_ts == "2026-01-01T00:20:00+00:00"
    assert fresh.last_signal_side == "buy"
    assert fresh.position_side == "base"


def test_teardown_emits_swap_when_base_exposed(strategy: OPTASwapMAStrategy):
    from almanak.framework.teardown import TeardownMode

    strategy.position_side = "base"
    intents = strategy.generate_teardown_intents(mode=TeardownMode.SOFT)
    assert len(intents) == 1
    assert intents[0].from_token == "WETH"
    assert intents[0].to_token == "USDC"


def test_get_open_positions_reflects_base_exposure(strategy: OPTASwapMAStrategy):
    strategy.position_side = "base"
    summary = strategy.get_open_positions()
    assert len(summary.positions) == 1
    assert summary.positions[0].details["symbol"] == "WETH"


def test_project_config_file_matches_strategy_defaults():
    config_path = Path(__file__).parent.parent / "config.json"
    with config_path.open() as fh:
        cfg = json.load(fh)
    assert cfg["chain"] == "optimism"
    assert cfg["protocol"] == "uniswap_v3"
    assert cfg["signal_timeframe"] == "5m"
    assert cfg["base_token"] == "WETH"
    assert cfg["quote_token"] == "USDC"
