"""Intraday fade: touch predicted High/Low, take profit at prior close.

High-win-rate setup. Fade side is the High/Low side with more room back to
prior close. For sector/stock, Close q50 must agree with that side
(+10bps long / -10bps short) or the card flattens — Close cannot flip the side.
Paper ledger uses RTH 5-minute bars (``fill_fade_bars``) and only opens if the
trigger prints before 12:30 America/New_York. Daily OHLC ``fill_fade`` remains
the walk-forward simulator. Conservative fill: if stop and target both print
in the same bar, stop wins. If the trigger fills but neither TP nor SL prints,
flatten at the last bar close (same-day book; no overnight). Skip if the
session open gapped through the trigger.
"""
