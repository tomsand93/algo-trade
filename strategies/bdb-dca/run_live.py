"""
CLI entry point for the BDB DCA live paper trading bot.

Usage:
  python run_live.py            Start live bot
  python run_live.py --risk     Start with risk engine enabled
  python run_live.py --dry-run  Warmup only, no trading
  python run_live.py --status   Print Alpaca account info and exit

Requires environment variables:
  ALPACA_API_KEY
  ALPACA_API_SECRET
"""

import argparse
import logging
import os
import sys

# Add parent dir so bdb_dca package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bdb_dca.config import StrategyConfig
from bdb_dca.risk import RiskConfig
from bdb_dca.live_bot import LiveBot
from bdb_dca.alpaca_broker import AlpacaBroker


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("alpaca").setLevel(logging.WARNING)


def print_status():
    """Print Alpaca account info and open positions."""
    broker = AlpacaBroker()
    acct = broker.connect()

    print(f"\n{'='*50}")
    print(f"  Alpaca Paper Account Status")
    print(f"{'='*50}")
    print(f"  Equity:        ${float(acct.equity):,.2f}")
    print(f"  Cash:          ${float(acct.cash):,.2f}")
    print(f"  Buying Power:  ${float(acct.buying_power):,.2f}")
    print(f"  Portfolio Val:  ${float(acct.portfolio_value):,.2f}")
    print(f"  Day P&L:       ${float(acct.equity) - float(acct.last_equity):,.2f}")
    print()

    pos = broker.get_btc_position()
    if pos:
        print(f"  BTC/USD Position:")
        print(f"    Qty:           {pos.qty}")
        print(f"    Avg Entry:     ${float(pos.avg_entry_price):,.2f}")
        print(f"    Market Value:  ${float(pos.market_value):,.2f}")
        print(f"    Unrealized PL: ${float(pos.unrealized_pl):,.2f}")
    else:
        print(f"  BTC/USD Position: FLAT")

    orders = broker.get_open_orders(symbol="BTC/USD")
    print(f"\n  Open Orders ({len(orders)}):")
    for o in orders:
        side = o.side.value if hasattr(o.side, 'value') else o.side
        otype = o.type.value if hasattr(o.type, 'value') else o.type
        stop_str = f" stop=${float(o.stop_price):,.2f}" if o.stop_price else ""
        limit_str = f" limit=${float(o.limit_price):,.2f}" if o.limit_price else ""
        print(f"    {side} {otype} qty={o.qty}{stop_str}{limit_str} "
              f"cid={o.client_order_id}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="BDB DCA Live Paper Trading Bot")
    parser.add_argument("--risk", action="store_true",
                        help="Enable risk engine")
    parser.add_argument("--dry-run", action="store_true",
                        help="Warmup only, no live trading")
    parser.add_argument("--status", action="store_true",
                        help="Print Alpaca account status and exit")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    parser.add_argument("--capital", type=float, default=None,
                        help="Override initial capital (default: use Alpaca equity)")
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)

    # Check for API keys
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_API_SECRET"):
        print("ERROR: ALPACA_API_KEY and ALPACA_API_SECRET environment variables required.")
        print("Set them in your shell or in a .env file.")
        sys.exit(1)

    if args.status:
        print_status()
        return

    # Live mode config overrides
    config = StrategyConfig(
        symbol="BTC/USD",            # Alpaca uses USD pairs
        commission_pct=0.15,         # Alpaca crypto taker fee
        slippage_ticks=0,            # Real fills, no simulated slippage
        tick_size=0.01,              # BTC tick size
        initial_capital=args.capital or 10000.0,
    )

    risk_config = RiskConfig() if args.risk else None

    bot = LiveBot(
        config=config,
        risk_config=risk_config,
        dry_run=args.dry_run,
    )
    bot.start()


if __name__ == "__main__":
    main()
