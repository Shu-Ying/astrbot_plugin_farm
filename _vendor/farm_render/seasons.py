"""按北京时间选择四季主题；蜂巢主题只供显式离线预览。"""

from datetime import datetime, timedelta, timezone

from ..farm_core.domain import integer

BEIJING = timezone(timedelta(hours=8))


def season_for(now: int) -> str:
    month = datetime.fromtimestamp(integer(now), BEIJING).month
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"
