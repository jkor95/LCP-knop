"""Controle van de beveiligde GitHub Actions-route, zonder echte credentials."""
import base64
import importlib.util
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import supabase_inspect as inspect

class InspectionTests(unittest.TestCase):
    def test_missing_secret_stops_before_network_access(self):
        with patch.dict('os.environ',{'SUPABASE_ACCESS_TOKEN':''}), patch.object(inspect,'request') as request:
            with self.assertRaisesRegex(inspect.InspectError,'GitHub Actions-geheim'):
                inspect.main()
            request.assert_not_called()

    def test_management_errors_do_not_expose_token_or_response(self):
        token='dummy-test-token-not-a-real-secret'
        error=urllib.error.HTTPError(inspect.API+'/functions',401,'Unauthorized',{},io.BytesIO(token.encode()))
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect=error
            with self.assertRaises(inspect.InspectError) as result:
                inspect.request(token,'/functions')
        self.assertIn('HTTP 401',str(result.exception))
        self.assertNotIn(token,str(result.exception))

    def test_inspection_is_read_only_and_discards_secret_digests(self):
        calls=[]
        def request(token,path,payload=None):
            calls.append((path,payload))
            if path=='/database/query':return b'[{"audit":{}}]'
            if path=='/functions':return b'[{"slug":"lcp-push"},{"slug":"other"}]'
            if path=='/secrets':return b'[{"name":"VAPID_PRIVATE_KEY","value":"must-not-be-retained"}]'
            if path=='/functions/lcp-push/body':return b'// private server source'
            raise AssertionError(path)
        with patch.object(inspect,'request',request):
            report=inspect.collect('dummy')
        self.assertEqual(report['secret_names'],['VAPID_PRIVATE_KEY'])
        self.assertNotIn('must-not-be-retained',json.dumps(report))
        queries=[payload['query'] for path,payload in calls if payload is not None]
        self.assertEqual(len(queries),1)
        self.assertTrue(queries[0].strip().lower().startswith('select '))
        self.assertFalse(any(word in queries[0].lower() for word in ['insert into','update public','delete from','alter table','create table']))
        self.assertEqual(set(report['sources']),{'lcp-push'})

    def test_redirects_are_not_followed_with_management_credentials(self):
        self.assertIsNone(inspect.NoRedirect().redirect_request(None,None,302,'Found',{},'https://other.example/'))
        for path in ['https://other.example/','/../other']:
            with self.assertRaises(inspect.InspectError):inspect.request('dummy',path)

    @unittest.skipUnless(importlib.util.find_spec('cryptography'),'Versleuteling vereist cryptography')
    def test_only_private_key_can_open_the_report_and_tampering_fails(self):
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives import hashes,serialization
        from cryptography.hazmat.primitives.asymmetric import rsa,padding
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        public=private.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo)
        report={'project':inspect.PROJECT,'source':'private-source-placeholder'}
        envelope=inspect.encrypt_report(report,public)
        self.assertNotIn(report['source'],json.dumps(envelope))
        decode=base64.b64decode
        key=private.decrypt(decode(envelope['key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
        aad=('LCP-Supabase-inspectie-v1:'+inspect.PROJECT).encode()
        ciphertext=decode(envelope['ciphertext']);nonce=decode(envelope['nonce'])
        self.assertEqual(json.loads(AESGCM(key).decrypt(nonce,ciphertext,aad)),report)
        with self.assertRaises(InvalidTag):AESGCM(key).decrypt(nonce,ciphertext[:-1]+bytes([ciphertext[-1]^1]),aad)


class DeploymentSafetyTests(unittest.TestCase):
    def test_unreviewed_server_source_never_produces_bindings(self):
        import supabase_apply
        with self.assertRaisesRegex(inspect.InspectError,'veranderd'):
            supabase_apply.legacy_bindings('webpush.setVapidDetails("a","b","c");')

    def test_entry_source_uses_the_original_sourcemap(self):
        import supabase_apply
        source='import webpush from "npm:web-push"; Deno.serve(handler);'
        raw=b'ESZIP'+json.dumps({'version':3,'sources':['source/index.ts'],'sourcesContent':[source]},separators=(',',':')).encode()+b'\x00'
        self.assertEqual(supabase_apply.entry_source(raw),source)


    def test_repeated_activation_reuses_existing_bindings_without_reading_keys(self):
        import supabase_apply
        import tempfile
        from contextlib import redirect_stdout
        source=Path('supabase/functions/lcp-push-dispatch/index.ts').read_text()
        raw=json.dumps({'version':3,'sources':['source/index.ts'],'sourcesContent':[source]},separators=(',',':')).encode()
        calls=[]
        def request(token,path,payload=None):
            calls.append((path,payload))
            if path.endswith('/body'):return raw
            if path=='/secrets':return json.dumps([{'name':name} for name in ['VAPID_SUBJECT','VAPID_PUBLIC_KEY','VAPID_PRIVATE_KEY','LCP_PUSH_WEBHOOK_TOKEN']]).encode()
            if path=='/database/query':return b'[]'
            raise AssertionError(path)
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ',{'RUNNER_TEMP':directory}), patch.object(supabase_apply,'request',request), redirect_stdout(io.StringIO()):
            supabase_apply.prepare('dummy')
            self.assertIsNone(json.loads((Path(directory)/'lcp-deployment-private.json').read_text()))
        self.assertFalse(any(path=='/secrets' and payload is not None for path,payload in calls))

if __name__=='__main__':unittest.main()
