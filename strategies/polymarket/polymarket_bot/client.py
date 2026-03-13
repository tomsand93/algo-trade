"""Polymarket data clients for Phase 1 and Phase 4.

ReplayClient: reads a JSONL snapshot file and yields MarketState objects.
MockClient: generates synthetic MarketState objects with random but valid prices.
PolymarketClient: L0 client — fetches real Polymarket market data for paper trading.
PolymarketLiveClient: L2 client — fetches market data AND places real signed orders.

All implement the same interface: get_market_states() -> Iterator[MarketState].
"""
import json
import random
from datetime import datetime, timezone
from typing import Iterator

from loguru import logger

from polymarket_bot.models import MarketState, SimulatedOrder


class ReplayClient:
    """Reads a JSONL snapshot file and yields MarketState objects sequentially.

    Sequential replay preserves price-series shape for deterministic signal testing.
    Malformed lines are skipped with a WARNING log — one bad line never crashes a run.
    """

    def __init__(self, snapshot_path: str) -> None:
        self.snapshot_path = snapshot_path

    def get_market_states(self) -> Iterator[MarketState]:
        """Yield MarketState objects from the snapshot file, one per line."""
        with open(self.snapshot_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "REPLAY: skipping malformed line {n} in {path}: {exc}",
                        n=line_num,
                        path=self.snapshot_path,
                        exc=exc,
                    )
                    continue

                try:
                    yield MarketState(
                        market_id=raw["market_id"],
                        question=raw["question"],
                        yes_price=raw["yes_price"],
                        no_price=raw["no_price"],
                        volume_24h=raw["volume_24h"],
                        timestamp=datetime.fromisoformat(raw["captured_at"]),
                    )
                except (KeyError, ValueError) as exc:
                    logger.warning(
                        "REPLAY: skipping invalid market state on line {n}: {exc}",
                        n=line_num,
                        exc=exc,
                    )
                    continue


class MockClient:
    """Generates synthetic MarketState objects with random but valid prices.

    Used for --mode mock when no snapshot file is available.
    Prices are always in [0.01, 0.99] and sum to 1.00, so MarketState validation passes.

    Also provides cancel_order() to satisfy DATA-05: bot can cancel open orders.
    In mock mode, cancellation is simulated by returning the order with status='CANCELLED'.
    """

    MOCK_MARKETS = [
        ("0xmock001", "Will BTC reach $150k by end of 2026?"),
        ("0xmock002", "Will ETH ETF approval happen before Q3 2026?"),
        ("0xmock003", "Will the Fed cut rates more than 3 times in 2026?"),
        ("0xmock004", "Will Polymarket process $10B volume in 2026?"),
        ("0xmock005", "Will a major AI lab release AGI by 2027?"),
    ]

    # Number of synthetic time-step observations to generate per market.
    # Must be >= the default rolling_window (20) so strategy signals can fire.
    STEPS_PER_MARKET = 25

    def __init__(self, seed: int | None = None) -> None:
        """Optionally seed for reproducible mock data in tests."""
        if seed is not None:
            random.seed(seed)
        # Track open orders so cancel_order() can locate them by order_id
        self._orders: dict[str, "SimulatedOrder"] = {}

    def get_market_states(self) -> Iterator[MarketState]:
        """Yield STEPS_PER_MARKET synthetic MarketState observations per mock market.

        Prices cycle through a random walk (±0.02 per step, clamped to [0.05, 0.95])
        to produce realistic price series that allow the rolling window to fill.
        """
        from polymarket_bot.models import MarketState
        now = datetime.now(timezone.utc)
        for market_id, question in self.MOCK_MARKETS:
            yes_price = round(random.uniform(0.30, 0.70), 4)
            for _ in range(self.STEPS_PER_MARKET):
                no_price = round(1.0 - yes_price, 4)
                volume = round(random.uniform(1000, 500000), 2)
                yield MarketState(
                    market_id=market_id,
                    question=question,
                    yes_price=yes_price,
                    no_price=no_price,
                    volume_24h=volume,
                    timestamp=now,
                )
                # Small random walk: ±0.02 per step, clamped to [0.05, 0.95]
                delta = round(random.uniform(-0.02, 0.02), 4)
                yes_price = round(min(0.95, max(0.05, yes_price + delta)), 4)

    def register_order(self, order: "SimulatedOrder") -> None:
        """Register a SimulatedOrder so it can be cancelled by order_id."""
        from polymarket_bot.models import SimulatedOrder
        self._orders[order.order_id] = order

    def cancel_order(self, order_id: str) -> "SimulatedOrder":
        """Cancel a previously registered order and return it with status='CANCELLED'.

        Raises KeyError if the order_id is not found (order was never registered
        or was already removed). In Phase 1 this is a simulated cancellation only —
        no real API calls are made.
        """
        from polymarket_bot.models import SimulatedOrder
        order = self._orders.pop(order_id)
        cancelled = order.model_copy(update={"status": "CANCELLED"})
        logger.info(
            "ORDER CANCELLED | order_id={order_id} | market={market_id}",
            order_id=order_id,
            market_id=cancelled.market_id,
        )
        return cancelled


class PolymarketClient:
    """L0 client for paper trading — fetches real Polymarket market data, places no orders.

    Implements get_market_states() -> Iterator[MarketState] to match MockClient/ReplayClient.
    Uses ClobClient with no credentials (L0: read-only public endpoints).

    Critical: get_midpoint() and get_order_book() require token_id (from market.tokens[]),
    NOT condition_id. These are different identifiers — passing condition_id returns wrong data.
    """

    CLOB_HOST = "https://clob.polymarket.com"

    def __init__(self) -> None:
        from py_clob_client.client import ClobClient
        self._clob = ClobClient(self.CLOB_HOST)

    def get_market_states(self) -> Iterator[MarketState]:
        """Fetch all active markets and yield one MarketState per YES token.

        Pagination: get_simplified_markets() returns cursor-based pages. Loop while
        next_cursor != "LTE=" (Polymarket's terminal cursor sentinel), passing the
        cursor from the previous response as next_cursor to the next call.
        Filter: skip inactive (active=False) and resolved (closed=True) markets.
        Price: use get_midpoint(yes_token_id) — clamped to [0.01, 0.99].
        Error handling: exceptions from get_midpoint() skip that market (log warning, continue).
        """
        now = datetime.now(timezone.utc)

        # Paginate all markets — Polymarket API returns first page only if no cursor given
        all_markets: list = []
        cursor = None
        while True:
            raw = self._clob.get_simplified_markets(next_cursor=cursor)
            all_markets.extend(raw.get("data", []))
            cursor = raw.get("next_cursor")
            if cursor == "LTE=" or not cursor:
                break

        for m in all_markets:
            if not m.get("active") or m.get("closed"):
                continue

            tokens = m.get("tokens", [])
            yes_token = next(
                (t for t in tokens if t["outcome"].lower() == "yes"), None
            )
            no_token = next(
                (t for t in tokens if t["outcome"].lower() == "no"), None
            )
            if not yes_token or not no_token:
                continue

            try:
                mid_resp = self._clob.get_midpoint(yes_token["token_id"])
                yes_price = float(mid_resp.get("mid", 0.5) or 0.5)
                yes_price = max(0.01, min(0.99, yes_price))
                no_price = round(1.0 - yes_price, 4)
                yield MarketState(
                    market_id=m["condition_id"],
                    question=m.get("question", ""),
                    yes_price=yes_price,
                    no_price=no_price,
                    volume_24h=float(m.get("volume", 0.0) or 0.0),
                    timestamp=now,
                )
            except Exception as exc:
                logger.warning(
                    "POLYMARKET: skipping market {}: {}",
                    m.get("condition_id", "?"),
                    exc,
                )
                continue


class PolymarketLiveClient:
    """L2 client for live trading — fetches market data AND places real orders.

    Requires valid API credentials in Settings:
      - polymarket_private_key (wallet private key)
      - polymarket_api_key, polymarket_api_secret, polymarket_api_passphrase (from derive_creds.py)
      - signature_type: 0=EOA, 1=POLY_PROXY, 2=GNOSIS_SAFE

    get_market_states() fetches and paginates ALL markets, caches {condition_id -> yes_token_id}
    in _token_id_cache. place_live_order() resolves the yes_token_id from this cache using
    signal.market_id — run_loop() does NOT need to know about token_id at all.

    Returns SimulatedOrder for compatibility with record_fill() in run_loop().
    """

    CLOB_HOST = "https://clob.polymarket.com"

    def __init__(self, settings) -> None:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        creds = ApiCreds(
            api_key=settings.polymarket_api_key.get_secret_value(),
            api_secret=settings.polymarket_api_secret.get_secret_value(),
            api_passphrase=settings.polymarket_api_passphrase.get_secret_value(),
        )
        self._clob = ClobClient(
            self.CLOB_HOST,
            key=settings.polymarket_private_key.get_secret_value(),
            chain_id=137,
            creds=creds,
            signature_type=settings.signature_type,
        )
        # Populated by get_market_states(); maps condition_id -> yes_token_id for order placement
        self._token_id_cache: dict[str, str] = {}

    def get_market_states(self) -> Iterator[MarketState]:
        """Fetch all active markets, cache yes_token_ids, and yield MarketState objects.

        Pagination: loops while next_cursor != "LTE=", same as PolymarketClient.
        Cache: populates self._token_id_cache = {condition_id: yes_token_id} so that
        place_live_order() can resolve token_id without requiring caller knowledge.
        """
        now = datetime.now(timezone.utc)

        # Paginate all markets and populate token_id cache
        all_markets: list = []
        cursor = None
        while True:
            raw = self._clob.get_simplified_markets(next_cursor=cursor)
            all_markets.extend(raw.get("data", []))
            cursor = raw.get("next_cursor")
            if cursor == "LTE=" or not cursor:
                break

        for m in all_markets:
            if not m.get("active") or m.get("closed"):
                continue
            tokens = m.get("tokens", [])
            yes_token = next(
                (t for t in tokens if t["outcome"].lower() == "yes"), None
            )
            no_token = next(
                (t for t in tokens if t["outcome"].lower() == "no"), None
            )
            if not yes_token or not no_token:
                continue
            # Cache yes_token_id before attempting price fetch — ensures place_live_order()
            # has the token_id even if get_midpoint() would fail for this market
            self._token_id_cache[m["condition_id"]] = yes_token["token_id"]
            try:
                mid_resp = self._clob.get_midpoint(yes_token["token_id"])
                yes_price = float(mid_resp.get("mid", 0.5) or 0.5)
                yes_price = max(0.01, min(0.99, yes_price))
                no_price = round(1.0 - yes_price, 4)
                yield MarketState(
                    market_id=m["condition_id"],
                    question=m.get("question", ""),
                    yes_price=yes_price,
                    no_price=no_price,
                    volume_24h=float(m.get("volume", 0.0) or 0.0),
                    timestamp=now,
                )
            except Exception as exc:
                logger.warning(
                    "POLYMARKET LIVE: skipping market {}: {}",
                    m.get("condition_id", "?"),
                    exc,
                )
                continue

    def place_live_order(self, signal, max_position_size: float) -> "SimulatedOrder":
        """Create and submit a real signed order; return SimulatedOrder for record_fill().

        Resolves yes_token_id from _token_id_cache[signal.market_id] — populated by the
        preceding call to get_market_states() in the same run_loop() tick. run_loop() does
        NOT need to know about token_id.

        Uses EIP-712 signing via py-clob-client. The signed order is submitted as GTC.
        Returns a SimulatedOrder with status=FILLED for record_fill() accounting.
        """
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        token_id = self._token_id_cache[signal.market_id]  # KeyError means market not seen yet
        side = BUY if "BUY" in signal.direction else SELL
        size = round(max_position_size / signal.price, 4) if signal.price > 0 else 0.0

        order_args = OrderArgs(
            token_id=token_id,
            price=signal.price,
            size=size,
            side=side,
        )
        signed = self._clob.create_order(order_args)
        resp = self._clob.post_order(signed, OrderType.GTC)

        logger.info("LIVE ORDER PLACED | market={} | resp={}", signal.market_id, resp)

        out_side = "YES" if "YES" in signal.direction else "NO"
        out_direction = "BUY" if "BUY" in signal.direction else "SELL"

        return SimulatedOrder(
            market_id=signal.market_id,
            side=out_side,
            direction=out_direction,
            fill_price=signal.price,
            quantity=size,
            status="FILLED",
            timestamp=datetime.now(timezone.utc),
        )
