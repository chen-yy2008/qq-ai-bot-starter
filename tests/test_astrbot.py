"""Actual pinned AstrBot types + HTTP transport stub, never real credentials."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE=os.environ.get("ASTRBOT_SOURCE")
if SOURCE: sys.path.insert(0,SOURCE)
AVAILABLE=bool(SOURCE and importlib.util.find_spec("astrbot"))

if AVAILABLE:
    import httpx
    from openai import AsyncOpenAI
    from astrbot.core.platform.astrbot_message import AstrBotMessage,MessageMember,Group
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.message_type import MessageType
    from astrbot.api.message_components import Plain
    from plugin.main import QQLab
    from plugin.core import ProviderConfigError, friendly_error

    class ActualEvent(AstrMessageEvent):
        async def send(self,chain): pass


@unittest.skipUnless(AVAILABLE,"Set ASTRBOT_SOURCE to pinned v4.29.0 source for integration tests")
class AstrBotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.requests=[]
        self.code=200
        async def handler(request):
            self.requests.append(json.loads(request.content))
            if self.code!=200:
                return httpx.Response(self.code,json={"error":{"message":"local fixture error","type":"test"}})
            return httpx.Response(200,json={"id":"local-fixture","object":"chat.completion","created":0,"model":"deepseek-flash","choices":[{"index":0,"message":{"role":"assistant","content":"离线传输桩"},"finish_reason":"stop"}],"usage":{"prompt_tokens":7,"completion_tokens":3,"total_tokens":10}})
        self.client=AsyncOpenAI(api_key="local-test-fixture",base_url="https://api.deepseek.com",http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        provider=SimpleNamespace(client=self.client,get_model=lambda:"deepseek-flash")
        context=SimpleNamespace(get_provider_by_id=lambda _:provider)
        conf=json.loads((Path(__file__).resolve().parents[1]/"config/plugin.example.json").read_text(encoding="utf-8"))
        conf.update(provider_id="local-fixture",allowed_groups=["group-fixture"])
        with patch("plugin.main.get_astrbot_data_path",return_value=self.temp.name):
            self.plugin=QQLab(context,conf)

    async def asyncTearDown(self):
        await self.plugin.terminate()
        await self.client.close()
        self.temp.cleanup()

    def event(self,text,admin=False,group="group-fixture",sender="user-fixture",bot=False):
        m=AstrBotMessage()
        m.type=MessageType.GROUP_MESSAGE
        m.group=Group(group)
        m.sender=MessageMember(sender,"离线夹具")
        m.self_id="bot-fixture"
        m.message_id=text+str(admin)+sender
        m.message=[Plain(text)]
        m.raw_message=SimpleNamespace(author=SimpleNamespace(bot=bot))
        event=ActualEvent(text,m,PlatformMetadata("qq_official","fixture","adapter-fixture"),group)
        event.role="admin" if admin else "member"
        event.is_at_or_wake_command=text.startswith("/")
        return event

    async def collect(self,event):
        results=[]
        async def send(chain):
            results.append(chain)
            event._has_send_oper=True
        with patch.object(event,"send",send):
            await self.plugin.on_group(event)
        return results

    async def test_native_event_permission_and_no_default_agent(self):
        denied=await self.collect(self.event("/启用群聊 已告知群友"))
        self.assertTrue(denied)
        self.assertEqual(self.requests,[])
        await self.collect(self.event("/启用群聊 已告知群友",admin=True))
        e=self.event("/emo 今天")
        results=await self.collect(e)
        self.assertTrue(results)
        self.assertTrue(e.is_stopped())
        self.assertTrue(e.call_llm)  # v4.29.0: True prohibits the default agent
        self.assertEqual(len(self.requests),1)
        body=self.requests[0]
        self.assertEqual(body["max_tokens"],256)
        self.assertEqual(body["model"],"deepseek-flash")
        self.assertEqual(body["thinking"],{"type":"disabled"})
        self.assertNotIn("tools",body)
        self.assertEqual(self.plugin.store.use(self.plugin.engine.day(),e.unified_msg_origin)[:3],(1,10,0))

    async def test_disallowed_group_and_bot_skip(self):
        await self.collect(self.event("/emo 今天",group="unlisted"))
        await self.collect(self.event("/emo 今天",sender="bot-fixture"))
        await self.collect(self.event("/emo 今天",bot=True))
        self.assertEqual(self.requests,[])

    async def test_actual_sdk_no_retry_on_429(self):
        self.code=429
        response=None
        try: await self.plugin.generate("system","prompt","",256)
        except Exception as e: response=e
        self.assertEqual(getattr(response,"status_code",None),429)
        self.assertEqual(len(self.requests),1)

    async def test_provider_source_is_not_a_model_instance_and_no_paid_call(self):
        self.plugin.context.get_provider_by_id=lambda value: None if value=="deepseek" else SimpleNamespace(client=self.client,get_model=lambda:"deepseek-flash")
        self.plugin.config["provider_id"]="deepseek"
        with self.assertRaises(ProviderConfigError) as caught:
            await self.plugin.generate("system","prompt","",256)
        message=friendly_error(caught.exception)
        self.assertIn("deepseek/deepseek-flash",message)
        self.assertIn("无需因此重填 Key",message)
        self.assertEqual(self.requests,[])
        self.plugin.config["provider_id"]="deepseek/deepseek-flash"
        await self.plugin.generate("system","prompt","",256)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(self.requests[0]["model"],"deepseek-flash")

    async def test_missing_provider_and_wrong_endpoint_are_distinct_local_errors(self):
        self.plugin.config["provider_id"]=""
        with self.assertRaises(ProviderConfigError) as caught:
            await self.plugin.generate("system","prompt","",256)
        self.assertIn("尚未选择模型",friendly_error(caught.exception))
        self.plugin.config["provider_id"]="fixture"
        self.plugin.context.get_provider_by_id=lambda _:SimpleNamespace(client=None)
        with self.assertRaises(ProviderConfigError) as caught:
            await self.plugin.generate("system","prompt","https://fixture.invalid/image",256)
        self.assertIn("模型地址或类型",friendly_error(caught.exception))
        self.assertEqual(self.requests,[])

    async def test_actual_sdk_server_failure_has_service_hint_and_no_retry(self):
        self.code=503
        with self.assertRaises(Exception) as caught:
            await self.plugin.generate("system","prompt","",256)
        self.assertIn("服务端暂时故障",friendly_error(caught.exception))
        self.assertIn("无需因此修改",friendly_error(caught.exception))
        self.assertEqual(len(self.requests),1)

    async def test_original_slash_after_framework_wake_prefix_stripping(self):
        e=self.event("/启用群聊 已告知群友",admin=True)
        e.message_str="启用群聊 已告知群友"
        result=await self.collect(e)
        self.assertTrue(result)
        self.assertTrue(self.plugin.store.state(e.unified_msg_origin)["authorized"])
        e=self.event("/自检")
        e.message_str="自检"
        await self.collect(e)
        self.assertEqual(len(self.requests),1)

    async def test_image_unavailable_text_fallback(self):
        async def missing(url): raise ValueError("fixture")
        with patch("plugin.main.prepare_image",missing):
            response=await self.plugin.generate("system","prompt","https://example.com/missing",256)
        self.assertIn("按文字处理",response.text)
        content=self.requests[0]["messages"][1]["content"]
        self.assertEqual([x["type"] for x in content],["text"])

    async def test_native_private_logging(self):
        import logging
        from packaging import version  # ordinary upstream dependency import
        self.assertIsNotNone(version)
        spec=importlib.util.spec_from_file_location("launcher_privacy",Path(__file__).resolve().parents[1]/"packaging/launch.py")
        launcher=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(launcher)
        original=logging.getLogRecordFactory()
        try:
            launcher.install_private_logging()
            record=logging.getLogRecordFactory()("fixture",40,"C:/private/test.py",1,"password=private fixture chat",(),None)
            self.assertNotIn("private",record.getMessage())
            self.assertEqual(record.pathname,"framework")
            self.assertIsNone(record.exc_info)
        finally: logging.setLogRecordFactory(original)


if __name__=="__main__": unittest.main()
