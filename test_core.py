import base64
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import ssl
import socket
import core

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aB1cAAAAASUVORK5CYII=')
CFG = core.DEFAULTS | {'token': 'test-not-a-real-token'}

class CoreTests(unittest.TestCase):
    def test_dpapi_round_trip_and_no_plaintext_storage(self):
        with tempfile.TemporaryDirectory(dir='.') as folder, patch.object(core, 'APP_DIR', Path(folder)):
            core.save_config(CFG)
            text = (Path(folder) / 'settings.json').read_text()
            self.assertNotIn(CFG['token'], text)
            self.assertEqual(core.load_config(), CFG)
    def test_upload_payload_and_commit_pinned_link(self):
        response = io.StringIO('{"commit":{"sha":"abc123"}}')
        with patch.object(core, 'urlopen', return_value=response) as request:
            record = core.upload(CFG, 'a [test].png', PNG)
        req = request.call_args.args[0]
        import json
        payload = json.loads(req.data)
        self.assertEqual(base64.b64decode(payload['content']), PNG)
        self.assertEqual(payload['branch'], 'main')
        self.assertIn('/abc123/images/', record['url'])
        self.assertTrue(record['markdown'].endswith('(' + record['url'] + ')'))
        self.assertEqual(req.get_header('Authorization'), 'Bearer ' + CFG['token'])
    def test_unsupported_and_oversize(self):
        for data in [b'', b'not an image', b'a' * (core.MAX_BYTES + 1)]:
            with self.assertRaises(ValueError): core.upload(CFG, 'x.png', data)
    def test_unique_paths(self):
        with patch.object(core, 'api', return_value={'commit': {'sha': '123'}}):
            a = core.upload(CFG, 'x.png', PNG)
            b = core.upload(CFG, 'x.png', PNG)
        self.assertNotEqual(a['path'], b['path'])
    def test_auth_error_does_not_leak_token(self):
        with patch.object(core, 'urlopen', side_effect=HTTPError('', 401, '', {}, None)):
            with self.assertRaisesRegex(ValueError, 'Token 无效'):
                core.upload(CFG, 'x.png', PNG)
    def test_private_repo_rejected(self):
        with patch.object(core, 'api', return_value={'private': True}):
            with self.assertRaisesRegex(ValueError, '公开仓库'): core.check_connection(CFG)
    def test_traversal_rejected(self):
        with self.assertRaises(ValueError): core.validate_config(CFG | {'folder': '../oops'})
    def test_network_errors_are_actionable_without_secrets(self):
        cases = [(FileNotFoundError(), '组件文件缺失'),
                 (URLError(ssl.SSLCertVerificationError()), '证书验证失败'),
                 (URLError(socket.gaierror()), '无法解析'),
                 (URLError(ConnectionRefusedError()), '连接被拒绝'),
                 (URLError(TimeoutError()), '超时')]
        for error, text in cases:
            with self.subTest(text=text), patch.object(core, 'urlopen', side_effect=error):
                with self.assertRaisesRegex(ValueError, text) as caught:
                    core.upload(CFG, 'x.png', PNG)
                self.assertNotIn(CFG['token'], str(caught.exception))

if __name__ == '__main__': unittest.main()
