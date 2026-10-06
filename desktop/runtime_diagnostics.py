"""Explicit developer diagnostics; failures go to JSON, never a crash dialog."""
import json
from pathlib import Path
import secrets
import tempfile


def run(root, app, output, *, check_mtp=False, bridge_factory=None):
    report = {'status': 'running', 'phase': 'gui',
              'mtp': {'status': 'not_requested'}}
    try:
        root.update_idletasks()
        report.update(gui_created=True, buttons=len(app.buttons))
        report['phase'] = 'qr'
        import cv2, zxingcpp
        from vault_qr import render_qr
        from vault_color import ColorFrame, packet, decode_color_image
        from cryptography.hazmat.primitives.asymmetric import ec
        from types import SimpleNamespace
        qr_test = render_qr('C71 Vault bundled QR runtime test', 320, 320)
        assert zxingcpp.read_barcode(qr_test).text == 'C71 Vault bundled QR runtime test'
        report['qr_roundtrip'] = True
        color_client = SimpleNamespace(private=ec.generate_private_key(ec.SECP256R1()), client_id='a'*64)
        color_packet = packet(color_client, 'b'*32, 'c'*32, 1, 1, bytes(range(256))*4)
        assert decode_color_image(render_qr(ColorFrame(color_packet), 630, 630)) == color_packet
        report.update(four_color_binary_roundtrip=True, opencv_loaded=cv2.__version__)
        report['phase'] = 'encrypted_roundtrip'
        from vault_crypto import pack, restore
        with tempfile.TemporaryDirectory(prefix='c71-exe-test-') as directory:
            d = Path(directory)
            src = d/'source'
            src.mkdir()
            (src/'試験.txt').write_text('復元検証', encoding='utf-8')
            key = secrets.token_bytes(32)
            pack(src, d/'test.c71b', key)
            restore(d/'test.c71b', d/'restored', key)
            assert (d/'restored'/'試験.txt').read_text(encoding='utf-8') == '復元検証'
        report['encrypted_roundtrip'] = True
        if check_mtp:
            report['phase'] = 'mtp'
            report['mtp'] = {'status': 'running'}
            if bridge_factory is None:
                from vault_transport import MtpBridge
                bridge_factory = MtpBridge
            bridge = bridge_factory()
            info = json.loads(bridge.read('device.json', max_bytes=16384))
            report['mtp'] = {'status': 'passed', 'device': bridge.name,
                             'device_fingerprint': info['fingerprint']}
        report.update(status='passed', phase='complete')
    except Exception as error:
        report.update(status='failed', error_type=type(error).__name__, error=str(error))
        if report['phase'] == 'mtp':report['mtp'] = {'status': 'failed'}
    finally:
        app.close()
    # An invalid diagnostic output path is also a controlled failure.
    try:
        Path(output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        return 2
    return 0 if report['status'] == 'passed' else 1
