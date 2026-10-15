"""Visible root entries shared by clean bundles and data-preserving patches."""

def batch(action):
    start='@echo off\r\nchcp 65001 >nul\r\nset "QQBOT_APP=%~dp0程序文件"\r\nif not exist "%QQBOT_APP%\\runtime\\python.exe" set "QQBOT_APP=%~dp0"\r\n'
    if action=="start":
        return start+'powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%QQBOT_APP%\\start.ps1"\r\nif errorlevel 1 pause\r\n'
    if action=="doctor":
        return start+'"%QQBOT_APP%\\runtime\\python.exe" -I -X utf8 "%QQBOT_APP%\\doctor.py"\r\npause\r\n'
    if action in ("update","diagnostics"):
        script="updater.py" if action=="update" else "diagnostic_control.py"
        return start+'"%QQBOT_APP%\\runtime\\python.exe" -I -X utf8 "%QQBOT_APP%\\'+script+'"\r\npause\r\n'
    return start+'"%QQBOT_APP%\\runtime\\python.exe" -I -X utf8 "%QQBOT_APP%\\control.py" '+action+'\r\nif errorlevel 1 pause\r\n'


ENTRIES={"启动机器人.bat":batch("start"),"打开管理面板.bat":batch("open"),"停止机器人.bat":batch("stop"),"重置管理密码.bat":batch("reset"),"自检.bat":batch("doctor"),"self-check.bat":batch("doctor")}
ENTRIES.update({"安全诊断.bat":batch("diagnostics")})
ENTRIES["首次使用.html"]='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>QQ 毒舌群友 · 首次使用</title><style>body{font:17px/1.8 "Microsoft YaHei",sans-serif;background:#f3f6fa;color:#26374a;max-width:850px;margin:40px auto;padding:0 24px}main{background:white;border-radius:18px;padding:32px}h1{margin-top:0;color:#2675a5}.status{color:#8b5b12}li{margin:14px 0}code{background:#eef3f8;padding:3px 6px}a{color:#146d9f}</style><main><h1>QQ 毒舌群友</h1><p class="status">v1.0.0 · 群内身份、授权和 AI 文字回复已获用户真人验证。主动接话、图片和长期记忆仍为实验功能，完整范围见验收报告。</p><ol><li>完整解压后，当前目录就能看到所有常用入口。双击 <b>启动机器人.bat</b>。</li><li>首次启动会打开本机密码设置窗口。输入两遍密码，点击每个密码框旁的小眼睛可以显示或隐藏。要求 12–128 位，含大写字母、小写字母和数字。</li><li>首次联网安装固定依赖后，会自动打开管理面板。默认用户名 <code>astrbot</code>，使用刚设置的密码登录，并保存好密码。</li><li>在原生面板填写自己的 DeepSeek Key、配置 QQ 官方机器人 AppID 和 AppSecret。不要将凭据发给其他人。<a href="使用说明/新手安装指南.md">配置步骤</a></li></ol><p>后台入口：<b>打开管理面板.bat</b>。默认地址：<a href="http://127.0.0.1:6185">http://127.0.0.1:6185</a></p><p>停止服务：双击 <b>停止机器人.bat</b>；旧版运行窗口可按 Ctrl+C。</p><p>忘记密码：先停止服务，再双击 <b>重置管理密码.bat</b>。仅重置面板认证，不删除 QQ、Key、插件或数据；已有用户名会保留。</p><p><b>data</b> 是本机私密数据；<b>程序文件</b> 是内部依赖和框架，日常无需打开。不要删除 data，也不要把它上传分享。</p><p>没有开机启动项，也不自动创建桌面快捷方式。首次安装需要网络，无需预装 Python、Git 或 Docker。</p></main></html>'''

def write_entries(root):
    for name,body in ENTRIES.items():
        if name=="首次使用.html":
            body=body.replace("<p>后台入口：",'<p>正式版仅提供新版整合包，不提供旧版自动升级。排查无回复：双击 <b>安全诊断.bat</b>，开启后重启，再复现并查看结果，结束后关闭。</p><p>后台入口：')
        (root/name).write_bytes(body.encode("utf-8"))
