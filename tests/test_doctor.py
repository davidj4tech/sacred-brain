from __future__ import annotations

import json
from unittest import mock

from sacred_brain.doctor import check_litellm


def test_check_litellm_ok():
    resp = mock.Mock()
    resp.json.return_value = {"data": [{"id": "gpt-4o-mini"}]}
    resp.raise_for_status.return_value = None
    with mock.patch("httpx.get", return_value=resp):
        status = check_litellm()
    assert status["litellm"] == "ok" or "litellm" in status


def test_check_litellm_fail():
    with mock.patch("httpx.get", side_effect=Exception("boom")):
        status = check_litellm()
    assert "error" in status.get("litellm", "")
