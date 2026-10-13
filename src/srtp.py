"""SRTP recruitment form validation and Beijing-time deadline."""
from datetime import datetime
import re
from src.storage import CHINA_TIME

CLOSE_AT = datetime(2026, 10, 16, 22, 0, tzinfo=CHINA_TIME)
FIELDS = {"name": (1, 30), "student_id": (1, 30), "college": (1, 80), "major": (1, 80), "introduction": (1, 2000)}

def now():
    return datetime.now(CHINA_TIME)

def valid_application(data, directions):
    for field, (minimum, maximum) in FIELDS.items():
        value = data.get(field, "")
        if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
            return False
        if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
            return False
    if not re.fullmatch(r"[0-9]{1,30}", data.get("student_id", "")):
        return False
    return data.get("campus") in {"A", "B", "C", "D"} and data.get("join_vision") in {"是", "否"} and data.get("grade") == "2026级" and bool(data.get("directions")) and set(data["directions"]) <= set(directions)
