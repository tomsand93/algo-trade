"""Copy-trade policies for pmirror.

Policies determine when and how much to trade when copying a target wallet.
"""

from pmirror.policies.base import CopyPolicy, PolicyContext, PolicyResult
from pmirror.policies.mirror_latency import MirrorLatencyPolicy
from pmirror.policies.position_rebalance import PositionRebalancePolicy
from pmirror.policies.fixed_allocation import FixedAllocationPolicy

__all__ = [
    "CopyPolicy",
    "PolicyContext",
    "PolicyResult",
    "MirrorLatencyPolicy",
    "PositionRebalancePolicy",
    "FixedAllocationPolicy",
]
