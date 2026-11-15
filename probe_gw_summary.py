#!/usr/bin/env python3
"""探针：直接打 OpenCode Go 网关，看它到底返回什么（不打印密钥）。"""
import json, urllib.request, uuid
from pathlib import Path

GW = "https://opencode.ai/zen/go/v1"
MODEL = "deepseek-v4.1-flash"
key = json.loads((Path.home() / ".pi/agent/auth.json").read_text())["opencode-go"]["key"]

PROMPT = ("用简体中文写一段 60-220 字的摘要，介绍这个 Hacker News 上的技术讨论。"
          "只输出摘要正文，不要标题、不要列表、不要 markdown、不要任何解释。"
          "必须写满 60 字以上。不要使用破折号。\n\n"
          "标题：TCP Use-After-Free: CVE-2026-98432 / CVSS 9.8\n"
          "补充信息：A newly disclosed Linux kernel TCP vulnerability allows remote code execution.")

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": "http://127.0.0.1:7897"}))

def call(max_tokens=400, extra=None):
    payload = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}],
               "max_tokens": max_tokens}
    if extra:
        payload.update(extra)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(f"{GW}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json",
                                          "User-Agent": "curl/8.5.0",
                                          "x-opencode-session": str(uuid.uuid4())})
    with opener.open(req, timeout=90) as r:
        return json.loads(r.read().decode())

for mt in (400, 1200):
    print(f"\n===== max_tokens={mt} =====")
    try:
        d = call(mt)
        ch = d["choices"][0]
        msg = ch.get("message", {})
        content = msg.get("content") or ""
        print(f" finish_reason={ch.get('finish_reason')}")
        print(f" usage={d.get('usage')}")
        print(f" content 长度={len(content)}  预览={content[:160]!r}")
        for k in msg:
            if k != "content":
                v = str(msg[k])[:120]
                print(f" 额外字段 {k} = {v}")
        print(f" 顶层字段：{list(d.keys())}")
    except Exception as e:
        print(" 失败:", type(e).__name__, str(e)[:200])
