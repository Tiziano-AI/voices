import re

from voices.util.timestamps import utc_now, utc_now_compact


def test_utc_now_format():
    ts = utc_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)


def test_utc_now_compact_format():
    ts = utc_now_compact()
    assert re.fullmatch(r"\d{8}T\d{6}Z", ts)
