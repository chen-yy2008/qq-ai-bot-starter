"""Regenerate the distributed, editable data files (contains no credentials)."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

styles={
    "毒舌损友":("你像一个嘴损但有分寸的老朋友。捕捉最近对话的反差，先回应对方具体在说什么，轻轻吐槽其中的反差；可以直接接话，不必每句都打比方。允许自嘲，避免连续针对同一个人。不要每次加哈哈，不写讲道理长文。",100,"群友：计划明天早起。\n你：你的闹钟已经提前申请工伤了。"),
    "抽象串子":("你是荒诞喜剧旁白，夸张、戏谑，善于把日常小事写成虚构史诗。用明确的娱乐口吻，所有离谱描述都作为比喻，不冒充真实新闻或权威。不要煽动成员互相攻击。",140,"群友：又忘带伞了。\n你：本台虚构快讯：人类成功研发以头皮探测降雨系统。"),
    "深夜 EMO":("你像深夜电台的写作者，用克制、诗意、轻微自嘲回应普通情绪。少用陈词滥调。遇到真实痛苦或求助时停止玩梗，先承认对方感受，温和建议联系信任的人。不要美化伤害。",160,"群友：夜里还在改方案。\n你：灯替月亮值了班，咖啡替我醒着。愿这一稿也能有个好梦。"),
    "理性吐槽役":("你先识别一个具体逻辑漏洞，再用友好的幽默指出问题。区分观点和事实，不妄下结论。信息不足时明确说无法判断。不居高临下，不以聪明为由羞辱人。",180,"群友：我买了健身卡，所以已经变健康了。\n你：这推理很省力，建议健身房按想象中的肌肉收年费。"),
}
for name,(prompt,length,example) in styles.items():
    dump(ROOT/"personas"/(name+".json"),dict(name=name,system_prompt=prompt,max_chars=length,proactive_rules=["仅限允许列表且管理员显式开启的群","安静档位不主动发言","自然至少冷却 120 秒，活跃至少 60 秒","休息时间不主动；候选允许返回 [沉默]","长篇讨论不插话，不针对退出成员"],examples=[example],forbidden=["敏感身份攻击","嘲笑真实困境","泄露凭据","冒充真实新闻","执行系统指令"],preset=dict(mode="安静",context=False,memory=False)))

dump(ROOT/"plugin"/"catalog.json",dict(
    songs=[
        dict(title="稻香",creator="周杰伦",tags=["治愈","放松","累"],reason="用生活里的小幸福给紧绷的心情松绑。"),
        dict(title="平凡之路",creator="朴树",tags=["迷茫","成长","旅行"],reason="适合在迷茫时重新寻找自己的步伐。"),
        dict(title="倔强",creator="五月天",tags=["励志","奋斗","坚持"],reason="给还想坚持一下的人添一点力量。"),
        dict(title="夜空中最亮的星",creator="逃跑计划",tags=["夜晚","孤独","emo"],reason="适合安静的夜晚，留一点向前看的光。")],
    books=[
        dict(title="小王子",creator="安托万·德·圣埃克苏佩里",tags=["治愈","孤独","童话"],reason="篇幅短，适合重新体会关系与珍惜。"),
        dict(title="活着",creator="余华",tags=["人生","成长","现实"],reason="通过个人命运感受生命的韧性；主题较沉重。"),
        dict(title="苏菲的世界",creator="乔斯坦·贾德",tags=["思考","哲学","好奇"],reason="用故事打开哲学问题的入口。"),
        dict(title="银河系漫游指南",creator="道格拉斯·亚当斯",tags=["幽默","科幻","放松"],reason="用荒诞太空冒险给日常烦恼换个尺度。")]))

schema={
    "allowed_groups":dict(description="允许使用插件的 QQ 群 ID 列表",type="list",default=[],hint="在 QQ 群发送 /身份（无需模型或预先授权）获取真实群 ID。添加后仍需管理员发送 /启用群聊 已告知群友。"),
    "ignored_bot_ids":dict(description="其他机器人发送者 ID（防循环）",type="list",default=[]),
    "provider_id":{'description': 'DeepSeek 模型提供者实例（不是提供商源）', 'type': 'string', '_special': 'select_provider', 'default': '', 'hint': '先在模型页面创建并启用官方 DeepSeek OpenAI 兼容模型，然后在此选择它。例如源 ID 为 deepseek、模型名为 deepseek-flash 时，实例 ID 是 deepseek/deepseek-flash，而不是 deepseek。API Base URL：https://api.deepseek.com/v1；Key 只填模型页面。模型名以账号实际可用列表为准。'},
}
settings={"cooldown":(20,"每群明确触发冷却秒数"),"daily_calls":(60,"每群每日请求上限"),"daily_tokens":(60000,"每群每日 Token 上限（含失败预留）"),"global_daily_calls":(200,"全局每日请求上限"),"global_daily_tokens":(200000,"全局每日 Token 上限"),"daily_proactive":(8,"每群每日主动候选上限"),"concurrency":(2,"全局模型并发上限（1–4）"),"timeout":(25,"整体请求超时秒数"),"quiet_start":(0,"上海时间休息开始小时"),"quiet_end":(8,"上海时间休息结束小时，相等时不设休息"),"token_price":(100.0,"每百万 Token 保守估算单价（元，不是官方报价）"),"daily_cost":(6.0,"每群每日估算费用上限（元，不是账单）")}
for key,(default,description) in settings.items():
    schema[key]=dict(description=description,type="float" if isinstance(default,float) else "int",default=default)
dump(ROOT/"plugin"/"_conf_schema.json",schema)
dump(ROOT/"config"/"plugin.example.json",{k:v["default"] for k,v in schema.items()})
