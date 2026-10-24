"""IR transformation passes and framework for cpp2py."""

from cpp2py.transforms.log import TransformRecord, TransformLog
from cpp2py.transforms.manager import (
    IRRewriter,
    IRPass,
    PassContext,
    run_pipeline,
)
from cpp2py.transforms.constant_fold import ConstantFoldPass
from cpp2py.transforms.dead_temps import DeadTempsPass

__all__ = [
    "TransformRecord",
    "TransformLog",
    "IRRewriter",
    "IRPass",
    "PassContext",
    "run_pipeline",
    "ConstantFoldPass",
    "DeadTempsPass",
]
