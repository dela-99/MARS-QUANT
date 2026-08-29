from __future__ import annotations
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class TemporalSplit:
    train_idx: pd.Index
    validation_idx: pd.Index
    test_idx: pd.Index
    embargo: int = 0

    def assert_no_overlap(self) -> None:
        a,b,c = set(self.train_idx), set(self.validation_idx), set(self.test_idx)
        if a & b or a & c or b & c: raise ValueError("temporal split overlap detected")
        if len(self.train_idx) and len(self.validation_idx) and self.train_idx.max() >= self.validation_idx.min(): raise ValueError("train must precede validation")
        if len(self.validation_idx) and len(self.test_idx) and self.validation_idx.max() >= self.test_idx.min(): raise ValueError("validation must precede test")

class TemporalSplitter:
    def __init__(self, train_ratio=.7, validation_ratio=.15, test_ratio=.15, embargo:int=0):
        total=train_ratio+validation_ratio+test_ratio
        if abs(total-1)>1e-9: raise ValueError("split ratios must sum to 1")
        self.train_ratio=train_ratio; self.validation_ratio=validation_ratio; self.test_ratio=test_ratio; self.embargo=embargo
    def split(self, index: pd.Index) -> TemporalSplit:
        n=len(index)
        if n < 10: raise ValueError("at least 10 rows required")
        n_train=int(n*self.train_ratio); n_val=int(n*self.validation_ratio)
        tr_end=max(0,n_train-self.embargo); val_start=min(n,n_train+self.embargo); val_end=max(val_start,n_train+n_val-self.embargo); test_start=min(n,n_train+n_val+self.embargo)
        split=TemporalSplit(index[:tr_end], index[val_start:val_end], index[test_start:], self.embargo)
        split.assert_no_overlap(); return split
