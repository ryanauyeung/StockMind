"""Next-session trade cards. Long/short only if the model beat baseline OOS."""

from __future__ import annotations

from typing import Protocol

from datetime import datetime, timezone

import numpy as np
import pandas as pd

from stockmind.config import (
    ARTIFACT_DIR,
    FADE_MIN_ATR,
    CLOSE_GATE_FAMILIES,
    RECENT_CLOSE_MAE_MAX,
    RECENT_CLOSE_MAE_SOFT,
    RECENT_ERROR_MIN_N,
    RECENT_ERROR_WINDOW,
    SHOW_TOP_N,
    MAE_RANK_W_CLOSE,
    MAE_RANK_W_HIGH,
    MAE_RANK_W_LOW,
    recent_close_error_path,
)
from stockmind.range_touch import FadeSetup, choose_setup
from stockmind.models.baseline import BaselineModel
from stockmind.models.families import SectorBundle, SharedBundle, StockBundle, pred_col
from stockmind.models.lightgbm_quantile import QuantileLGBM
from stockmind.universe import load_sp500, rank_by_dollar_volume

# LOAD_FROM:/workspace/stockmind-rename/branch_files/src/stockmind/cards.py
# TRUNCATED_ON_PURPOSE_SHOULD_BE_REPLACED
