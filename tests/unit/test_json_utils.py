from astrbot.core.utils.json_utils import json_loads_no_bom


def test_json_loads_no_bom_accepts_leading_utf8_bom():
    assert json_loads_no_bom('\ufeff[{"role": "user", "content": "hello"}]') == [
        {"role": "user", "content": "hello"}
    ]
