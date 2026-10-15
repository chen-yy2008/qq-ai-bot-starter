"""AstrBot v4.29.0 adapter. Credentials stay in the existing framework WebUI."""
import asyncio
import json
from pathlib import Path

from astrbot.api import AstrBotConfig
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Plain
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .core import Completion, Engine, Message, Store, ProviderConfigError
from .images import prepare_image
from .diagnostics import report


COMMANDS=frozenset("身份 帮助 状态 人格 退出记忆 恢复记忆 别吐槽我 恢复吐槽 启用群聊 停用群聊 上下文 长期记忆 主动 开麦 闭嘴 安静 图片 记住 回忆 忘记 清空记忆 串子 emo 吐槽 推荐歌 推荐书 自检".split())
ALIASES={"/毒舌身份":"/身份","/毒舌帮助":"/帮助","/毒舌状态":"/状态"}


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
        self.engine=Engine(self.store,personas,json.loads((root/"catalog.json").read_text(encoding="utf-8")),self.generate,settings,observe=report)

    async def initialize(self):
        async def purge_loop():
            while True:
                await asyncio.sleep(30)
                self.engine.purge()
        self.purge_task=asyncio.create_task(purge_loop())

    async def generate(self,system,prompt,image,max_output):
        provider_id=self.config.get("provider_id","")
        if not provider_id:
            raise ProviderConfigError("missing")
        provider=self.context.get_provider_by_id(provider_id)
        if not provider:
            raise ProviderConfigError("not_found")
        client=getattr(provider,"client",None)
        if client is None or getattr(client.base_url,"host","")!="api.deepseek.com" or client.base_url.scheme!="https":
            raise ProviderConfigError("endpoint")
        images=[]
        image_notice=""
        if image:
            try:
                images=[await prepare_image(image)]
            except Exception:
                prompt += "\n[图片读取失败；不要猜测图片内容，只依据文字回复。]"
                image_notice="图片读取失败，已按文字处理。\n"
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

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-10)
    async def on_group(self,event: AstrMessageEvent):
        if event.get_platform_name()!="qq_official":
            return
        event.set_extra("qqbot_plugin_seen",True)
        report("plugin.enter",event=event)
        # Slash prefixes are stripped from message_str by WakingCheckStage.
        # QQ's real parser produces At + Plain; don't parse the At's ID/name.
        original="".join(x.text for x in event.get_messages() if isinstance(x,Plain)).strip()
        text=original or event.get_message_str().strip()
        parts=text.split(maxsplit=1)
        cmd=parts[0] if parts else ""
        command=ALIASES.get(cmd,cmd)
        own=command.removeprefix("/") in COMMANDS and command.startswith("/")
        # Command filters that already matched (including renamed commands)
        # belong to the framework/other plugin. Never consume them or spend.
        from astrbot.core.star.filter.command import CommandFilter
        from astrbot.core.star.filter.command_group import CommandGroupFilter
        other_command=any(h.handler_module_path!=__name__ and any(isinstance(f,(CommandFilter,CommandGroupFilter)) for f in h.event_filters) for h in event.get_extra("activated_handlers",[]))
        if other_command or (text.startswith("/") and not own):
            report("plugin.pass.command",event=event)
            return
        group=str(event.get_group_id() or "")
        if not group:
            report("plugin.ignore.no_group",event=event)
            return
        # In v4.29.0 this flag means PROHIBIT the default agent. False allows
        # it (ProcessStage checks `not event.call_llm`). No second paid path.
        event.should_call_llm(True)
        raw=getattr(event.message_obj,"raw_message",None)
        author=raw.get("author",{}) if isinstance(raw,dict) else getattr(raw,"author",None)
        author_bot=author.get("bot",False) if isinstance(author,dict) else getattr(author,"bot",False)
        raw_data=getattr(raw,"raw_data",{})
        raw_author=raw_data.get("author",{}) if isinstance(raw_data,dict) else {}
        bot=event.get_sender_id()==event.get_self_id() or bool(author_bot) or bool(raw_author.get("bot",False)) or event.get_sender_id() in self.config.get("ignored_bot_ids",[])
        if bot:
            report("plugin.ignore.bot",event=event)
            return
        if own:
            text=command+(" "+parts[1] if len(parts)>1 else "")
        if command=="/身份":
            await self.respond(event,"本群 ID："+group+"\n你的发送者 ID："+event.get_sender_id()+"\n仅将自己的 ID 填入本机 AstrBot 管理员列表，并把群 ID 填入插件 allowed_groups。",consume=True)
            return
        allowed=[str(x) for x in self.config.get("allowed_groups",[])[:128]]
        if group not in allowed:
            report("plugin.ignore.unlisted",event=event)
            if own:
                await self.respond(event,"本群未加入插件允许列表。先发送 /身份 获取配置所需 ID，在本机 WebUI 设置管理员和插件 allowed_groups，保存并重载后发送 /启用群聊 已告知群友。",consume=True)
            return
        if not own and event._has_send_oper:
            report("plugin.pass.already_replied",event=event)
            return
        images=[x for x in event.get_messages() if isinstance(x,Image)]
        image=str(getattr(images[0],"url","") or "") if images else ""
        # PreProcessStage localizes Image.url before plugins run. Recover QQ's
        # original attachment URL, still subject to our HTTPS/DNS/size checks;
        # never loosen the image guard to accept arbitrary local files.
        attachments=raw.get("attachments",[]) if isinstance(raw,dict) else getattr(raw,"attachments",[])
        if images:
            for item in attachments or []:
                kind=item.get("content_type","") if isinstance(item,dict) else getattr(item,"content_type","")
                url=item.get("url","") if isinstance(item,dict) else getattr(item,"url","")
                if str(kind or "").startswith("image/") and url:
                    image="https:"+url if url.startswith("//") else str(url)
                    break
        # Keep the existing storage key; updating code must not orphan consent,
        # privacy choices or budget counters already saved in the local DB.
        scope=event.unified_msg_origin
        m=Message(scope,event.get_sender_id(),str(event.message_obj.message_id or ""),text,bool(event.is_at_or_wake_command),event.is_admin(),False,image)
        job=asyncio.current_task()
        self.jobs.add(job)
        try:
            reply=await self.engine.handle(m)
            if reply:
                await self.respond(event,reply,consume=own)
            else:
                report("plugin.ignore.policy",event=event)
                if own: event.stop_event()
        except Exception as error:
            report("plugin.failed",error=error,event=event)
            if own or event.is_at_or_wake_command:
                await self.respond(event,"插件配置或数据异常，请运行本地自检或安全诊断。原始异常不会发送到群里。",consume=own)
        finally:
            self.jobs.discard(job)

    async def respond(self,event,text,consume=False):
        report("plugin.reply.ready",event=event)
        try:
            # Short plain text needs no QQ native Markdown entitlement. Send
            # before stopping; a stopped yielded result can skip later stages.
            await event.send(event.plain_result(text).use_t2i(False).use_markdown(False))
            report("plugin.reply.sent",event=event)
        except Exception as error:
            report("plugin.reply.failed",error=error,event=event)
        finally:
            if consume: event.stop_event()

    async def terminate(self):
        pending=[task for task in self.jobs if task is not asyncio.current_task()]
        if self.purge_task:
            pending.append(self.purge_task)
        for task in pending: task.cancel()
        if pending: await asyncio.gather(*pending,return_exceptions=True)
        self.store.close()
