You are Claude Code acting as a senior Python engineer.

Goal:
Create a working Polymarket trading bot using the “trading-strategies” skill from:
https://skills.sh/agentmc15/polymarket-trader/trading-strategies

Hard requirements:
1) Follow the skill’s interfaces and patterns (BaseStrategy, MarketState, Signal, Backtester/BacktestResult).
2) Produce a runnable Python project with:
   - /polymarket_bot (package)
   - /strategies (strategy implementations)
   - /data (optional local cache)
   - /scripts (run_backtest.py, run_paper.py, run_live.py)
   - pyproject.toml or requirements.txt
   - README.md with exact commands to run
3) No placeholders like “TODO: implement exchange.” If an API needs keys, implement the client with env vars and a clear error if missing.
4) Include logging, config via .env, and a “dry-run/paper mode”.
5) Include at least one complete strategy implementation + one backtest using historical data loaded from CSV/JSON.

Step-by-step tasks:
A) Pull in/replicate the skill code patterns:
   - Define dataclasses for MarketState and Signal exactly as expected by the skill.
   - Define BaseStrategy with generate_signal(market_state) and should_trade(signal, market_state).
   - Implement Backtester that simulates fills and PnL for YES/NO tokens, with slippage + fees params.

B) Implement Polymarket adapter:
   - Create PolymarketClient with methods:
     - list_markets()
     - get_market_state(market_id) -> MarketState (orderbook, mid price, volume, timestamp)
     - place_order(market_id, side, outcome, price, size)
     - cancel_order(order_id)
   - All keys from env vars:
     POLYMARKET_API_KEY, POLYMARKET_API_SECRET (or whatever the API requires)
   - If official API isn’t available, implement a “mock client” and clearly separate it, but still keep the bot runnable end-to-end in paper mode.

C) Strategy:
   - Implement MeanReversionStrategy using the skill style:
     - compute z-score of mid price vs rolling mean/std
     - buy YES when z < -z_entry, sell/exit when z > -z_exit (or vice versa)
     - risk controls: max position per market, daily loss limit, stop-loss, cooldown after trade

D) Runners:
   - run_backtest.py: loads ./data/history_<market_id>.csv, runs Backtester, prints metrics and saves results JSON.
   - run_paper.py: polls markets every N seconds, generates signals, simulates fills, logs trades.
   - run_live.py: same as paper but uses real place_order (guarded by --i-know-what-im-doing flag).

E) Deliverables:
   - Full code for all files (no ellipses), ready to copy into a folder and run.
   - A short README with setup + example commands.
   - A section “How to add a new strategy” referencing BaseStrategy.

Proceed by:
1) Proposing the file tree.
2) Then outputting each file with a header like: ### path/to/file.py
3) Ensure everything runs on Python 3.11.
