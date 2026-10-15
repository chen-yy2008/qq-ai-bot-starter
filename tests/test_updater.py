import copy
import io
import json
import socket
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packaging"))
import updater as u


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name).resolve()
        self.app=self.root/"程序文件"
        self.install(self.app)
        self.private={"data/cmd_config.json":b'{"dashboard":{"port":6185},"provider":["fixture-key"],"platform":["fixture-secret"],"admins_id":["fixture-admin"]}',"data/config/qq_ai_lab_config.json":b'fixture-group-list',"data/plugins/astrbot_plugin_qq_ai_lab/personas/毒舌损友.json":b'custom-persona',"data/plugin_data/qq_ai_lab/state.db":b'private-db-fixture',"data/plugins/other/main.py":b'other-plugin'}
        for name,data in self.private.items():
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        with socket.socket() as free:
            free.bind(("127.0.0.1",0));self.port=free.getsockname()[1]
        config=self.root/"data/cmd_config.json"
        value=json.loads(config.read_bytes());value["dashboard"]["port"]=self.port
        config.write_text(json.dumps(value),encoding="utf-8")
        self.private["data/cmd_config.json"]=config.read_bytes()
        self.payload={("plugin","main.py"):b'new plugin',("app","updater.py"):b'new updater',("root","检查并更新.bat"):b'new root entry'}
        self.archive,self.manifest=self.package(self.payload)
        self.starts=0;self.stops=0

    def tearDown(self):self.temp.cleanup()

    def install(self,app):
        for path,content in ((app/"runtime/python.exe",b'fixture'),(app/"framework/main.py",b'fixture'),(app/"framework/astrbot/__init__.py",b'__version__ = "4.29.0"'),(self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py",b'old plugin')):
            path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(content)

    def package(self,payload):
        data=io.BytesIO()
        with zipfile.ZipFile(data,"w",zipfile.ZIP_DEFLATED) as z:
            for (target,path),body in payload.items():z.writestr(f"payload/{target}/{path}",body)
        archive=data.getvalue()
        return archive,{"schema":1,"framework":"4.29.0","version":"1.0.0","release_tag":u.CHANNEL,"sequence":1,"package":{"name":u.ASSET,"size":len(archive),"sha256":u.digest(archive)},"files":[{"target":t,"path":p,"sha256":u.digest(b)} for (t,p),b in payload.items()],"changes":["fixture update"]}

    def start(self,*args):self.starts+=1
    def stop(self,*args):self.stops+=1

    def apply(self,**kwargs):
        return u.apply_update(self.root,self.app,self.manifest,u.unpack(self.archive,self.manifest),is_running=lambda *a:False,stop=self.stop,start=kwargs.pop("start",self.start),**kwargs)

    def preserved(self):
        for name,data in self.private.items():self.assertEqual((self.root/name).read_bytes(),data,name)

    def test_update_success_preserves_all_user_files_bytes(self):
        self.assertEqual(u.layout(self.root),(self.root,self.app))
        backup=self.apply()
        self.assertEqual((self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").read_bytes(),b'new plugin')
        self.assertEqual(json.loads((backup/"transaction.json").read_text(encoding="utf-8"))["state"],"committed")
        self.assertEqual(self.starts,1);self.preserved()

    def test_legacy_layout_without_program_folder(self):
        # A separate legacy install, no synthetic deletion/migration of user data.
        self.root=self.root/"legacy";self.root.mkdir();self.app=self.root;self.install(self.app)
        (self.root/"data/cmd_config.json").write_text(json.dumps({"dashboard":{"port":self.port}}))
        self.assertEqual(u.layout(self.root),(self.root,self.root))
        self.apply();self.assertEqual((self.root/"updater.py").read_bytes(),b'new updater')

    def test_write_failure_restores_old_and_removes_only_new_program_files(self):
        original=self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py"
        def failed(path,data):
            u.atomic_write(path,data)
            if path.name=="updater.py":raise OSError("fixture write failure")
        with self.assertRaisesRegex(u.UpdateError,"已校验并恢复"):self.apply(replace=failed)
        self.assertEqual(original.read_bytes(),b'old plugin')
        self.assertFalse((self.app/"updater.py").exists());self.preserved()

    def test_restart_failure_rolls_back_receipt_and_program(self):
        receipt=self.root/"data/qqbot-update.json";receipt.write_bytes(b'{"sequence":0}')
        def fail(*args):raise u.UpdateError("fixture startup failure")
        with self.assertRaisesRegex(u.UpdateError,"已校验并恢复"):self.apply(start=fail)
        self.assertEqual(receipt.read_bytes(),b'{"sequence":0}')
        self.assertEqual((self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").read_bytes(),b'old plugin');self.preserved()

    def test_ctrl_c_during_copy_rolls_back(self):
        def fail(path,data):u.atomic_write(path,data);raise KeyboardInterrupt()
        with self.assertRaisesRegex(u.UpdateError,"已校验并恢复"):self.apply(replace=fail)
        self.assertEqual((self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").read_bytes(),b'old plugin');self.preserved()

    def test_download_interrupted_and_wrong_hash_leave_program_unchanged(self):
        import urllib.error
        with patch.object(u.urllib.request,"build_opener",side_effect=urllib.error.URLError("fixture")):
            with self.assertRaisesRegex(u.UpdateError,"网络"):u.download("https://github.com/fixture",100)
        with self.assertRaises(u.UpdateError):u.unpack(self.archive[:-10],self.manifest)
        changed=copy.deepcopy(self.manifest);changed["files"][0]["sha256"]="0"*64
        with self.assertRaises(u.UpdateError):u.unpack(self.archive,changed)
        self.assertEqual((self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py").read_bytes(),b'old plugin');self.preserved()

    def test_reject_wrong_framework_and_unsafe_manifest_paths(self):
        (self.app/"framework/astrbot/__init__.py").write_text('__version__ = "4.30.0"')
        with self.assertRaisesRegex(u.UpdateError,"版本不匹配"):u.layout(self.root)
        for target,path in (("plugin","personas/毒舌损友.json"),("root","data/cmd_config.json"),("plugin","../main.py"),("app","framework/main.py"),("plugin","main.py.")):
            m=copy.deepcopy(self.manifest);m["files"][0].update(target=target,path=path)
            with self.assertRaises(u.UpdateError):u.validate_manifest(m)
        self.preserved()

    def test_public_release_requires_real_asset_digest_and_exact_repo(self):
        meta=json.dumps(self.manifest).encode()
        prefix=f"https://github.com/{u.REPO}/releases/download/{u.CHANNEL}/"
        release={"tag_name":u.CHANNEL,"draft":False,"prerelease":False,"assets":[{"name":u.METADATA,"browser_download_url":prefix+u.METADATA,"digest":"sha256:"+u.digest(meta)},{"name":u.ASSET,"browser_download_url":prefix+u.ASSET,"digest":"sha256:"+u.digest(self.archive),"size":len(self.archive)}]}
        def fetch(url,limit,expected=None):
            if url==u.API:return json.dumps(release).encode()
            self.assertEqual(expected,u.digest(meta));return meta
        self.assertEqual(u.get_release(fetch)[0],self.manifest)
        for key,value in (("draft",True),("prerelease",True),("tag_name","v1.0.0-rc.1")):
            old=release[key];release[key]=value
            with self.assertRaises(u.UpdateError):u.get_release(fetch)
            release[key]=old
        release["assets"][1]["browser_download_url"]="https://example.org/unknown.zip"
        with self.assertRaises(u.UpdateError):u.get_release(fetch)
        for url in ("http://github.com/file","https://github.com.evil.test/file","https://name:pass@github.com/file","https://github.com:444/file"):
            self.assertFalse(u.trusted_url(url))

    def test_anonymous_api_limit_fallback_still_verifies_source_and_files(self):
        seen=[]
        prefix=f"https://github.com/{u.REPO}/releases/download/{u.CHANNEL}/"
        def fetch(url,limit,expected=None):
            seen.append(url)
            if url==u.API:raise u.UpdateError("fixture public quota",code=403)
            self.assertEqual(url,prefix+u.METADATA)
            return json.dumps(self.manifest).encode()
        manifest,url=u.get_release(fetch)
        self.assertEqual(url,prefix+u.ASSET)
        self.assertEqual(u.unpack(self.archive,manifest),self.payload)
        with self.assertRaises(u.UpdateError):u.unpack(self.archive[:-1],manifest)
        self.assertEqual(seen,[u.API,prefix+u.METADATA])

    def test_cannot_restore_is_explicit_and_stops_further_work(self):
        atomic=u.atomic_write
        old_plugin=self.root/"data/plugins/astrbot_plugin_qq_ai_lab/main.py"
        def fail(path,data):
            atomic(path,data)
            raise OSError("fixture")
        def unavailable_restore(path,data):
            if path==old_plugin and data==b'old plugin':raise OSError("restore permission fixture")
            atomic(path,data)
        with patch.object(u,"atomic_write",side_effect=unavailable_restore):
            with self.assertRaisesRegex(u.UpdateError,"无法自动完整恢复"):self.apply(replace=fail)
        transaction=next((self.root/"data/update-backups").glob("*/transaction.json"))
        self.assertEqual(json.loads(transaction.read_text(encoding="utf-8"))["state"],"manual_recovery_required")
        with self.assertRaisesRegex(u.UpdateError,"上次更新中断"):self.apply()
        self.preserved()


if __name__=="__main__":unittest.main()
