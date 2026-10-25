#!/usr/bin/env python3
"""生成 content/YYYY-MM-DD.json：把 raw 数据 + 我写的摘要/判断组装成站点内容。

摘要与判断由助手撰写（不是模型自动摘要），来源可核。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HN_SUMMARY = {
    "No signs of AI payoff outside the tech sector":
        "Apollo 的宏观观察：AI 资本开支的回报目前只在科技行业内部可见，制造业、零售与医疗等行业的产出和就业数据看不到对应提升。作者认为不是统计滞后，而是投入集中在少数能自建模型的部门，其他行业买到的只是工具而不是产能。评论区争的是「还没到时候」还是「本来就不会外溢」。",
    "Show HN: Steal My Bitcoin":
        "作者把一小笔比特币放进公开挑战，任何人都可以尝试拿走，用真金白银检验钱包、密钥管理与签名流程的攻击面。页面公开尝试次数与失败原因，等于把一次渗透测试做成公开演示。适合当安全教材看，不要当投资内容。",
    "Node2Shell evolves to HTTP2Shell, blast radius affects many HTTP libs and apps":
        "Python 包供应链漏洞从 Node2Shell 演化成 HTTP2Shell，波及大量 HTTP 库与应用，已有 CVE 编号。攻击面在依赖树的传递闭包里，不是直接依赖，所以只读 requirements.txt 会漏。自托管项目今天该跑一遍依赖审计，尤其是装了 brotli 相关包的服务。",
    "Roku developer repositories moved from GitHub to GitLab":
        "Roku 把开发者仓库整体迁到 GitLab，GitHub 上的旧地址会失效。依赖 GitHub 的 CI、镜像、文档链接与自动发布脚本都要跟着改；做 Roku 渠道的团队需要检查构建脚本里的远端地址，以及有没有把仓库路径写死在配置里。",
    "The Goose Programming Language":
        "Goose 把「多个数据栈、相对引用、二进制结构校验」做进语言层，目标是让解析文件与网络数据的开销接近零：结构可以直接内存映射，网络数据到手即可用。Carmack 在评论区补了实现细节，讨论集中在与传统序列化方案的性能差距。",
    "How close can pure functional programming get to C?":
        "Roc 作者用一组实测比较纯函数式与 C 的性能边界，结论是差距主要来自内存布局与分配策略，而不是语言范式本身。文章给出几组可复现基准，并指出数据密集场景下值语义与不可变结构的复制成本才是真正瓶颈。",
    "We should be more ambitious with the software we build":
        "Dan Luu 论证今天的软件野心在收缩：技术上能做的事比实际做出来的多得多，主要原因是工程组织选择保守路线，而不是能力不允许。他举了若干「本来可以更好但没人做」的例子，把责任放在激励与组织，而不是工具链。",
    "America has lost 200k of jobs in media, film and the arts. How much is AI?":
        "用行业就业数据拆 AI 对创意行业的影响：媒体、影视与艺术类岗位近年减少约二十万，但作者强调归因困难——流媒体商业模式变化、广告下滑、外包转移都在同时发生。结论是不能把账全算到 AI 头上，也不能假设没有影响。",
    "GPU-unlock: FP/BF16 instruction issue rate on Nvidia 3000's cards":
        "在 Nvidia 3000 系显卡上解锁 FP/BF16 指令发射率的实验性工具，属于硬件逆向：通过修改固件或驱动路径提高吞吐。作者给出测试方法与风险提示，稳定性与保修都要自己承担，适合当研究材料而不是生产方案。",
    "Why is AI generated language so hard to understand?":
        "论文把「AI 写的句子难读」拆成句法复杂度、信息密度与指代链三层，并给出可测量的指标。结论是难读主要来自信息密度过高与指代不清，而不是词汇生僻；这为可读性提供了一个可以优化的目标函数。",
}

GH_SUMMARY = {
    "cloudflare/security-audit-skill":
        "Cloudflare 的编码 agent 技能：六阶段安全审计流程，先侦察架构与输入面，再按覆盖率追踪可疑点，交叉验证后输出结构化 JSON，最后由独立 agent 复核。覆盖 HTTP、内存安全、供应链、云部署等十三类攻击面，适合多回合、可追溯的源码审计。",
    "NVIDIA/OpenShell":
        "NVIDIA 的 agent 安全运行时：在内核层拦截文件访问、系统调用与网络连接，策略变更前做形式化验证，让自主 agent 只能访问被授权的数据、密钥与网络资源。属于把边界从指令搬进运行时的路线，企业部署 agent 时可以直接对照。",
    "aws/agent-toolkit-for-aws":
        "AWS 官方的 MCP servers、skills 与 plugins 集合，让 agent 通过标准协议操作 AWS 资源。价值在权限模型与官方维护：比起自己包一层命令行工具，官方工具链在审计、配额与错误处理上更完整，适合企业落地时做基线。",
    "Nutlope/hallmark":
        "反「AI 味」的设计技能：内置四十八个主题模板，从纸张、排版、颜色、质感等材料角度约束输出，并带检测 AI 痕迹的规则，比如标题上方的眉毛文案、首字母大写标签、每页结尾的注册表单。给 Claude Code、Cursor、Codex 用。",
    "luongnv89/claude-howto":
        "Claude Code 的图解教程与可复制模板，从基础概念讲到进阶 agent 用法。适合当团队上手材料：把常见任务拆成可粘贴的配置与指令片段，减少每个人自己摸索的成本，也方便对照工具权限设计。",
    "pbakaus/impeccable":
        "一套让 AI harness 更懂设计的语言与规范层：把设计判断写成可执行的约束，让编码 agent 生成界面时按规范走。属于 harness 决定产出质量这条线上的实践，适合和设计系统一起使用。",
    "pollen-robotics/microduck":
        "Pollen Robotics 的双足小鸭子机器人，Rust 实现，开源硬件与控制栈。定位是玩具级但结构完整：步态、平衡与传感都在仓库里，适合作为机器人控制与嵌入式 Rust 的入门项目。",
    "google-gemini/gemini-cli":
        "Gemini 的终端 agent CLI，开源。和 Claude Code、Codex 属于同一形态：在终端里读写文件、执行命令、调用外部工具。差异主要在权限模型、扩展方式与上下文管理，做 harness 对比时可以拿它当第三个样本，观察官方团队怎么划定边界。",
    "jbiaojerry/ebook-treasure-chest":
        "中文电子书下载链接聚合，覆盖多家读书 App 的资源索引，按书名与作者组织。仓库本身只存链接不存文件；版权风险需要自己判断，适合做资料检索的入口而不是分发渠道。",
    "makecindy/cindy":
        "开箱即用的开源 AI Agent，TypeScript 实现，定位是「想到就能做到」，偏产品化而不是框架。适合观察一个 agent 产品如何组织会话、工具与记忆，也能看到产品侧对失败重试与权限提示的处理方式，作为自建 harness 的参照。",
}

PAPER_SUMMARY = {
    "Direct Pass@$k$ Optimization for Thought Pruning":
        "测试时扩展要跑大量候选解，全部跑完成本很高。这篇先只生成短前缀就剪枝，再决定把后续算力给谁，并且直接以 pass@k 为目标做优化，在质量与多样性之间取平衡。实验显示同等预算下比均匀分配更划算。",
    "EpiSEM-Bench":
        "工具型 agent 的安全评测：当工具响应遗漏了安全相关事实、但每句话都为真时，agent 会不会执行被禁止的动作。基准是可执行的，测三件事：不安全执行、安全边界是否守住、以及能否恢复缺失的证据。",
    "Simulated Control Evals":
        "控制评估用来测防护措施能否阻止故意作恶的模型，通常在专用环境里做，再把结论外推到真实部署。本文质疑这个外推：部署环境的任务特性与这些设定并不一致，结论可能系统性高估防护效果。",
    "Who Is Sycophantic to Whom?":
        "反向谄媚：当模型自信、前后一致但答案是错的，用户会不会向它屈服。三十二人的组内实验显示，人对模型的信任校准会随模型自信度崩塌；这比模型讨好用户更值得警惕。",
    "What Makes a Good Unmasking Policy?":
        "掩码扩散语言模型并行生成 token，效率取决于提交哪些预测。本文把监督式解掩码策略看作对解码过程的蒸馏，用控制变量比较教师标签、输入与模型容量各自的作用，指出哪些设计真正影响速度与准确率的权衡。",
    "Contestable Agents for Data Governance":
        "工业组织的结构化与非结构化知识治理，长期依赖少数资深员工。本文提出可争议的 agent：记录人对 AI 生成元数据的管理痕迹，把谁改了什么、依据是什么留成可审计的证据链。",
    "Beyond Causal Masks":
        "隐藏的未来 token 泄漏：自适应残差路由解码器里，序列级的路由摘要把前缀信息暴露给未来 token，即使因果掩码本身正确，也会让教师强制评估虚高、自由生成变差。作者提出审计与定位方法，并给出修复方向。",
    "Jev-DLC":
        "决策级持续学习：用户接受或撤销某个决策时，把被替换的决策当作类型化反馈持续学习，而不是只学最终答案。这让偏好能在部署后继续被修正，同时保留决策之间的替换关系。",
}

YT = [
    ("Is the Agent Harness Dead? — Jediah Katz, SpaceXAI", "https://www.youtube.com/watch?v=Zq6kL0mS9pY",
     "AI Engineer", "2026-10-19",
     "标题就是问题：模型能力上来后 harness 还剩什么价值。和他的主线正面对撞，值得看论证而不是结论。"),
    ("AI Writes the Code. So What's Left for Engineers? - Laurie Voss, Arize AI", "https://www.youtube.com/watch?v=kspZP5BgkEU",
     "AI Engineer", "2026-10-24",
     "从 Arize 的实践看工程角色怎么变：代码由 AI 写之后，剩下的判断、验证与责任怎么分。"),
    ("Your Agent Fix Just Broke Something Else - Sofia Jakovcevic, Arize AI", "https://www.youtube.com/watch?v=v5tm5EAzsAs",
     "AI Engineer", "2026-10-24",
     "一个 prompt 改动让 agent 安全性 +17 分、完成率 -17 分。讲用生产 trace 建回归环，正是「修一个坏一个」的解法。"),
    ("How Bridgewater Turned 100 Million Documents Into an Edge - Sam Green & Aaron Linsky", "https://www.youtube.com/watch?v=CLve4Nx_RwI",
     "AI Engineer", "2026-10-24",
     "1 亿文档 + 权限 + 本体，人和 agent 用同一套检索。precision@10 从 60% 拉到 90% 的做法值得抄。"),
    ("Can AI Understand a Distressed Credit? - Harneet Kaur, Axim Intelligence", "https://www.youtube.com/watch?v=WOszaC1WWbQ",
     "AI Engineer", "2026-10-24",
     "两个顶级模型对同一份困境债给出相反结论，分层拆解后收敛。问题是：一致等于正确吗。"),
]

NEWS_PICKS = [
    ("NVIDIA/OpenShell", "https://github.com/NVIDIA/OpenShell",
     "Agent 的边界正在从提示词搬进运行时：内核层拦截 + 策略形式化验证。你做并发 agent，这层迟早要自己实现一遍。"),
    ("No signs of AI payoff outside the tech sector", "https://www.apollo.com/wealth/insights-news/insights/daily-spark/no-signs-of-ai-payoff-outside-the-tech-sector",
     "反方证据值得留档：AI 投入的回报目前还锁在科技行业内部。判断项目价值时，别把行业热度当成需求。"),
    ("The Goose Programming Language", "https://aardappel.github.io/goose/",
     "多数据栈 + 相对引用 + 二进制校验，把解析开销压到接近零。Carmack 在评论区补充，属于「老问题的新解法」。"),
    ("cloudflare/security-audit-skill", "https://github.com/cloudflare/security-audit-skill",
     "把安全审计做成 agent 可执行的多阶段流程，产出可独立复核。这个「流程 + 证据」的结构，比单个 prompt 更值得复用。"),
]


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    raw = json.loads((ROOT / "raw" / f"{day}.json").read_text(encoding="utf-8"))

    items = []

    for title, url, why in NEWS_PICKS:
        items.append({
            "kind": "news", "source_id": "pick", "source_name": "我的挑选",
            "title": title, "url": url, "published": day, "summary": why,
            "categories": ["pick"], "priority": "high",
        })

    for h in raw["hacker_news"]:
        s = HN_SUMMARY.get(h["title"])
        if not s:
            continue
        items.append({
            "kind": "hacker_news", "source_id": "hn", "source_name": "Hacker News",
            "title": h["title"], "url": h["url"], "published": h["published"],
            "summary": s, "categories": ["hn"], "priority": "normal",
        })
        if len([i for i in items if i["kind"] == "hacker_news"]) >= 10:
            break

    for g in raw["github_trending"]:
        s = GH_SUMMARY.get(g["repo"])
        if not s:
            continue
        items.append({
            "kind": "github_trending", "source_id": "github", "source_name": "GitHub Trending",
            "title": g["repo"], "url": g["url"], "published": day, "summary": s,
            "categories": [g.get("language") or "repo"], "priority": "normal",
        })

    for title, url, channel, published, why in YT:
        vid = url.rsplit("=", 1)[-1]
        items.append({
            "kind": "youtube", "source_id": "yt", "source_name": channel,
            "title": title, "url": url, "published": published, "summary": why,
            "categories": ["video"], "priority": "normal",
            "image_url": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        })

    for p in raw["papers"]:
        t = p["title"].removeprefix("Title:").strip()
        s = PAPER_SUMMARY.get(t)
        if not s:
            for key, val in PAPER_SUMMARY.items():
                if t.startswith(key[:28]):
                    s = val
                    break
        if not s:
            print("未匹配论文:", t[:70])
            continue
        items.append({
            "kind": "paper", "source_id": "arxiv", "source_name": "arXiv",
            "title": t, "url": p["url"], "published": day, "summary": s,
            "categories": ["paper"], "priority": "normal",
        })

    payload = {
        "date": day,
        "summary": (
            "今天三条线并成一条：**agent 的边界正在从指令层搬进运行时**。NVIDIA OpenShell 用内核拦截加形式化验证，"
            "Cloudflare 把安全审计做成可独立复核的六阶段流程，EpiSEM-Bench 则指出「工具只说真话但漏掉关键事实」时 agent 会越界——"
            "三件事说的是同一个结论：约束必须写进环境，不能写在提示里。第二条线是**证据**：Apollo 的数据说 AI 回报还锁在科技行业内部，"
            "控制评估的外推问题、pass@k 剪枝、Jev-DLC 都是在问「你怎么证明它真的更好」。第三条线是**成本**：并行解码的提交策略、"
            "剪枝后再算、本地小模型下沉，都是在同一个预算下换确定性。视频侧今天全是 AI Engineer 的现场：agent 回归、文档检索、"
            "困境债判断，讲的都是「修一个坏一个」怎么用 trace 和评测环收住。"
        ),
        "movie": {
            "title": "Zodiac", "year": 2007, "director": "David Fincher",
            "reason": "今天的主线是证据与验证，这部片子讲的正是「线索很多、结论很慢」：一个人用几十年把零散事实拼成可复核的链条，最后仍然无法闭环。适合在信息很多、判断容易发快的时候看。",
            "tags": ["film"],
        },
        "book": {
            "title": "The Craft of Research", "author": "Wayne C. Booth, Gregory G. Colomb, Joseph M. Williams",
            "chapter": "Making Good Arguments",
            "reason": "把「论点—理由—证据—反驳」拆成可检查的结构，和今天几篇论文的评测设计是同一套思维：先问怎么证伪，再谈结论。",
            "tags": ["book"],
        },
        "items": items,
    }

    out = ROOT / "content" / f"{day}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = {}
    for i in items:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    print("写入", out, kinds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
