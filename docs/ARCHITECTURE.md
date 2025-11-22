# Traderbot Momentum Architecture

## Design Principles
- **Adapters over vendors** – define venue-agnostic interfaces for data providers and broker clients, then plug Massive, Alpaca, or mocks via a registry.
- **Library + Actions pattern** – pure logic lives under `src/…`; each CLI action in `actions/` calls a single library entry point.
- **CSV-first contracts** – every stage emits canonical CSVs (`data/raw`, `data/processed`, `data/results`) to make debugging and downstream analytics trivial.
- **Stateless steps, explicit state** – transient work happens in-memory; durable state (`state/portfolio.json`, pointers, logs) is written intentionally.
- **Topic-based modularity** – analytics, backtesting, config, data, execution, strategies, utils, venues, orchestration each own one concern, simplifying ownership and testing.
- **Fail fast with remediation** – every action/orchestrator surfaces missing config, credentials, or schema violations clearly.

## Directory Tree
```
.
├─ docs/
│  └─ ARCHITECTURE.md
├─ config/
│  └─ strategy/
├─ data/
│  ├─ raw/
│  ├─ processed/
│  └─ results/
├─ state/
├─ src/
│  ├─ analytics/
│  ├─ backtesting/
│  ├─ config/
│  ├─ data/
│  ├─ execution/
│  ├─ strategies/
│  ├─ utils/
│  ├─ venues/
│  └─ orchestration/
├─ actions/
└─ tests/
```

## Module Responsibilities
| Folder | Purpose |
| --- | --- |
| `src/analytics/` | Feature engineering (returns, momentum, spreads, technical indicators), feature assemblers, statistical helpers for pairs/cross-section signals. |
| `src/backtesting/` | Vectorized daily-bar engine, scenario runner, performance metrics, evaluation utilities, report writers (equity, trades, attribution). |
| `src/config/` | Loaders and validators for `.env`, TOML, YAML; typed settings objects passed into pipelines/actions. |
| `src/data/` | IO helpers (CSV reader/writer in canonical schema), ingest adapters, state stores, cache layers, gap detection. |
| `src/execution/` | Order normalization, slippage/fee models, paper fills, broker routing (re-using venue adapters). |
| `src/strategies/` | Strategy definitions (pairs momentum, cross-sectional, etc.), signal generation pipelines, registries for enabling/disabling strategies. |
| `src/utils/` | Time/calendar helpers, logging setup, shared types/errors, math helpers. |
| `src/venues/` | Base ABCs for `DataProvider`/`BrokerClient`, Massive/Alpaca adapters, registry for selecting venues by name. |
| `src/orchestration/` | Workflow coordinators (`daily_pipeline.py`, `clock.py`) assembling config, data refresh, feature builds, signal generation, (paper) execution, persistence. |
| `actions/` | One-file-per-action scripts invoking the corresponding library functions (connection checks, fetch history, feature builds, etc.). |
| `tests/` | Unit + smoke/integration tests mirroring `src/` layout, verifying CSV contracts and orchestrator flows. |

## Canonical CSV Schemas
- **Raw symbol CSV** (`data/raw/{SYMBOL}.csv`): `symbol,date,open,high,low,close,volume` – ISO `YYYY-MM-DD`, strictly increasing dates, one row per day.
- **Processed symbol CSV** (`data/processed/{SYMBOL}.csv`): raw columns plus `ret_1d,ret_5d,sma_20,sma_50,ema_20,rsi_14,macd,macd_signal,bb_mid,bb_up,bb_dn,atr_14,slope_20`.
- **Processed pair CSV** (`data/processed/pairs/{LONG}_{SHORT}.csv` or similar): raw columns for each leg plus `close_long,close_short,ret_long,ret_short,beta,spread,zscore_60,mom_60,hedge_mode`.
- **Signal CSVs** (future): include symbol/pair identifiers, signal timestamp, direction, size, confidence, metadata (TBD).
- Ordering and headers must remain consistent; actions validate schema before writing.

## Ports & Adapters
- **DataProvider interface (`src/venues/base.py`)**
  ```python
  class DataProvider(Protocol):
      def get_history(self, symbol: str, start: str, end: str, timeframe: str = "1d") -> pandas.DataFrame: ...
  ```
  - Returns canonical OHLCV DataFrame with `RAW_COLS`.
  - Adapters: `MassiveDataProvider`, `AlpacaDataProvider`, `MockDataProvider`.

- **BrokerClient interface**
  ```python
  class BrokerClient(Protocol):
      def place_order(self, order: Order) -> OrderResult: ...
      def get_positions(self) -> list[Position]: ...
  ```
  - Normalized order objects provided by `src/execution/normalize.py`.
  - Paper broker implements the same interface for backtests/sandbox.

- **Adapter registry (`src/venues/registry.py`)**
  ```python
  def get_data_provider(name: str, **kwargs) -> DataProvider: ...
  def get_broker_client(name: str, **kwargs) -> BrokerClient: ...
  ```
  - Maps names like `"massive"` or `"alpaca"` to constructors, injecting config and credentials.

## Time & Calendar Layer (`src/utils/time.py`)
- `get_calendar(market: str, mode: str = "regular") -> TradingCalendar`
- `is_trading_day(dt: datetime, market: str) -> bool`
- `session_bounds(date: date, market: str) -> tuple[datetime, datetime]`
- `session_date(ts: datetime, market: str) -> date`
- `align_to_sessions(series: DataFrame, market: str, mode: str = "regular"|"24/7") -> DataFrame`
- `fetch_window(anchor: date, lookback: int, lookahead: int, calendar) -> tuple[date, date]`
- `rebalance_dates(start: date, end: date, frequency: str = "monthly") -> list[date]`
- `window_of_interest(end: date, length: int, calendar) -> list[date]`
- Support regular US equities calendar plus optional 24/7 mode (crypto-like assets) for `is_trading_day` and window calculations.

## Backtesting Plan
- **Engine**: iterate by session (daily bars). For each date, feed features and signals into a paper broker to produce fills, update positions, and mark-to-market.
- **Paper fills**: configurable slippage/fee model in `src/execution/`.
- **Outputs**: equity curve CSV, trades ledger CSV, metrics JSON per backtest run in `data/results/`.
- **Metrics**: Sharpe, Sortino, ROI, CAGR, annualized volatility, max drawdown, Calmar, Information Ratio, plus rolling versions (e.g., 60-day Sharpe) and hit rate/win ratio.
- **Evaluation**: parameter sweeps, walk-forward splits, scenario comparisons via `src/backtesting/evaluate.py`.

## Orchestration Design
- `src/orchestration/daily_pipeline.py`
  - Steps: load config → resolve venues via registry → check Massive/Alpaca connectivity → fetch/append OHLCV into `data/raw/` → run analytics builders to produce `data/processed/` → call strategy generators for signals → optionally trigger paper execution → persist summaries (state, logs, `data/results/`).
  - Pure library module returning structured summaries and writing artifacts.
- `actions/run_daily_pipeline.py`
  - Thin CLI: parse `--symbols`, `--start`, `--end`, `--days`, import `run_pipeline` and print human-friendly status; all heavy lifting stays in orchestration.
- `src/orchestration/clock.py`
  - (Optional) scheduler helpers to trigger actions pre-open, pre-close, or on custom cron intervals; wraps APScheduler/Cron-style triggers when introduced.

## Phased Build Plan
1. **Iteration 1** – Massive connection check, ingest action (`actions/fetch_history_massive.py`), data-ingest-only pipeline. Fail fast when credentials missing.
2. **Iteration 2** – Implement analytics layer (`src/analytics/`), processed dataset builders, and matching action to populate `data/processed/`.
3. **Iteration 3** – Strategy modules in `src/strategies/`, strategy registry, signal generation action writing to `data/results/signals.csv`.
4. **Iteration 4** – Backtesting engine, metrics, reporting pipelines, CLI actions for backtest + metrics.
5. **Iteration 5** – Paper execution + portfolio state management, order normalization, action to simulate trades.
6. **Iteration 6+** – Live broker adapters, risk sizing enhancements, ML allocators, dashboards/monitoring.

## Acceptance Criteria for This Architecture
- Document is skimmable with clear headers, tables, and explicit interfaces/schemas.
- CSV contracts are unambiguous (names, order, data rules).
- Ports/adapters specify exact function signatures and responsibility boundaries.
- Each topic folder under `src/` has defined responsibilities and supporting explanation in README + this document.
- One action corresponds to one library module/function to keep the mental map tight.
