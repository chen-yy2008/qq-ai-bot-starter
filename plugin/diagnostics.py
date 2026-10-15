"""Optional launcher bridge: codes only, never message/ID/exception text."""
import sys


def report(code, error=None, event=None):
    bridge=sys.modules.get("qqbot_safe_diagnostics")
    if bridge is not None:
        bridge.emit(code,error=error,event=event)
