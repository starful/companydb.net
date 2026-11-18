"""Shared anonymous visit log for Starful content sites (HQ「이용자 보기」).

No survey. Cookie vid · page views · clicks/CTA · referrer host · optional UTM.
"""

from .store import KEEP_DAYS, get_store
from .summarize import summarize
from .token import derive_hq_token, hq_token

__all__ = ["KEEP_DAYS", "derive_hq_token", "get_store", "hq_token", "summarize"]
