"""AstrBot v4.29.0 adapter. Credentials stay in the existing framework WebUI."""
import asyncio
import json
from pathlib import Path

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .core import Completion, Engine, Message, Store
from .images import prepare_image


@register("qq_ai_lab", "chen-yy2008", "QQ 群聊四人格实验", "1.0.0")
class QQLab(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.context,self.config=context,config
        self.provider=None
        self.jobs=set()
        self.purge_task=None
        root=Path(__file__).parent
        resources=root if (root/"personas").exists() else root.parent
        personas={p.stem:json.loads(p.read_text(encoding="utf-8")) for p in (resources/"personas").glob("*.json")}
        data=Path(get_astrbot_data_path())/"plugin_data"/"qq_ai_lab"
        data.mkdir(parents=True,exist_ok=True)
        self.store=Store(str(data/"state.db"))
        names=("cooldown","daily_calls","daily_tokens","global_daily_calls","global_daily_tokens","daily_proactive","concurrency","timeout","quiet_start","quiet_end","token_price","daily_cost")
        settings={name:config[name] for name in names if name in config}
        self.engine=Engine(self.store,personas,json.loads((root/"catalog.json").read_text(encoding="utf-8")),self.generate,settings)

    async def initialize(self):
        async def purge_loop():
            while True:
                await asyncio.sleep(30)
                self.engine.purge()
        self.purge_task=asyncio.create_task(purge_loop())

    async def generate(self,system,prompt,image,max_output):
        provider=self.context.get_provider_by_id(self.config.get("provider_id",""))
        if not provider:
            raise ValueError("provider not configured")
        images=[]
        image_notice=""
        if image:
            try:
                images=[await prepare_image(image)]
            except Exception:
                prompt += "\n[图片读取失败；不要猜测图片内容，只依据文字回复。]"
                image_notice="图片读取失败，已按文字处理。\n"
        client=getattr(provider,"client",None)
        if client is None or getattr(client.base_url,"host","")!="api.deepseek.com" or client.base_url.scheme!="https":
            raise ValueError("Please select the official DeepSeek OpenAI-compatible provider")
        content=[{"type":"text","text":prompt}]
        for prepared in images:
            content.append({"type":"image_url","image_url":{"url":"data:image/jpeg;base64,"+prepared.removeprefix("base64://"),"detail":"low"}})
        try:
            # v4.29.0 text_chat ignores max_tokens kwargs and has an outer retry loop.
            # Reuse its configured AsyncOpenAI client, with isolated per-call limits.
            response=await client.with_options(max_retries=0,timeout=20).chat.completions.create(
                model=provider.get_model(),messages=[{"role":"system","content":system},{"role":"user","content":content}],
                max_tokens=max_output,extra_body={"thinking":{"type":"disabled"}},stream=False)
        except Exception as error:
            # No second paid request; next explicit text command remains available.
            if images and getattr(error,"status_code",None) in (400,404,422):
                return Completion("模型不支持本次图片请求。请关闭图片理解后发送文字，或在 WebUI 选择支持视觉的模型。")
            raise
        usage=getattr(response,"usage",None)
        return Completion(image_notice+(response.choices[0].message.content or ""),usage.total_tokens if usage and usage.total_tokens>0 else None)

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=100)
    async def on_group(self,event: AstrMessageEvent):
        if event.get_platform_name()!="qq_official":
            return
        event.should_call_llm(False)
        text=event.get_message_str().strip()
        # WakingCheckStage strips the configured '/' prefix from message_str.
        # The original Plain components retain it; commands must use that source.
        original="".join(x.text for x in event.get_messages() if isinstance(x,Plain)).strip()
        if original.startswith("/"):
            text=original
        group=str(event.get_group_id())
        if not group:
            event.stop_event()
            return
        if text=="/身份":
            yield event.plain_result("本群 ID："+group+"\n你的发送者 ID："+event.get_sender_id()+"\n仅将自己的 ID 填入本机 AstrBot 管理员列表，并把群 ID 填入插件 allowed_groups。")
            event.stop_event()
            return
        # Fail closed: another platform, private chat or unlisted group cannot spend.
        allowed=self.config.get("allowed_groups",[])[:128]
        if group not in allowed:
            if text in ("/状态","/帮助"):
                yield event.plain_result("本群未加入插件允许列表。先发送 /身份 获取配置所需 ID，在本机 WebUI 设置管理员和插件 allowed_groups，保存并重载后发送 /启用群聊 已告知群友。")
            event.stop_event()
            return
        images=[x for x in event.get_messages() if isinstance(x,Image)]
        image=str(getattr(images[0],"url","") or "") if images else ""
        raw=getattr(event.message_obj,"raw_message",None)
        author=raw.get("author",{}) if isinstance(raw,dict) else getattr(raw,"author",None)
        author_bot=author.get("bot",False) if isinstance(author,dict) else getattr(author,"bot",False)
        bot=event.get_sender_id()==event.get_self_id() or bool(author_bot) or event.get_sender_id() in self.config.get("ignored_bot_ids",[])
        m=Message(event.unified_msg_origin,event.get_sender_id(),str(event.message_obj.message_id or ""),text,bool(event.is_at_or_wake_command),event.is_admin(),bot,image)
        job=asyncio.current_task()
        self.jobs.add(job)
        try:
            reply=await self.engine.handle(m)
            if reply:
                yield event.plain_result(reply)
        except Exception:
            if text.startswith("/") or event.is_at_or_wake_command:
                yield event.plain_result("插件配置或数据异常，请运行本地自检。原始异常不会发送到群里。")
        finally:
            self.jobs.discard(job)
            event.stop_event()

    async def terminate(self):
        pending=[task for task in self.jobs if task is not asyncio.current_task()]
        if self.purge_task:
            pending.append(self.purge_task)
        for task in pending: task.cancel()
        if pending: await asyncio.gather(*pending,return_exceptions=True)
        self.store.close()
