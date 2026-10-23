import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher_check', ROOT/'windows/inspect_lcp_launcher.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LauncherTests(unittest.TestCase):
    def test_retains_start_structure_without_executing_or_disclosing_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'support').mkdir()
            (root/'LCP-background.vbs').write_text('shell.Run "SECRET_VBS account.py", 0, True\n')
            (root/'support/account.py').write_text('''import os, runpy
from pathlib import Path
# SECRET_COMMENT
password = "SECRET_PASSWORD"
blob = b"SECRET_BYTES"
number = 12345678901
key = f"SECRET_FSTRING{password}"
os.environ['LCP_EMAIL'] = password
worker = Path(__file__).with_name('upstream_worker.py')
Path('MUST_NOT_BE_CREATED').write_text('executed')
runpy.run_path(str(worker), run_name='__main__')
raise RuntimeError('SECRET_ERROR')
''')
            output = module.inspect_launcher(root)
            for secret in ('SECRET_', '12345678901', 'MUST_NOT_BE_CREATED'):
                self.assertNotIn(secret, output)
            for evidence in ('Gebruikt Run: True', 'account.py', 'upstream_worker.py', 'runpy.run_path', 'LCP_EMAIL'):
                self.assertIn(evidence, output)
            self.assertFalse((root/'MUST_NOT_BE_CREATED').exists())

    def test_syntax_error_never_discloses_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/'support').mkdir()
            (root/'support/account.py').write_text('password = "SECRET_BROKEN')
            output = module.inspect_launcher(root)
            self.assertNotIn('SECRET_BROKEN', output)
            self.assertIn('kon niet worden gelezen', output)


if __name__ == '__main__':
    unittest.main()
