# Crypto Regime Trader — v2 snapshot

Frozen snapshot of the **v2** generation of my Binance trading bot, kept for reference.
The current, maintained version (v3.0, with Kelly sizing, scale-out exits, walk-forward
backtests and a test suite) is **[crypto-regime-trader](https://github.com/Kotsur69/crypto-regime-trader)**.

What v2 already had:
- Pattern analysis plus a market-regime classifier (trend / range / volatile) per pair
- A decision engine with multi-timeframe confirmation and an LLM news-sentiment overlay
- A risk manager with an emergency stop, Binance testnet/mainnet execution and a learning module that scores past patterns
- A Flask dashboard and Discord notifications

Code is in [`crypto_trading_bot/`](crypto_trading_bot). Runtime state and trade logs were left out.
API keys in the configs are placeholders.
