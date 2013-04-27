# coding: utf8

# part of pybacktest package: https://github.com/ematvey/pybacktest

import pandas
import IPython
import pyquant
import pylab
import parts
import performance
import datetime
import time

from cached_property import cached_property

__all__ = ['Backtest']


class Backtest(object):
    '''
    Backtest (Pandas implementation of vectorized backtesting).

    Lazily attemts to extract multiple pandas.Series with signals and prices
    from a given namespace and combine them into equity curve.

    Attempts to be as smart as possible.

    '''

    _ohlc_possible_fields = ('ohlc', 'bars', 'ohlcv')
    _sig_mask_int = ('Buy', 'Sell', 'Short', 'Cover')
    _pr_mask_int = ('BuyPrice', 'SellPrice', 'ShortPrice', 'CoverPrice')

    def __init__(self, dataobj, name='Unknown',
                 signal_fields=('buy', 'sell', 'short', 'cover'),
                 price_fields=('buyprice', 'sellprice', 'shortprice',
                               'coverprice')):
        '''
        Arguments:

        *dataobj* should be dict-like structure containing signal series.
        Easiest way to define is to create pandas.Series with exit and entry
        signals and pass whole local namespace (`locals()`) as dataobj.

        *name* is simply backtest/strategy name. Will be user for printing,
        potting, etc.

        *signal_fields* specifies names of signal Series that backtester will
        attempt to extract from dataobj. By default follows AmiBroker's naming
        convention.

        *price_fields* specifies names of price Series where trades will take
        place. If some price is not specified (NaN at signal's timestamp, or
        corresponding Series not present in dataobj altogather), defaults to
        Open price of next bar. By default follows AmiBroker's naming
        convention.

        Also, dataobj should contain dataframe with Bars of underlying
        instrument. We will attempt to guess its name before failing miserably.

        To get a hang of it, check out the examples.

        '''
        self._dataobj = dict([(k.lower(), v) for k, v in dataobj.iteritems()])
        self._sig_mask_ext = signal_fields
        self._pr_mask_ext = price_fields
        self.name = name
        self.trdplot = self.sigplot = parts.Slicer(self.plot_trades,
                                                   obj=self.ohlc)
        self.eqplot = parts.Slicer(self.plot_equity, obj=self.ohlc)
        self.run_time = time.strftime('%Y-%d-%m %H:%M:%S %Z', time.localtime())

    def __repr__(self):
        return "Backtest('%s', %s)" % (self.name, self.run_time)

    @property
    def dataobj(self):
        return self._dataobj

    @cached_property(ttl=0)
    def signals(self):
        return parts.extract_frame(self.dataobj, bool, self._sig_mask_ext,
                                   self._sig_mask_int)

    @cached_property(ttl=0)
    def prices(self):
        return parts.extract_frame(self.dataobj, float, self._pr_mask_ext,
                                   self._pr_mask_int)

    @cached_property(ttl=0)
    def default_price(self):
        return self.ohlc.O.shift(-1)

    @cached_property(ttl=0)
    def trade_price(self):
        pr = self.prices
        if pr is None:
            return self.ohlc.O.shift(-1)
        dp = pandas.Series(dtype=float, index=pr.index)
        for pf, sf in zip(self._pr_mask_int, self._sig_mask_int):
            s = self.signals[sf]
            p = self.prices[pf]
            dp[s] = p[s]
        return dp.combine_first(self.default_price)

    @cached_property(ttl=0)
    def positions(self):
        return parts.signals_to_positions(self.signals,
                                          mask=self._sig_mask_int)

    @cached_property(ttl=0)
    def trades(self):
        t = pandas.DataFrame({'pos': self.positions})
        t['price'] = self.trade_price
        t = t.dropna()
        t['vol'] = t.pos.diff()
        return t

    @cached_property(ttl=0)
    def equity(self):
        return parts.trades_to_equity(self.trades)

    @cached_property(ttl=0)
    def ohlc(self):
        for possible_name in self._ohlc_possible_fields:
            s = self.dataobj.get(possible_name)
            if not s is None:
                return s
        raise Exception("Bars dataframe was not found in dataobj")

    @cached_property(ttl=0)
    def report(self):
        return performance.performance_summary(self.equity)

    def summary(self):
        import yaml
        print '%s performance summary\n' % self
        print yaml.dump(self.report, allow_unicode=True,
                        default_flow_style=False)

    def plot_equity(self, subset=None):
        if subset is None:
            subset = slice(None, None)
        assert isinstance(subset, slice)
        eq = self.equity[subset].cumsum()
        eq.plot(color='red', label='strategy')
        ix = self.ohlc.ix[eq.index[0]:eq.index[-1]].index
        price = self.ohlc.C
        (price[ix] - price[ix][0]).plot(color='black', alpha=0.5,
                                        label='underlying')
        pylab.legend(loc='upper left')
        pylab.title('%s\nEquity' % self)

    def plot_trades(self, subset=None):
        if subset is None:
            subset = slice(None, None)
        self.ohlc.C.ix[subset].plot(color='black', label='price')
        fr = self.trades.ix[subset]
        le = fr.price[(fr.pos > 0) & (fr.vol > 0)]
        se = fr.price[(fr.pos < 0) & (fr.vol < 0)]
        lx = fr.price[(fr.pos.shift() > 0) & (fr.vol < 0)]
        sx = fr.price[(fr.pos.shift() < 0) & (fr.vol > 0)]
        pylab.plot(le.index, le.values, '^', color='lime', markersize=12,
                   label='long enter')
        pylab.plot(se.index, se.values, 'v', color='red', markersize=12,
                   label='short enter')
        pylab.plot(lx.index, lx.values, 'o', color='lime', markersize=7,
                   label='long exit')
        pylab.plot(sx.index, sx.values, 'o', color='red', markersize=7,
                   label='short exit')
        eq = self.equity.ix[subset].cumsum()
        (eq + self.ohlc.C[eq.index[0]]).plot(color='red', style='-')
        pylab.title('%s\nTrades for %s' % (self, subset))