"""Local, opt-in, expiring diagnostics. No free-form payload fields exist."""
import contextvars
from datetime import datetime, timezone
import functools
import json
import logging
from pathlib import Path
import re
import secrets
import threading
import time

ROOT=None
TRACE=contextvars.ContextVar("qqbot_trace",default=None)
LOCK=threading.Lock()
CODES=frozenset("adapter.group.received adapter.private.received pipeline.begin pipeline.end pipeline.no_plugin pipeline.failed plugin.enter plugin.pass.command plugin.pass.already_replied plugin.ignore.no_group plugin.ignore.bot plugin.ignore.unlisted plugin.ignore.policy plugin.reply.ready plugin.reply.sent plugin.reply.failed plugin.failed model.begin model.completed model.failed model.skipped.cooldown model.skipped.budget send.begin send.completed send.failed diagnostics.started".split())


def error_code(error):
    if error is None:return "none"
    status=getattr(error,"status_code",None)
    if status in (400,401,403,404,408,409,422,429,500,502,503,504):return "http_"+str(status)
    name=type(error).__name__
    if type(error).__module__=="botpy.errors":
        # qq-botpy stores the entire private server response in `msgs` and has
        # no status_code attribute. Classify by its fixed exception classes.
        return {"AuthenticationFailedError":"qq_auth","ForbiddenError":"qq_forbidden","NotFoundError":"qq_not_found","MethodNotAllowedError":"qq_method","SequenceNumberError":"qq_sequence","ServerError":"qq_server"}.get(name,"internal")
    if isinstance(error,TimeoutError) or name in ("APITimeoutError","ReadTimeout","ConnectTimeout"):return "timeout"
    if isinstance(error,ConnectionError) or name in ("APIConnectionError","ConnectError","ClientConnectorError","ClientConnectorDNSError"):return "network"
    if isinstance(error,PermissionError):return "permission"
    if isinstance(error,ValueError):return "configuration"
    if isinstance(error,OSError):return "io"
    return "internal"


def enabled():
    if ROOT is None:return False
    try:
        flag=json.loads((ROOT/"data/safe-diagnostics.enabled.json").read_text(encoding="utf-8"))
        return 0 < flag["expires"]-time.time() <= 3600
    except (OSError,ValueError,KeyError,TypeError):return False


def emit(code,error=None,event=None):
    if code not in CODES or not enabled():return
    trace=event.get_extra("qqbot_trace") if event is not None else TRACE.get()
    record={"time":datetime.now(timezone.utc).isoformat(timespec="seconds"),"code":code,"error":error_code(error)}
    if isinstance(trace,str) and re.fullmatch(r"[a-f0-9]{12}",trace):record["trace"]=trace
    try:
        path=ROOT/"data/safe-diagnostics.jsonl"
        with LOCK:
            if path.exists() and path.stat().st_size>2_000_000:path.replace(path.with_suffix(".previous.jsonl"))
            with path.open("a",encoding="utf-8") as out:out.write(json.dumps(record,separators=(",",":"))+"\n")
    except OSError:pass  # Never break a bot event when diagnostics is unwritable.


def phase(path):
    path=str(path).replace("\\","/").lower()
    for fragment,label in (("qqofficial","qq.adapter"),("process_stage","pipeline.process"),("waking_check","pipeline.wake"),("whitelist_check","pipeline.whitelist"),("session_status_check","pipeline.session"),("rate_limit_check","pipeline.rate_limit"),("respond/","pipeline.respond"),("result_decorate","pipeline.decorate"),("preprocess_stage","pipeline.preprocess"),("star_manager","plugin.loader"),("data/plugins/","plugin"),("provider","model"),("dashboard","panel"),("httpx","network"),("botpy","qq.transport")):
        if fragment in path:return label
    return "framework"


def install_private_logging():
    factory=logging.getLogRecordFactory()
    def private_factory(*args,**kwargs):
        record=factory(*args,**kwargs)
        stage=phase(record.pathname)
        error=record.exc_info[1] if record.exc_info else None
        record.msg=f"[隐私保护] stage={stage} error={error_code(error)}"
        record.args=()
        record.exc_info=record.exc_text=record.stack_info=None
        record.pathname=record.filename=record.module="framework"
        record.funcName="event"
        return record
    logging.setLogRecordFactory(private_factory)
    from loguru import logger
    def private_patch(record):
        stage=phase(record["file"].path)
        exception=record.get("exception")
        error=exception.value if exception else None
        safe=re.fullmatch(r"\[隐私保护\] stage=(framework|qq\.adapter|qq\.transport|pipeline\.(?:process|wake|whitelist|session|rate_limit|respond|decorate|preprocess)|plugin(?:\.loader)?|model|panel|network) error=(none|internal|configuration|timeout|network|permission|io|qq_(?:auth|forbidden|not_found|method|sequence|server)|http_(?:400|401|403|404|408|409|422|429|500|502|503|504))",record["message"])
        if not safe:record["message"]=f"[隐私保护] stage={stage} error={error_code(error)}"
        record["exception"]=None
        # Upstream interceptors add platform instance IDs after LogRecordFactory.
        record["extra"].update(platform_id=None,platform_type=None,plugin_name=None,plugin_tag="[Core]",source="core",source_file=stage,source_line=0,category="system")
    logger.configure(patcher=private_patch)


def install(root):
    """Observe pinned public execution boundaries without modifying framework files."""
    global ROOT
    ROOT=Path(root)
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import QQOfficialPlatformAdapter
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import QQOfficialMessageEvent
    from astrbot.core.log import _RecordEnricherFilter
    enrich=_RecordEnricherFilter.filter
    if not getattr(enrich,"_qqbot_safe",False):
        def safe_enrich(self,record):
            result=enrich(self,record)
            record.platform_id=record.platform_type=record.plugin_name=None
            record.plugin_tag="[Core]"
            record.source="core"
            return result
        safe_enrich._qqbot_safe=True
        _RecordEnricherFilter.filter=safe_enrich
    if getattr(PipelineScheduler.execute,"_qqbot_observed",False):return
    commit=QQOfficialPlatformAdapter.commit_event
    execute=PipelineScheduler.execute
    send=QQOfficialMessageEvent.send
    @functools.wraps(commit)
    def received(self,event):
        event.set_extra("qqbot_trace",secrets.token_hex(6))
        emit("adapter.group.received" if event.get_group_id() else "adapter.private.received",event=event)
        return commit(self,event)
    @functools.wraps(execute)
    async def pipeline(self,event):
        if event.get_platform_name()!="qq_official":return await execute(self,event)
        if not event.get_extra("qqbot_trace"):event.set_extra("qqbot_trace",secrets.token_hex(6))
        token=TRACE.set(event.get_extra("qqbot_trace"))
        emit("pipeline.begin",event=event)
        try:return await execute(self,event)
        except Exception as error:
            emit("pipeline.failed",error=error,event=event)
            raise
        finally:
            if event.get_group_id() and not event.get_extra("qqbot_plugin_seen"):emit("pipeline.no_plugin",event=event)
            emit("pipeline.end",event=event)
            TRACE.reset(token)
    pipeline._qqbot_observed=True
    @functools.wraps(send)
    async def sending(self,message):
        emit("send.begin",event=self)
        try:
            result=await send(self,message)
            emit("send.completed",event=self)
            return result
        except Exception as error:
            emit("send.failed",error=error,event=self)
            raise
    QQOfficialPlatformAdapter.commit_event=received
    PipelineScheduler.execute=pipeline
    QQOfficialMessageEvent.send=sending
    emit("diagnostics.started")


def report(root):
    """Summarize codes, not messages; absence is a clue, never platform proof."""
    path=Path(root)/"data/safe-diagnostics.jsonl"
    records=[]
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item=json.loads(line)
                if item.get("code") in CODES:records.append(item)
            except ValueError:pass
    except OSError:pass
    counts={code:sum(r.get("code")==code for r in records) for code in CODES}
    print("安全诊断：只统计当前文件；不含正文、凭据、群或成员 ID。")
    for code in sorted(counts):
        if counts[code]:print(code,counts[code])
    for code,label in (("adapter.group.received","适配器收到群消息"),("plugin.enter","进入自研插件"),("plugin.reply.sent","插件发送成功"),("plugin.reply.failed","插件发送失败"),("send.failed","适配器发送失败"),("model.failed","模型失败"),("pipeline.no_plugin","进入管线但未进入插件")):
        print(label+"："+str(counts[code]))
    if not counts["adapter.group.received"]:print("未记录到适配器群消息；请在启用诊断后重启，再实际发一条消息。此结果不能单独证明 QQ 平台未投递。")
    errors={"timeout","network","configuration","permission","io","internal","http_400","http_401","http_403","http_404","http_408","http_422","http_429","http_500","http_502","http_503","http_504","qq_auth","qq_forbidden","qq_not_found","qq_method","qq_sequence","qq_server"}
    print("错误类别：",", ".join(sorted({r.get("error","internal") for r in records if r.get("error") in errors})) or "none")
