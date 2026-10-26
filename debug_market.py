from src.agents.market import MarketDataError, market

try:
    result = market({"user_input": "What is the latest available price for META?"})
    print(result)
except MarketDataError as exc:
    print(f"Market lookup failed: {exc}")