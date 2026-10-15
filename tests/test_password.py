import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PACKAGING=Path(__file__).resolve().parents[1]/"packaging"
sys.path.insert(0,str(PACKAGING))
import panel_password as password
from bundle_paths import locations
from entrypoints import ENTRIES

FIXTURE="LocalFixtureAa12345"


def verify_hash(value,candidate):
    _,iterations,salt,digest=value.split("$")
    return hashlib.pbkdf2_hmac("sha256",candidate.encode(),bytes.fromhex(salt),int(iterations)).hex()==digest


class PasswordTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        (self.root/"data").mkdir()
        with socket.socket() as free:
            free.bind(("127.0.0.1",0));self.port=free.getsockname()[1]
        bootstrap=patch.dict(password.BOOTSTRAP["dashboard"],port=self.port)
        bootstrap.start();self.addCleanup(bootstrap.stop)
        self.path=self.root/"data/cmd_config.json"
        self.conf={"dashboard":{"username":"custom-owner","host":"127.0.0.1","port":6185,"password":"old-hash","pbkdf2_password":"","password_change_required":True,"jwt_secret":"old-jwt","totp":{"enable":True,"secret":"test-totp-retained"},"auth_rate_limit":{"enable":True}},"platform":[{"type":"qq_official","secret":"fixture-qq-retained"}],"provider":[{"key":["fixture-provider-retained"]}],"unknown_field":{"preserve":True}}
        self.conf["dashboard"]["port"]=self.port
        self.original=json.dumps(self.conf,ensure_ascii=False,indent=3).encode()
        self.path.write_bytes(self.original)
        self.notices=[]
        self.ask=lambda *args:(FIXTURE,FIXTURE)
        self.inform=lambda *args,**kwargs:self.notices.append(args)

    def tearDown(self): self.temp.cleanup()

    def reset(self):
        with patch.object(password,"check_stopped"):
            return password.ensure_password(self.root,PACKAGING,reset=True,ask=self.ask,inform=self.inform)

    def test_reset_preserves_every_non_auth_field_and_user_data(self):
        for relative in ("data/qq-client.cfg","data/plugins/fixture/main.py","data/chats.db"):
            p=self.root/relative; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(b"retain exact fixture bytes")
        before={str(p.relative_to(self.root)):p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        updated=self.reset()
        old,new=copy.deepcopy(self.conf),copy.deepcopy(updated)
        for field in password.AUTH_FIELDS:
            old["dashboard"].pop(field,None); new["dashboard"].pop(field,None)
        self.assertEqual(old,new)
        for relative,content in before.items():
            if Path(relative)!=Path("data/cmd_config.json"): self.assertEqual((self.root/relative).read_bytes(),content)
        self.assertTrue(verify_hash(updated["dashboard"]["pbkdf2_password"],FIXTURE))
        self.assertNotEqual(updated["dashboard"]["jwt_secret"],"old-jwt")
        self.assertFalse(updated["dashboard"]["password_change_required"])
        self.assertIn("custom-owner",self.notices[-1][1])
        self.assertIn(f"127.0.0.1:{self.port}",self.notices[-1][1])
        for p in (self.path,self.root/"data/panel-password.initialized.json"):
            self.assertNotIn(FIXTURE.encode(),p.read_bytes())

    def test_cancel_leaves_original_bytes(self):
        def cancelled(*args): raise password.Cancelled()
        with patch.object(password,"check_stopped"),self.assertRaises(password.Cancelled):
            password.ensure_password(self.root,PACKAGING,reset=True,ask=cancelled,inform=self.inform)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_invalid_confirmation_and_complexity_leave_original(self):
        for first,second in [(FIXTURE,"DifferentFixtureA123"),("short1A","short1A"),("lowercase12345","lowercase12345")]:
            with self.subTest(case=len(first)),self.assertRaises(password.PasswordError):
                password.save_password(self.root,self.conf,self.original,first,second)
            self.assertEqual(self.path.read_bytes(),self.original)

    def test_config_replace_failure_leaves_original_bytes_and_no_temp_files(self):
        original_replace=os.replace
        def failing(src,dst):
            if Path(dst)==self.path: raise PermissionError("fixture failure")
            return original_replace(src,dst)
        with patch.object(password.os,"replace",side_effect=failing),patch.object(password,"check_stopped"),self.assertRaises(PermissionError):
            self.reset()
        self.assertEqual(self.path.read_bytes(),self.original)
        self.assertFalse(password.initialized(self.root,self.conf))
        self.assertFalse(list((self.root/"data").glob(".panel-*.tmp")))

    def test_receipt_failure_precedes_config_replacement(self):
        with patch.object(password.os,"replace",side_effect=OSError("fixture")),patch.object(password,"check_stopped"),self.assertRaises(OSError): self.reset()
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_changed_config_not_overwritten(self):
        modified=self.original+b"\n"
        self.path.write_bytes(modified)
        with self.assertRaises(password.PasswordError):
            password.save_password(self.root,self.conf,self.original,FIXTURE,FIXTURE,stopped=lambda _:None)
        self.assertEqual(self.path.read_bytes(),modified)

    def test_invalid_json_no_dialog_or_write(self):
        bad=b'{"dashboard": broken'
        self.path.write_bytes(bad)
        ask=unittest.mock.Mock()
        with self.assertRaises(password.PasswordError): password.ensure_password(self.root,PACKAGING,ask=ask)
        ask.assert_not_called()
        self.assertEqual(self.path.read_bytes(),bad)

    def test_existing_config_and_test_residue_without_receipt_require_gui(self):
        asked=[]
        def ask(*args): asked.append(args); return FIXTURE,FIXTURE
        with patch.object(password,"check_stopped"):
            password.ensure_password(self.root,PACKAGING,ask=ask,inform=self.inform)
        self.assertEqual(len(asked),1)
        self.assertEqual(asked[0][1],"setup")

    def test_inherited_password_and_reset_env_cannot_bypass_gui(self):
        with patch.dict(os.environ,{"ASTRBOT_DASHBOARD_INITIAL_PASSWORD":"UnwantedFixtureA123","ASTRBOT_RESET_DASHBOARD_PASSWORD":"1"}):
            self.reset()
            self.assertNotIn("ASTRBOT_DASHBOARD_INITIAL_PASSWORD",os.environ)
            self.assertNotIn("ASTRBOT_RESET_DASHBOARD_PASSWORD",os.environ)
        self.assertTrue(verify_hash(json.loads(self.path.read_text())["dashboard"]["pbkdf2_password"],FIXTURE))

    def test_restart_and_native_webui_password_change_do_not_prompt_again(self):
        conf=self.reset()
        ask=unittest.mock.Mock(side_effect=AssertionError("Should not ask"))
        password.ensure_password(self.root,PACKAGING,ask=ask)
        conf["dashboard"]["pbkdf2_password"]="pbkdf2_sha256$600000$"+"12"*16+"$"+"34"*32
        self.path.write_text(json.dumps(conf),encoding="utf-8")
        password.ensure_password(self.root,PACKAGING,ask=ask)
        ask.assert_not_called()

    def test_first_setup_without_framework_or_dependencies(self):
        self.path.unlink()
        with patch.object(password,"check_stopped"):
            conf=password.ensure_password(self.root,PACKAGING,ask=self.ask,inform=self.inform)
        self.assertEqual(conf["dashboard"]["username"],"astrbot")
        self.assertEqual(conf["dashboard"]["host"],"127.0.0.1")
        self.assertTrue(password.initialized(self.root,conf))

    def test_corrupt_hash_does_not_suppress_setup(self):
        conf=self.reset()
        conf["dashboard"]["pbkdf2_password"]="pbkdf2_sha256$broken"
        self.assertFalse(password.initialized(self.root,conf))

    def test_no_secret_in_dialog_cli_or_environment(self):
        result=subprocess.CompletedProcess([],0,json.dumps({"password":FIXTURE,"confirmation":FIXTURE}).encode(),b"")
        with patch.object(password.subprocess,"run",return_value=result) as run:
            self.assertEqual(password.dialog(PACKAGING,"reset","astrbot","http://127.0.0.1:6185"),(FIXTURE,FIXTURE))
        args,kwargs=run.call_args
        self.assertNotIn(FIXTURE," ".join(args[0]))
        self.assertNotIn(FIXTURE,kwargs["input"].decode())
        self.assertNotIn("env",kwargs)
        self.assertTrue(kwargs["capture_output"])

    def test_bundle_lock_prevents_parallel_reset(self):
        with password.BundleLock(self.root):
            with self.assertRaises(password.PasswordError):
                with password.BundleLock(self.root): pass

    def test_port_conflict_blocks_password_change_before_dialog(self):
        with socket.socket() as server:
            server.bind(("127.0.0.1",0)); server.listen()
            conf=copy.deepcopy(self.conf); conf["dashboard"]["port"]=server.getsockname()[1]
            with self.assertRaises(password.PasswordError): password.check_stopped(conf)

    def test_configured_port_check_does_not_probe_another_installation_default(self):
        with patch.object(password.socket,"socket") as socket_factory:
            password.check_stopped(self.conf)
        socket_factory.return_value.__enter__.return_value.bind.assert_called_once_with(("127.0.0.1",self.port))

    def test_top_level_entries_and_layout_compatibility(self):
        for name in ("启动机器人.bat","打开管理面板.bat","停止机器人.bat","重置管理密码.bat","首次使用.html"):
            self.assertIn(name,ENTRIES)
        self.assertEqual(locations(self.root/"程序文件/launch.py"),(self.root,self.root/"程序文件"))
        self.assertEqual(locations(self.root/"launch.py"),(self.root,self.root))

    def test_launcher_initializes_before_any_astrbot_import(self):
        spec=importlib.util.spec_from_file_location("launch_initialization_test",PACKAGING/"launch.py")
        launch=importlib.util.module_from_spec(spec); spec.loader.exec_module(launch)
        class StopHere(Exception): pass
        with patch.object(launch,"ROOT",self.root),patch.object(launch,"APP",PACKAGING),patch.object(launch,"ensure_password",side_effect=StopHere) as ensure,patch.object(launch,"install_private_logging") as logging:
            with self.assertRaises(StopHere): launch.main()
        ensure.assert_called_once()
        logging.assert_not_called()
        self.assertEqual(self.path.read_bytes(),self.original)


@unittest.skipUnless(os.name=="nt","Windows WinForms controls")
class NativeWindowTests(unittest.TestCase):
    def test_real_controls_mask_independent_eyes_and_validation(self):
        process=subprocess.run(["powershell.exe","-NoLogo","-NoProfile","-STA","-ExecutionPolicy","Bypass","-File",str(PACKAGING/"password_dialog.ps1"),"-Mode","selftest"],capture_output=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stderr.decode(errors="replace"))
        self.assertEqual(json.loads(process.stdout)["controls"],"passed")


if __name__=="__main__": unittest.main()
