import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packaging"))
import safe_diagnostics as d


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/"data").mkdir();self.previous=d.ROOT;d.ROOT=self.root
        self.flag=self.root/"data/safe-diagnostics.enabled.json"
        self.log=self.root/"data/safe-diagnostics.jsonl"
    def tearDown(self):d.ROOT=self.previous;self.temp.cleanup()
    def enable(self):self.flag.write_text(json.dumps({"expires":time.time()+3600}))

    def test_disabled_by_default_expiry_and_immediate_off(self):
        d.emit("plugin.enter");self.assertFalse(self.log.exists())
        self.enable();d.emit("plugin.enter");self.assertTrue(self.log.exists())
        before=self.log.read_bytes()
        self.flag.write_text(json.dumps({"expires":time.time()-1}));d.emit("plugin.enter")
        self.assertEqual(self.log.read_bytes(),before)
        self.flag.unlink();d.emit("plugin.enter");self.assertEqual(self.log.read_bytes(),before)

    def test_messages_credentials_identity_and_error_text_are_never_fields(self):
        self.enable()
        secret="fixture-secret-identity-and-chat"
        error=ValueError(secret)
        d.emit(secret,error=error)
        event=type("Fixture",(),{"get_extra":lambda self,key:secret})()
        d.emit("model.failed",error=error,event=event)
        data=self.log.read_text(encoding="utf-8")
        self.assertNotIn(secret,data)
        self.assertEqual(set(json.loads(data)),{"time","code","error"})
        self.assertIn("configuration",data)

    def test_timeout_network_rate_limit_classification(self):
        self.assertEqual(d.error_code(TimeoutError("private")),"timeout")
        self.assertEqual(d.error_code(ConnectionError("private")),"network")
        error=RuntimeError("private");error.status_code=429
        self.assertEqual(d.error_code(error),"http_429")
        error_type=type("ForbiddenError",(RuntimeError,),{"__module__":"botpy.errors"})
        error=error_type("private server response; credentials and member identity")
        self.assertEqual(d.error_code(error),"qq_forbidden")


if __name__=="__main__":unittest.main()
