import asyncio
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from plugin.core import Completion, Engine, Message, Store, friendly_error, plain
from plugin.images import encode_frame, validate_url, MAX_BYTES

ROOT=Path(__file__).resolve().parents[1]


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=Store(str(Path(self.temp.name)/"state.db"))
        self.now=1792036800.0  # daytime in Asia/Shanghai
        self.calls=[]
        async def model(*args):
            self.calls.append(args)
            return Completion("**这句梗有用**",30)
        self.model=model
        self.personas={p.stem:json.loads(p.read_text(encoding="utf-8")) for p in (ROOT/"personas").glob("*.json")}
        self.catalog=json.loads((ROOT/"plugin/catalog.json").read_text(encoding="utf-8"))
        self.engine=Engine(self.store,self.personas,self.catalog,model,dict(quiet_start=0,quiet_end=0),clock=lambda:self.now,rng=lambda:0)
        self.n=0

    async def asyncTearDown(self):
        self.store.close()
        self.temp.cleanup()

    async def send(self,text="",group="qq:GroupMessage:g1",user="u1",admin=False,**kwargs):
        self.n+=1
        return await self.engine.handle(Message(group,user,str(self.n),text,admin=admin,**kwargs))

    async def enable(self,group="qq:GroupMessage:g1"):
        await self.send("/启用群聊 已告知群友",group=group,admin=True)

    async def test_safe_defaults_and_no_api_for_ordinary_traffic(self):
        for i in range(200): await self.send("普通群消息",user=str(i%3))
        self.assertEqual(self.calls,[])
        self.assertEqual(len(self.engine.runtimes["qq:GroupMessage:g1"].context),0)
        self.assertFalse(self.store.state("qq:GroupMessage:g1")["authorized"])

    async def test_admin_and_notice_requirements(self):
        self.assertIn("管理员",await self.send("/启用群聊 已告知群友"))
        self.assertIn("先告知",await self.send("/启用群聊",admin=True))
        await self.enable()
        self.assertTrue(self.store.state("qq:GroupMessage:g1")["authorized"])
        for cmd in ("/人格 抽象串子","/主动 活跃","/记住 abc","/清空记忆","/图片 关闭","/闭嘴"):
            self.assertIn("管理员",await self.send(cmd))

    async def test_proactive_wrong_notice_argument_has_copyable_steps_and_keeps_consent(self):
        await self.enable()
        reply=await self.send("/主动 活跃 已告知群友",admin=True)
        self.assertIn("/上下文 开启 已告知群友",reply)
        self.assertIn("再发送 /主动 活跃",reply)
        state=self.store.state("qq:GroupMessage:g1")
        self.assertEqual(state["mode"],"安静")
        self.assertFalse(state["context"])
        reply=await self.send("/主动 活跃",admin=True)
        self.assertIn("上下文尚未开启",reply)
        self.assertFalse(self.store.state("qq:GroupMessage:g1")["context"])
        for n in range(6):await self.send("自然讨论",user="u"+str(n%2))
        self.assertEqual(self.calls,[])

    async def test_explicit_commands_and_four_personas(self):
        await self.enable()
        for persona in self.personas:
            await self.send("/人格 "+persona,admin=True)
            self.now+=30
            self.assertEqual("这句梗有用",await self.send("/吐槽 健身卡"))
            self.assertIn(self.personas[persona]["system_prompt"],self.calls[-1][0])
        self.assertEqual(len(self.calls),4)

    async def test_group_isolation_ttl_and_no_permanent_history(self):
        await self.enable()
        await self.send("/上下文 开启 已告知群友",admin=True)
        await self.send("只属于第一群")
        await self.enable("qq:GroupMessage:g2")
        await self.send("/emo 天气",group="qq:GroupMessage:g2")
        self.assertNotIn("只属于第一群",self.calls[-1][1])
        self.now+=601
        await self.send("/emo 风")
        self.assertNotIn("只属于第一群",self.calls[-1][1])
        self.assertNotIn("只属于第一群", "\n".join(self.store.db.iterdump()))

    async def test_context_size_and_sensitive_input(self):
        await self.enable()
        await self.send("/上下文 开启 已告知群友",admin=True)
        for i in range(100): await self.send("长"*1000)
        r=self.engine.runtimes["qq:GroupMessage:g1"]
        self.assertEqual(len(r.context),24)
        self.assertLessEqual(max(len(x[2]) for x in r.context),400)
        await self.send("api_key=private-placeholder-value")
        self.assertFalse(any("private-placeholder" in x[2] for x in r.context))

    async def test_memory_crud_privacy_restart_and_isolation(self):
        await self.enable()
        self.assertIn("未开启",await self.send("/记住 喜欢科幻",admin=True))
        await self.send("/长期记忆 开启 已告知群友",admin=True)
        await self.send("/记住 喜欢科幻",admin=True)
        self.assertIn("科幻",await self.send("/回忆 科幻"))
        self.assertEqual(self.store.memories("qq:GroupMessage:g2"),[])
        other=Store(str(Path(self.temp.name)/"state.db"))
        self.assertTrue(other.state("qq:GroupMessage:g1")["memory"])
        self.assertTrue(other.memories("qq:GroupMessage:g1"))
        other.close()
        await self.send("/退出记忆")
        self.assertEqual(self.store.memories("qq:GroupMessage:g1"),[])
        self.assertIn("退出",await self.send("/记住 abc",admin=True))
        await self.send("/恢复记忆")
        await self.send("/记住 new",admin=True)
        await self.send("/忘记 new",admin=True)
        self.assertEqual(self.store.memories("qq:GroupMessage:g1"),[])
        await self.send("/记住 next",admin=True)
        await self.send("/清空记忆",admin=True)
        self.assertEqual(self.store.memories("qq:GroupMessage:g1"),[])

    async def test_memory_limit_and_sensitive_rejection(self):
        await self.enable()
        await self.send("/长期记忆 开启 已告知群友",admin=True)
        self.assertIn("非敏感",await self.send("/记住 password=do-not-save-this",admin=True))
        for i in range(100): await self.send("/记住 条目"+str(i),admin=True)
        self.assertIn("上限",await self.send("/记住 extra",admin=True))

    async def test_dedup_and_bot_loop(self):
        await self.enable()
        m=Message("qq:GroupMessage:g1","u1","fixed","/emo 夜晚")
        await self.engine.handle(m)
        self.now+=30
        self.assertIsNone(await self.engine.handle(m))
        self.assertIsNone(await self.engine.handle(replace(m,event_id="bot",bot=True)))
        self.assertEqual(len(self.calls),1)

    async def test_usage_real_and_failure_reservation(self):
        await self.enable()
        await self.send("/emo 夜晚")
        self.assertEqual(self.store.use(self.engine.day(),"qq:GroupMessage:g1")[:3],(1,30,0))
        async def broken(*args): raise TimeoutError()
        self.engine.generate=broken
        self.now+=30
        self.assertIn("超时",await self.send("/emo 夜晚"))
        calls,tokens,estimated,_=self.store.use(self.engine.day(),"qq:GroupMessage:g1")
        self.assertEqual(calls,2)
        self.assertEqual(tokens-estimated,30)
        self.assertGreater(estimated,0)

    async def test_budgets_global_and_daily_rollover(self):
        await self.enable()
        self.engine.config["daily_calls"]=1
        await self.send("/emo 今天")
        self.now+=30
        self.assertIn("上限",await self.send("/emo 今天"))
        self.now+=86400
        self.assertEqual(await self.send("/emo 明天"),"这句梗有用")
        self.engine.config["global_daily_calls"]=1
        await self.enable("qq:GroupMessage:g2")
        self.assertIn("上限",await self.send("/emo 主题",group="qq:GroupMessage:g2"))

    async def test_cost_and_token_preflight(self):
        await self.enable()
        self.engine.config["daily_tokens"]=1
        self.assertIn("上限",await self.send("/emo 风"))
        self.engine.config["daily_tokens"]=60000
        self.engine.config["daily_cost"]=0.00001
        self.assertIn("上限",await self.send("/emo 风"))
        self.assertEqual(self.calls,[])

    async def test_proactive_candidate_once_per_turn_and_mute(self):
        await self.enable()
        await self.send("/上下文 开启 已告知群友",admin=True)
        await self.send("/主动 自然",admin=True)
        self.assertIsNone(await self.send("今天如何",user="a"))
        self.assertIsNone(await self.send("还行",user="b"))
        self.assertEqual(await self.send("挺有意思",user="a"),"这句梗有用")
        for i in range(10): self.assertIsNone(await self.send("接着聊",user=str(i%2)))
        self.assertEqual(len(self.calls),1)
        await self.send("/闭嘴",admin=True)
        self.now+=200
        for i in range(5): self.assertIsNone(await self.send("聊啥",user=str(i%2)))
        self.assertEqual(await self.send("/emo 安静"),"这句梗有用")

    async def test_inflight_mute_and_global_concurrency(self):
        await self.enable()
        start=asyncio.Event()
        finish=asyncio.Event()
        async def delayed(*args):
            start.set()
            await finish.wait()
            return Completion("迟到回复",10)
        self.engine.generate=delayed
        task=asyncio.create_task(self.send("/emo 主题"))
        await start.wait()
        self.assertIn("冷却",await self.send("/emo 第二条"))
        await self.send("/闭嘴",admin=True)
        finish.set()
        self.assertIsNone(await task)

    async def test_timeout_and_no_retries(self):
        await self.enable()
        self.engine.config["timeout"]=0.01
        async def hang(*args):
            self.calls.append(args)
            await asyncio.sleep(1)
        self.engine.generate=hang
        self.assertIn("超时",await self.send("/emo 夜晚"))
        self.assertEqual(len(self.calls),1)
        self.assertIn("退避",await self.send("/emo 夜晚"))

    async def test_recommendations_are_from_catalog_and_free(self):
        await self.enable()
        self.assertIn("周杰伦",await self.send("/推荐歌 治愈"))
        self.assertIn("贾德",await self.send("/推荐书 哲学"))
        self.assertEqual(self.calls,[])

    async def test_image_rate_limit_and_disable(self):
        await self.enable()
        await self.send("图片",mentioned=True,image="https://example.com/a.png")
        self.assertTrue(self.calls[-1][2])
        self.now+=30
        await self.send("图片",mentioned=True,image="https://example.com/a.png")
        self.assertFalse(self.calls[-1][2])
        self.now+=61
        await self.send("/图片 关闭",admin=True)
        await self.send("图片",mentioned=True,image="https://example.com/a.png")
        self.assertFalse(self.calls[-1][2])

    async def test_optout_blocks_context_and_roast(self):
        await self.enable()
        await self.send("/上下文 开启 已告知群友",admin=True)
        await self.send("/别吐槽我")
        await self.send("不要收集这句话")
        self.assertFalse(self.engine.runtimes["qq:GroupMessage:g1"].context)
        await self.send("/吐槽 一个观点")
        self.assertIn("禁止被吐槽",self.calls[-1][0])

    async def test_idle_context_purged_and_quiet_hours(self):
        await self.enable()
        await self.send("/上下文 开启 已告知群友",admin=True)
        await self.send("/主动 活跃",admin=True)
        self.engine.config.update(quiet_start=0,quiet_end=23)
        for i in range(5): await self.send("休息时不接话",user=str(i%2))
        self.assertEqual(self.calls,[])
        self.now+=601
        self.engine.purge()
        self.assertEqual(len(self.engine.runtimes["qq:GroupMessage:g1"].context),0)

    async def test_global_concurrency_no_queue_or_budget_spend(self):
        await self.enable()
        await self.enable("qq:GroupMessage:g2")
        self.engine.semaphore=asyncio.Semaphore(1)
        start,finish=asyncio.Event(),asyncio.Event()
        async def delayed(*args):
            start.set()
            await finish.wait()
            return Completion("ok",1)
        self.engine.generate=delayed
        task=asyncio.create_task(self.send("/emo 等待"))
        await start.wait()
        self.assertIn("繁忙",await self.send("/emo 另一个群",group="qq:GroupMessage:g2"))
        self.assertEqual(self.store.use(self.engine.day(),"qq:GroupMessage:g2")[0],0)
        finish.set()
        await task


class SecurityTests(unittest.TestCase):
    def test_image_ssrf(self):
        for url in ("http://example.com/a","https://127.0.0.1/a","https://[::1]/a","https://169.254.169.254/a","https://10.0.0.1/a","file:///secret","https://localhost/a","https://example.local/a","https://user:pass@example.com/a","https://example.com:8080/a"):
            with self.subTest(url=url),self.assertRaises(ValueError): validate_url(url)
        self.assertEqual(validate_url("https://example.com/a.png"),"example.com")

    def test_static_frame_and_byte_limit(self):
        from PIL import Image
        data=io.BytesIO()
        Image.new("RGB",(2,2)).save(data,"PNG")
        self.assertTrue(encode_frame(data.getvalue()).startswith("base64://"))
        with self.assertRaises(ValueError): encode_frame(b"x"*(MAX_BYTES+1))

    def test_format_and_errors_dont_leak(self):
        self.assertEqual(plain("**ok**"),"ok")
        self.assertNotIn("do-not-show",plain("password=do-not-show"))
        self.assertNotIn("private fixture secret",friendly_error(ValueError("private fixture secret")))


if __name__=="__main__": unittest.main()
