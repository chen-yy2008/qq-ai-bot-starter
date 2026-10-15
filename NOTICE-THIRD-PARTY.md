# 第三方来源与许可证

Copyright 2026 chen-yy2008. 自有代码采用 GNU AGPL-3.0-or-later，完整文本见 LICENSE。

| 组件 | 固定版本 | 来源 | 许可与分发方式 |
| --- | --- | --- | --- |
| AstrBot | v4.29.0；提交 db4ce0c4b0ae94f443c641f0f78cc9228ddabbeb | https://github.com/AstrBotDevs/AstrBot/tree/v4.29.0 | AGPL-3.0-or-later；包内 程序文件/framework 保留原版源码和 LICENSE；不修改上游代码。 |
| AstrBot dashboard | AstrBot-v4.29.0-dashboard.zip | https://github.com/AstrBotDevs/AstrBot/releases/tag/v4.29.0 | 保留同版本 dashboard 源码和 AstrBot LICENSE；构建资产校验匹配官方发布摘要。 |
| CPython Windows embedded x64 | 3.12.10 | https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip | Python Software Foundation License 及其完整捆绑许可，保留 程序文件/runtime/LICENSE.txt；不包含用户电脑的 Python 副本。 |
| uv | 0.9.5 | https://github.com/astral-sh/uv/tree/0.9.5 | MIT OR Apache-2.0；保留 程序文件/tools/licenses 下的两份许可证；独立安装工具。 |
| Python 传递依赖 | 149 个，精确版本与哈希见 packaging/requirements-win.lock | https://pypi.org/ | 首次启动在线安装，不预装进分发 ZIP；包括 QQ SDK、OpenAI SDK、Pillow 等，不将它们改标为本项目许可。 |

AstrBot Copyright (c) AstrBot contributors；uv Copyright (c) Astral Software Inc.；CPython Copyright (c) Python Software Foundation 及其贡献者。以对应项目保留的原始 LICENSE 为准。

上游 AstrBot 使用多个第三方项目，其仓库自带的通知文件均保留。模型服务和 QQ 账号权限不是软件许可证授予的权利。这里不捆绑、分发或索取 QQ 客户端登录凭据。API Key、AppSecret 和群聊数据只由使用者在本地设置。

源码与修改入口：https://github.com/chen-yy2008/qq-ai-bot-starter 。发布用户包同时附完整本项目源码归档；AstrBot 源码已在用户包 程序文件/framework 目录中提供。uv 上游固定版本亦可获取源代码；CPython 对应源代码见 https://www.python.org/downloads/release/python-31210/ 。
