"""Pinned upstream parser, QQ event/send, filters, scheduler and all nine stages.

Only network I/O, persistent framework services and the default agent are stubs.
The custom plugin uses the real AsyncOpenAI SDK with an HTTP transport fixture.
This is NOT a live QQ or paid DeepSeek acceptance test.
"""
import copy
import functools
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import test_astrbot as support
AVAILABLE=support.AVAILABLE

if AVAILABLE:
    import botpy.message
    from astrbot.core.config.default import DEFAULT_CONFIG
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.pipeline.process_stage.stage import ProcessStage
    from astrbot.core.pipeline.process_stage.method.star_request import StarRequestSubStage
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
    from astrbot.core.star.star import star_map, StarMetadata
    from astrbot.core.star.star_handler import star_handlers_registry
    from astrbot.builtin_stars.builtin_commands.main import Main
    from astrbot.builtin_stars.builtin_commands.commands.help import HelpCommand


@unittest.skipUnless(AVAILABLE, "Requires pinned AstrBot source")
class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await support.AstrBotTests.asyncSetUp(self)
        self.sent=[]
        self.default_calls=0
        self.count=0
        self.patches=[]
        self.saved_handlers=[(h,h.handler,h.enabled) for h in star_handlers_registry]
        self.saved_map=star_map.copy()
        conf=copy.deepcopy(DEFAULT_CONFIG)
        conf["wake_prefix"]=["/"]
        conf["admins_id"]=["admin-fixture"]
        conf["platform_settings"].update(unique_session=False,enable_id_white_list=False,reply_with_mention=False,reply_with_quote=False)
        conf["platform_settings"]["rate_limit"]["count"]=0
        conf["platform_settings"]["segmented_reply"]["enable"]=False
        conf["provider_settings"]["enable"]=True
        conf["provider_tts_settings"]["enable"]=False
        context=SimpleNamespace(get_config=lambda:conf,conversation_manager=SimpleNamespace(),get_using_tts_provider_async=AsyncMock(return_value=None))
        builtin=Main(context)
        own="plugin.main"
        native=Main.__module__
        star_map[native]=StarMetadata(name="builtin_commands",reserved=True,activated=True)
        star_map[own].activated=True
        for h in star_handlers_registry:
            if h.handler_module_path in (own,native):
                instance=self.plugin if h.handler_module_path==own else builtin
                raw=h.handler.func if isinstance(h.handler,functools.partial) else h.handler
                h.handler=functools.partial(raw,instance)  # identical to PluginManager binding
                h.enabled=True
            else: h.enabled=False
        for target,value in (
            ("astrbot.core.star.session_plugin_manager.sp.get_async",AsyncMock(return_value={})),
            ("astrbot.core.star.session_llm_manager.SessionServiceManager.is_session_enabled",AsyncMock(return_value=True)),
            ("astrbot.core.platform.astr_message_event.Metric.upload",AsyncMock()),
            ("astrbot.builtin_stars.builtin_commands.commands.help.get_dashboard_version",AsyncMock(return_value="4.29.0")),
            ("astrbot.builtin_stars.builtin_commands.commands.help.command_management.list_commands",AsyncMock(return_value=[])),
        ):
            p=patch(target,value);p.start();self.patches.append(p)
        p=patch.object(HelpCommand,"_query_astrbot_notice",AsyncMock(return_value=""));p.start();self.patches.append(p)
        ctx=PipelineContext(conf,SimpleNamespace(context=context),"test",None)
        self.pipeline=PipelineScheduler(ctx)
        # All nine real stages, including real ProcessStage.process(). The
        # default agent only counts attempts; it must never run for owned input.
        from astrbot.core.pipeline.stage import registered_stages
        for cls in registered_stages:
            stage=cls()
            if isinstance(stage,ProcessStage):
                stage.ctx=ctx
                stage.star_request_sub_stage=StarRequestSubStage()
                await stage.star_request_sub_stage.initialize(ctx)
                async def default(event):
                    self.default_calls+=1
                    if False: yield
                stage.agent_sub_stage=SimpleNamespace(process=default)
            else: await stage.initialize(ctx)
            self.pipeline.stages.append(stage)

    async def asyncTearDown(self):
        for p in reversed(self.patches):p.stop()
        for h,handler,enabled in self.saved_handlers:h.handler=handler;h.enabled=enabled
        star_map.clear();star_map.update(self.saved_map)
        await support.AstrBotTests.asyncTearDown(self)

    async def incoming(self,text,group="unlisted",sender="user-fixture",at=False,private=False,bot=False,attachments=None):
        self.count+=1
        async def send(**payload):
            self.sent.append(payload)
            return {"id":"out-fixture"}
        async def http(route,**kwargs):return await send(**kwargs.get("json",{}))
        api=SimpleNamespace(post_group_message=send,post_c2c_message=send,_http=SimpleNamespace(request=http))
        data={"id":str(self.count),"content":text,"group_openid":group,"author":{"member_openid":sender,"user_openid":sender,"bot":bot},"attachments":attachments or []}
        cls=botpy.message.C2CMessage if private else botpy.message.GroupMessage
        source=cls(api,"fixture-event",data)
        source.author.bot=bot  # SDK GroupMessage._User omits this field
        kind=MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
        abm=await QQOfficialPlatformAdapter._parse_from_qqofficial(source,kind,force_group_mention=at)
        abm.session_id=sender if private else group
        event=QQOfficialMessageEvent(abm.message_str,abm,PlatformMetadata("qq_official","fixture","adapter-fixture"),abm.session_id,SimpleNamespace(api=api))
        event.set_extra("qqofficial_use_markdown",False)
        await self.pipeline.execute(event)
        return event

    async def test_pipeline_native_help_plugin_disabled_then_enabled(self):
        star_map["plugin.main"].activated=False
        await self.incoming("/help")
        self.assertEqual(len(self.sent),1)
        self.assertIn("AstrBot v4.29.0",str(self.sent[-1]))
        star_map["plugin.main"].activated=True
        await self.incoming("/help",at=True)
        self.assertEqual(len(self.sent),2)
        self.assertIn("AstrBot v4.29.0",str(self.sent[-1]))
        self.assertEqual(self.requests,[])

    async def test_pipeline_sid_and_private_help(self):
        await self.incoming("/sid")
        self.assertEqual(len(self.sent),1)
        self.assertIn("UID",str(self.sent[-1]))
        await self.incoming("/help",private=True)
        self.assertEqual(len(self.sent),2)
        self.assertIn("AstrBot v4.29.0",str(self.sent[-1]))

    async def test_pipeline_identity_before_auth_without_model(self):
        self.plugin.config["provider_id"]=""
        await self.incoming("/身份",at=True)
        self.assertEqual(len(self.sent),1)
        self.assertIn("unlisted",str(self.sent[-1]))
        self.assertIn("user-fixture",str(self.sent[-1]))
        self.assertEqual(self.requests,[])
        self.assertEqual(self.default_calls,0)
        self.assertEqual(self.plugin.engine.runtimes,{})

    async def test_pipeline_native_commands_in_authorized_group_never_call_model(self):
        await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
        for text in ("/help","/sid","/unknown-native"):
            await self.incoming(text,group="group-fixture",at=True)
        self.assertIn("AstrBot v4.29.0",str(self.sent))
        self.assertIn("UID",str(self.sent))
        self.assertEqual(self.requests,[])
        # Unknown commands are left to AstrBot; its default agent may run.
        self.assertEqual(self.default_calls,1)

    async def test_pipeline_other_plugin_observer_and_command(self):
        from astrbot.api.event import filter
        from astrbot.core.star.star_handler import EventType
        observers=[]
        class Other:
            @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE,priority=-20)
            async def observer(self,event):observers.append(True)
            @filter.command("fixture-command",priority=-20)
            async def command(self,event):return event.plain_result("other-plugin-ok")
            @filter.command("身份",priority=-20)
            async def identity(self,event):return event.plain_result("other-plugin-identity")
        handlers=star_handlers_registry.get_handlers_by_module_name(__name__)
        star_map[__name__]=StarMetadata(name="fixture-other",activated=True)
        try:
            for h in handlers:h.handler=functools.partial(h.handler,Other())
            await self.incoming("ordinary fixture",at=True)
            self.assertEqual(observers,[True])
            await self.incoming("/fixture-command",at=True)
            self.assertIn("other-plugin-ok",str(self.sent))
            await self.incoming("/身份",at=True)
            self.assertIn("other-plugin-identity",str(self.sent[-1]))
            await self.incoming("/毒舌身份",at=True)
            self.assertIn("本群 ID",str(self.sent[-1]))
            self.assertEqual(self.requests,[])
        finally:
            for h in handlers:star_handlers_registry.remove(h)

    async def test_pipeline_429_one_request_and_friendly_reply(self):
        self.code=429
        await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
        await self.incoming("/吐槽 fixture",group="group-fixture",at=True)
        self.assertEqual(len(self.requests),1)
        self.assertIn("限流",str(self.sent))
        self.assertEqual(self.default_calls,0)

    async def test_pipeline_bad_model_source_id_replies_with_instance_hint_without_api(self):
        self.plugin.config["provider_id"]="deepseek"
        self.plugin.context.get_provider_by_id=lambda _:None
        await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
        await self.incoming("/吐槽 fixture",group="group-fixture",at=True)
        self.assertEqual(len(self.sent),2)
        self.assertIn("deepseek/deepseek-flash",str(self.sent[-1]))
        self.assertEqual(self.requests,[])
        self.assertEqual(self.default_calls,0)

    async def test_pipeline_unlisted_plain_and_at_no_api_or_context(self):
        await self.incoming("fixture message")
        e=await self.incoming("fixture message",at=True)
        self.assertEqual(self.requests,[])
        self.assertEqual(self.default_calls,0)
        self.assertEqual(self.plugin.engine.runtimes,{})
        self.assertFalse(e.is_stopped())

    async def test_pipeline_authorization_help_and_single_sdk_request(self):
        await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
        self.assertIn("已授权",str(self.sent))
        await self.incoming("/帮助",group="group-fixture")
        self.assertEqual(len(self.sent),2)
        await self.incoming("/吐槽 fixture",group="group-fixture",at=True)
        self.assertEqual(len(self.requests),1)
        self.assertEqual(len(self.sent),3)
        self.assertIn("离线传输桩",str(self.sent[-1]))
        self.assertEqual(self.default_calls,0)

    async def test_pipeline_self_bot_does_not_identify_or_call_model(self):
        await self.incoming("/身份",sender="qq_official",bot=True)
        self.assertEqual(self.sent,[])
        self.assertEqual(self.requests,[])

    async def test_pipeline_image_original_url_survives_upstream_localization(self):
        from astrbot.core.pipeline.preprocess_stage.stage import PreProcessStage
        await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
        async def normalize(stage,event,component):component.url="C:/fixture/framework-temp.png"
        prepared=AsyncMock(return_value="base64://fixture-image-bytes")
        with patch.object(PreProcessStage,"_normalize_image_component",normalize),patch("plugin.main.prepare_image",prepared):
            await self.incoming("/吐槽 fixture image",group="group-fixture",at=True,attachments=[{"content_type":"image/png","url":"https://example.com/fixture.png"}])
        prepared.assert_awaited_once_with("https://example.com/fixture.png")
        self.assertEqual(len(self.requests),1)
        content=self.requests[0]["messages"][1]["content"]
        self.assertEqual([x["type"] for x in content],["text","image_url"])

    async def test_pipeline_safe_diagnostics_receipt_ignore_model_and_send_failure(self):
        import asyncio
        import json
        from pathlib import Path
        import sys
        import time
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"packaging"))
        import safe_diagnostics as d
        previous=d.ROOT
        methods=(QQOfficialPlatformAdapter.commit_event,PipelineScheduler.execute,QQOfficialMessageEvent.send)
        root=Path(self.temp.name)
        (root/"data").mkdir(exist_ok=True)
        (root/"data/safe-diagnostics.enabled.json").write_text(json.dumps({"expires":time.time()+3600}))
        with patch.dict(sys.modules,{"qqbot_safe_diagnostics":d}):
            try:
                d.install(root)
                e=await self.incoming("private fixture chat",at=True)
                adapter=QQOfficialPlatformAdapter.__new__(QQOfficialPlatformAdapter)
                adapter._event_queue=asyncio.Queue()
                adapter.commit_event(e)
                self.assertIs(adapter._event_queue.get_nowait(),e)
                # A send error must be distinguishable from model failure and
                # never cause an extra model request or raw exception reply.
                async def failed_send(*args,**kwargs):raise PermissionError("fixture-secret-raw-response")
                with patch.object(QQOfficialMessageEvent,"_post_send",failed_send):
                    await self.incoming("/身份",at=True)
                self.code=429
                await self.incoming("/启用群聊 已告知群友",group="group-fixture",sender="admin-fixture")
                await self.incoming("/吐槽 fixture",group="group-fixture",at=True)
                text=(root/"data/safe-diagnostics.jsonl").read_text(encoding="utf-8")
                codes={r["code"] for r in map(json.loads,text.splitlines())}
                self.assertTrue({"adapter.group.received","pipeline.begin","plugin.enter","plugin.ignore.unlisted","plugin.reply.ready","send.failed","plugin.reply.failed","model.failed"}<=codes)
                for private in ("private fixture chat","fixture-secret-raw-response","user-fixture","group-fixture","fixture-key"):
                    self.assertNotIn(private,text)
                self.assertIn("http_429",text)
                self.assertEqual(len(self.requests),1)
            finally:
                QQOfficialPlatformAdapter.commit_event,PipelineScheduler.execute,QQOfficialMessageEvent.send=methods
                d.ROOT=previous


if __name__=="__main__":unittest.main()
