"""Training poll definition; all deadlines use Beijing time."""
from datetime import datetime, timedelta, timezone

CHINA_TIME = timezone(timedelta(hours=8))
POLL_ID = "vision-training-202610"
POLL_TITLE = "Gsing视觉组实训培训时间"
# Accept votes through the entire 23:59 minute on October 10.
POLL_CLOSE = datetime(2026, 10, 11, 0, 0, tzinfo=CHINA_TIME)
POLL_OPTIONS = [
    ("1011-am", "10 月 11 日 · 上午"),
    ("1011-pm", "10 月 11 日 · 下午"),
    ("1012-pm", "10 月 12 日 · 下午"),
    ("1012-evening", "10 月 12 日 · 晚上"),
    ("1013-evening", "10 月 13 日 · 晚上"),
    ("1015-pm", "10 月 15 日 · 下午"),
    ("1016-pm", "10 月 16 日 · 下午"),
    ("1017-pm", "10 月 17 日 · 下午"),
    ("1017-evening", "10 月 17 日 · 晚上"),
]

def china_now():
    return datetime.now(CHINA_TIME)

POLLS = {
    "vision-training": {"id": POLL_ID, "title": POLL_TITLE, "requires_team": True},
    "vision-freshman-training": {"id": "freshman-training-202610", "title": "Gsing视觉组新生考核培训", "requires_team": False},
}
