#!/usr/bin/env python3
"""
Financial market data generator
Simulates stock market tick data using geometric Brownian motion
"""
import random
import time
import json
import math

class StockSimulator:
    """Simulate stock price movement using geometric Brownian motion"""

    def __init__(self, symbol, initial_price=100.0, volatility=0.02, drift=0.0001):
        """
        Args:
            symbol: Stock ticker symbol
            initial_price: Starting price
            volatility: Price volatility (standard deviation)
            drift: Trend direction (positive = upward, negative = downward)
        """
        self.symbol = symbol
        self.price = initial_price
        self.volatility = volatility
        self.drift = drift
        self.daily_high = initial_price
        self.daily_low = initial_price
        self.daily_volume = 0

    def next_price(self):
        """Generate next price using geometric Brownian motion"""
        # GBM: S(t+1) = S(t) * exp((drift - 0.5*volatility^2)*dt + volatility*sqrt(dt)*Z)
        # Simplified version for demonstration
        dt = 1  # Time step
        random_shock = random.gauss(0, 1)

        price_change = self.drift * self.price * dt + \
                      self.volatility * self.price * math.sqrt(dt) * random_shock

        self.price += price_change

        # Ensure price stays positive
        if self.price < 1.0:
            self.price = 1.0

        # Update daily metrics
        self.daily_high = max(self.daily_high, self.price)
        self.daily_low = min(self.daily_low, self.price)

        return self.price

def generate_market_data(symbols=None, ticks_per_second=10):
    """
    Generate realistic stock market tick data

    Args:
        symbols: List of stock symbols to simulate
        ticks_per_second: Number of ticks per second per symbol
    """
    if symbols is None:
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]

    # Create simulators with different characteristics
    simulators = {
        "AAPL": StockSimulator("AAPL", 178.0, 0.015, 0.0001),
        "GOOGL": StockSimulator("GOOGL", 141.0, 0.018, 0.00005),
        "MSFT": StockSimulator("MSFT", 378.0, 0.016, 0.00008),
        "AMZN": StockSimulator("AMZN", 146.0, 0.020, 0.00003),
        "TSLA": StockSimulator("TSLA", 242.0, 0.035, -0.00002),  # Higher volatility
        "NVDA": StockSimulator("NVDA", 496.0, 0.025, 0.00015),
        "META": StockSimulator("META", 328.0, 0.022, 0.00006),
        "NFLX": StockSimulator("NFLX", 367.0, 0.024, -0.00001),
    }

    # Filter to requested symbols
    simulators = {s: simulators[s] for s in symbols if s in simulators}

    tick_count = 0

    while True:
        for symbol, sim in simulators.items():
            price = sim.next_price()
            spread = price * 0.0005  # 0.05% spread (realistic for liquid stocks)

            # Volume varies realistically
            base_volume = random.randint(100, 1000)
            if tick_count % 100 < 10:  # Spike at market open/close
                base_volume *= random.randint(5, 10)

            tick = {
                "timestamp": int(time.time() * 1000),
                "symbol": symbol,
                "price": round(price, 2),
                "bid": round(price - spread/2, 2),
                "ask": round(price + spread/2, 2),
                "volume": base_volume,
                "daily_high": round(sim.daily_high, 2),
                "daily_low": round(sim.daily_low, 2),
                "exchange": "NASDAQ"
            }

            sim.daily_volume += base_volume
            tick["daily_volume"] = sim.daily_volume

            yield tick

        tick_count += 1
        time.sleep(1.0 / ticks_per_second)

if __name__ == "__main__":
    print("# Financial Market Data Generator")
    print("# Generating stock tick data... (Ctrl+C to stop)")
    print()

    try:
        for tick in generate_market_data(ticks_per_second=5):
            # Format nicely for display
            print(f"{tick['symbol']:6s} ${tick['price']:7.2f} "
                  f"(bid: ${tick['bid']:7.2f}, ask: ${tick['ask']:7.2f}) "
                  f"vol: {tick['volume']:,}")
    except KeyboardInterrupt:
        print("\nStopped.")
