You are an expert Python engineer building a maintainable stock screening tool with optional market news enrichment.

Goal

Identify and summarize relevant stocks based on user-provided screening criteria. Analyze each stock against the criteria, organize findings clearly, and enrich with recent trading/stock news headlines + sentiment (optional) to support decision-making.

Repo / Data-source options (pick best-fit; prefer stable & widely used)

Data platform baseline (preferred):

Use OpenBB as the main data access layer if it supports the required metrics (fundamentals/technicals) for the target market.

TradingView screener wrappers (only if needed; note unofficial / ToS risk)

GitHub repos (choose one; justify):

shner-elmo/TradingView-Screener

deepentropy/tvscreener

j-miet/screenerfetch

If the market is India/NSE and breakout-style scans are needed, consider:

pkjmesra/PKScreener

IMPORTANT: If using TradingView-based scraping/unofficial endpoints, clearly flag ToS/compliance concerns and provide an alternative approach (e.g., OpenBB + official data vendors).

News APIs (optional; pick one and integrate cleanly)

Support at least one of these as a pluggable provider:

Finnhub

Alpha Vantage

Alpaca Markets news

Financial Modeling Prep

NewsAPI (general news; filter by tickers/keywords)

User inputs (make these CLI args + config file)

market: (US / TASE / NSE / other)

universe: list of tickers OR “all from exchange” OR sector list

criteria: a list of filters, e.g.

Market Cap: > X

P/E: < Y

Dividend Yield: > Z

Revenue growth, EPS growth, debt/equity, ROE, etc.

Technical filters (optional): RSI threshold, MA crossover, breakout, volume spike, ATR, etc.

ranking weights (optional): how to rank passing stocks (value score, quality score, momentum score)

news settings (optional): last N days, max headlines per ticker

Required behavior

Criteria Analysis

Parse and validate criteria.

For each criterion, state the required metric and how it’s computed.

Data Gathering

Use reliable, up-to-date sources (prefer official APIs or widely used libraries).

Implement caching (disk) + rate-limit handling.

Filtering

Apply filters; keep an explainable “pass/fail” reason per stock per criterion.

Comparison and Summary

Produce a table of passing stocks with key metrics used in criteria + ranking score.

Insights

Provide short insights: why top 3–10 stocks rank highest, any red flags, missing data warnings.

If news enabled: attach 3–5 recent headlines per top ticker + optional sentiment score if available.

Output format (must match exactly)

A) Table (markdown) for passing stocks:

Company | Ticker | Market | Key metrics columns (only those used) | Rank score | Pass/Fail notes (short)

B) Analysis section

Top picks summary (bullet list)

Notable risks / caveats (data freshness, missing fields, ToS if relevant)

C) Artifacts

Save results to:

results.csv (full table)

results.json (full details incl. per-criterion pass/fail + news headlines)

run.log (timings, API calls count, cache hits)

Implementation constraints

Python project with clean structure:

/src (providers, screener, scoring, utils)

/configs (yaml/json)

/scripts (cli entry)

/tests (basic tests for criteria parsing and filtering)

Provide a single command:

python -m screener run --config configs/example.yaml

Keep code readable and modular. Add minimal but useful docstrings. No over-commenting.

Safety / compliance note

Do NOT give personalized financial advice. Present data-driven screening results and explain assumptions. Encourage users to verify and consider risk.

Deliverables

Full codebase files

example config

README: setup, providers, how to add criteria, limitations

Now build it.