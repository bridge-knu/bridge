"""서비스 기준 시간. 사용자가 모두 한국에 있으므로 날짜는 한국 시간(KST, UTC+9) 기준이다.

서버(컨테이너) 시간대가 UTC여도 한국 날짜로 계산한다. 한국은 서머타임이 없어 +9시간 고정.
"""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9), "KST")


def today() -> date:
    return datetime.now(KST).date()
