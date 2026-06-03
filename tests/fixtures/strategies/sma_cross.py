from backtesting import Strategy
from backtesting.lib import crossover
import pandas as pd
import numpy as np
import ta


class Strategy_SmaCross(Strategy):
    fast = 10
    slow = 30

    def init(self):
        close = pd.Series(self.data.Close)
        self.sma_f = self.I(lambda c, p: c.rolling(p).mean(), close, self.fast)
        self.sma_s = self.I(lambda c, p: c.rolling(p).mean(), close, self.slow)

    def next(self):
        if crossover(self.sma_f, self.sma_s):
            self.buy()
        elif crossover(self.sma_s, self.sma_f):
            self.position.close()
