import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd

from almanak.framework.intents import Intent
from almanak.framework.market import MarketSnapshot
from almanak.framework.strategies import IntentStrategy, almanak_strategy

logger = logging.getLogger(__name__)


@almanak_strategy(
    name="o_p_t_a_swap_m_a",
    description="EMA crossover swap strategy with reset gating",
    version="1.0.0",
    author="Generated",
    tags=["ta", "ema", "swap", "momentum"],
    supported_chains=["optimism"],
    supported_protocols=["uniswap_v3"],
    intent_types=["SWAP", "HOLD"],
    default_chain="optimism",
)
class OPTASwapMAStrategy(IntentStrategy):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.protocol = str(self.get_config("protocol", "uniswap_v3"))
        self.base_token = str(self.get_config("base_token", "WETH"))
        self.quote_token = str(self.get_config("quote_token", "USDC"))
        self.signal_timeframe = str(self.get_config("signal_timeframe", "5m"))
        self.fast_ema_period = int(self.get_config("fast_ema_period", 8))
        self.slow_ema_period = int(self.get_config("slow_ema_period", 21))
        self.ohlcv_limit = int(self.get_config("ohlcv_limit", 80))
        self.min_trade_value_usd = Decimal(str(self.get_config("min_trade_value_usd", "25")))
        self.max_slippage_bps = int(self.get_config("max_slippage_bps", 50))
        self.force_action = str(self.get_config("force_action", "")).strip().lower()

        self.buy_armed = True
        self.sell_armed = True
        self.last_processed_closed_ts: str | None = None
        self.last_signal_side: str | None = None
        self.position_side = "quote"

    @property
    def max_slippage(self) -> Decimal:
        return Decimal(str(self.max_slippage_bps)) / Decimal("10000")

    def decide(self, market: MarketSnapshot) -> Intent | None:
        if self.force_action:
            return self._forced_intent(market)

        try:
            quote_balance = market.balance(self.quote_token)
            base_balance = market.balance(self.base_token)
        except ValueError as exc:
            return Intent.hold(
                reason=f"Balance unavailable: {exc}",
                reason_code="DATA_UNAVAILABLE",
            )

        try:
            candles = market.ohlcv(
                self.base_token,
                timeframe=self.signal_timeframe,
                limit=self.ohlcv_limit,
            )
        except ValueError as exc:
            return Intent.hold(
                reason=f"OHLCV unavailable: {exc}",
                reason_code="DATA_UNAVAILABLE",
            )

        if candles.empty or "close" not in candles.columns or "timestamp" not in candles.columns:
            return Intent.hold(
                reason="OHLCV missing close/timestamp columns",
                reason_code="DATA_UNAVAILABLE",
            )

        required = max(self.slow_ema_period + 3, 4)
        if len(candles) < required:
            return Intent.hold(
                reason=f"Need {required} candles, got {len(candles)}",
                reason_code="INSUFFICIENT_CANDLES",
            )

        ordered = candles.sort_values("timestamp").reset_index(drop=True)
        closed_ts = self._timestamp_key(ordered.iloc[-2]["timestamp"])
        if self.last_processed_closed_ts == closed_ts:
            return Intent.hold(reason="No new confirmed candle close", reason_code="NO_NEW_CLOSE")

        closes = pd.to_numeric(ordered["close"], errors="coerce")
        if closes.isna().any():
            return Intent.hold(reason="OHLCV close contains NaN", reason_code="DATA_UNAVAILABLE")

        ema_fast = closes.ewm(span=self.fast_ema_period, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow_ema_period, adjust=False).mean()

        fast_prev = Decimal(str(ema_fast.iloc[-3]))
        slow_prev = Decimal(str(ema_slow.iloc[-3]))
        fast_curr = Decimal(str(ema_fast.iloc[-2]))
        slow_curr = Decimal(str(ema_slow.iloc[-2]))

        if fast_curr <= slow_curr:
            self.buy_armed = True
        if fast_curr >= slow_curr:
            self.sell_armed = True

        bull_cross = fast_prev <= slow_prev and fast_curr > slow_curr
        bear_cross = fast_prev >= slow_prev and fast_curr < slow_curr

        self.last_processed_closed_ts = closed_ts

        if bull_cross:
            if not self.buy_armed:
                return Intent.hold(reason="Bull crossover not re-armed", reason_code="NOT_REARMED")
            if quote_balance.balance_usd < self.min_trade_value_usd:
                return Intent.hold(
                    reason=(
                        f"Insufficient {self.quote_token} balance_usd "
                        f"{quote_balance.balance_usd} < {self.min_trade_value_usd}"
                    ),
                    reason_code="INSUFFICIENT_BALANCE",
                )
            self.buy_armed = False
            self.last_signal_side = "buy"
            self.position_side = "base"
            return self._buy_intent()

        if bear_cross:
            if not self.sell_armed:
                return Intent.hold(reason="Bear crossover not re-armed", reason_code="NOT_REARMED")
            if base_balance.balance_usd < self.min_trade_value_usd:
                return Intent.hold(
                    reason=(
                        f"Insufficient {self.base_token} balance_usd "
                        f"{base_balance.balance_usd} < {self.min_trade_value_usd}"
                    ),
                    reason_code="INSUFFICIENT_BALANCE",
                )
            self.sell_armed = False
            self.last_signal_side = "sell"
            self.position_side = "quote"
            return self._sell_intent()

        return Intent.hold(reason="No EMA crossover", reason_code="NO_CROSSOVER")

    def _forced_intent(self, market: MarketSnapshot) -> Intent:
        if self.force_action == "buy":
            quote_balance = market.balance(self.quote_token)
            if quote_balance.balance_usd < self.min_trade_value_usd:
                return Intent.hold(reason="Insufficient quote balance for forced buy", reason_code="INSUFFICIENT_BALANCE")
            self.last_signal_side = "buy"
            self.position_side = "base"
            self.buy_armed = False
            return self._buy_intent()

        if self.force_action == "sell":
            base_balance = market.balance(self.base_token)
            if base_balance.balance_usd < self.min_trade_value_usd:
                return Intent.hold(reason="Insufficient base balance for forced sell", reason_code="INSUFFICIENT_BALANCE")
            self.last_signal_side = "sell"
            self.position_side = "quote"
            self.sell_armed = False
            return self._sell_intent()

        return Intent.hold(reason=f"Unknown force_action: {self.force_action}", reason_code="UNKNOWN_FORCE_ACTION")

    def _buy_intent(self) -> Intent:
        return Intent.swap(
            from_token=self.quote_token,
            to_token=self.base_token,
            amount="all",
            max_slippage=self.max_slippage,
            protocol=self.protocol,
            chain=self.chain,
        )

    def _sell_intent(self) -> Intent:
        return Intent.swap(
            from_token=self.base_token,
            to_token=self.quote_token,
            amount="all",
            max_slippage=self.max_slippage,
            protocol=self.protocol,
            chain=self.chain,
        )

    def on_intent_executed(self, intent, success: bool, result):
        if not success:
            return
        if getattr(intent.intent_type, "value", "") != "SWAP":
            return
        if getattr(intent, "to_token", None) == self.base_token:
            self.position_side = "base"
        elif getattr(intent, "to_token", None) == self.quote_token:
            self.position_side = "quote"

    def get_status(self) -> dict[str, Any]:
        return {
            "strategy": self.STRATEGY_NAME,
            "chain": self.chain,
            "base_token": self.base_token,
            "quote_token": self.quote_token,
            "signal_timeframe": self.signal_timeframe,
            "buy_armed": self.buy_armed,
            "sell_armed": self.sell_armed,
            "last_processed_closed_ts": self.last_processed_closed_ts,
            "last_signal_side": self.last_signal_side,
            "position_side": self.position_side,
        }

    def get_persistent_state(self):
        return {
            "buy_armed": self.buy_armed,
            "sell_armed": self.sell_armed,
            "last_processed_closed_ts": self.last_processed_closed_ts,
            "last_signal_side": self.last_signal_side,
            "position_side": self.position_side,
        }

    def load_persistent_state(self, state):
        if not state:
            return
        self.buy_armed = bool(state.get("buy_armed", True))
        self.sell_armed = bool(state.get("sell_armed", True))
        self.last_processed_closed_ts = state.get("last_processed_closed_ts")
        self.last_signal_side = state.get("last_signal_side")
        self.position_side = state.get("position_side", "quote")

    def get_open_positions(self):
        from almanak.framework.teardown import PositionInfo, PositionType, TeardownPositionSummary

        positions: list[PositionInfo] = []
        if self.position_side == "base":
            positions.append(
                PositionInfo(
                    position_type=PositionType.TOKEN,
                    position_id=f"{self.STRATEGY_NAME}:base",
                    chain=self.chain,
                    protocol=self.protocol,
                    value_usd=Decimal("0"),
                    details={"symbol": self.base_token},
                )
            )

        return TeardownPositionSummary(
            strategy_id=self.strategy_id or self.STRATEGY_NAME,
            timestamp=datetime.now(UTC),
            positions=positions,
        )

    def generate_teardown_intents(self, mode=None, market=None) -> list[Intent]:
        from almanak.framework.teardown import TeardownMode

        if self.position_side != "base":
            return []

        slippage = Decimal("0.03") if mode == TeardownMode.HARD else self.max_slippage
        return [
            Intent.swap(
                from_token=self.base_token,
                to_token=self.quote_token,
                amount="all",
                max_slippage=slippage,
                protocol=self.protocol,
                chain=self.chain,
            )
        ]

    @staticmethod
    def _timestamp_key(value: Any) -> str:
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
