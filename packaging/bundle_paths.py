"""Resolve the new flat bundle and existing installations without moving data."""
from pathlib import Path


def locations(script=__file__):
    app=Path(script).resolve().parent
    root=app.parent if app.name=="程序文件" else app
    return root,app
