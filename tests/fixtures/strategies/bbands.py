from backtesting import Strategy
import pandas as pd
import ta


class Strategy_BBands(Strategy):
    period = 20
    std = 2.0

    def init(self):
        close = pd.Series(self.data.Close)
        bb = ta.volatility.BollingerBands(close, self.period, self.std)
        self.upper = self.I(lambda: bb.bollinger_hband().values)
        self.lower = self.I(lambda: bb.bollinger_lband().values)

    def next(self):
        if not self.position and self.data.Close[-1] < self.lower[-1]:
            self.buy()
        elif self.position and self.data.Close[-1] > self.upper[-1]:
            self.position.close()
