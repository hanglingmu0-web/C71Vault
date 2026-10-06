"""Diagnostics must work offline and record connection failures without raising."""
import json
from pathlib import Path
import sys
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'desktop'))
from runtime_diagnostics import run


def test_default_runtime_test_does_not_access_usb(tmp_path):
    root = Mock()
    app = Mock(buttons=[])
    bridge = Mock(side_effect=AssertionError('USB must not be accessed'))
    output = tmp_path/'offline.json'
    assert run(root, app, output, bridge_factory=bridge) == 0
    bridge.assert_not_called()
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['status'] == 'passed'
    assert report['mtp']['status'] == 'not_requested'
    assert report['encrypted_roundtrip'] is True
    app.close.assert_called_once()


def test_requested_mtp_failure_is_reported_without_uncaught_exception(tmp_path):
    app = Mock(buttons=[])
    output = tmp_path/'unavailable.json'
    bridge = Mock(side_effect=RuntimeError('C71のUSB転送先が見つかりません'))
    assert run(Mock(), app, output, check_mtp=True, bridge_factory=bridge) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['status'] == 'failed'
    assert report['phase'] == 'mtp'
    assert report['mtp']['status'] == 'failed'
    assert report['error'] == 'C71のUSB転送先が見つかりません'
    assert report['encrypted_roundtrip'] is True
    app.close.assert_called_once()


def test_invalid_device_info_is_not_reported_as_success(tmp_path):
    output = tmp_path/'invalid-device.json'
    bridge = Mock()
    bridge.read.return_value = b'not json'
    app = Mock(buttons=[])
    assert run(Mock(), app, output, check_mtp=True, bridge_factory=lambda: bridge) == 1
    report = json.loads(output.read_text(encoding='utf-8'))
    assert report['status'] == 'failed'
    assert report['phase'] == 'mtp'
    assert report['error_type'] == 'JSONDecodeError'
    app.close.assert_called_once()
