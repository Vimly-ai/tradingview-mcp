from backtesting import Strategy
import pandas as pd
import ta


class Strategy_Rsi(Strategy):
    rsi_period = 14
    oversold = 30
    overbought = 70

    def init(self):
        close = pd.Series(self.data.Close)
        self.rsi = self.I(
            lambda c, p: ta.momentum.RSIIndicator(c, p).rsi(),
            close, self.rsi_period,
        )

    def next(self):
        if not self.position and self.rsi[-1] < self.oversold:
            self.buy()
        elif self.position and self.rsi[-1] > self.overbought:
            self.position.close()
