# newsInAI

我的每日简报页面。**版式与主站 `news.zhangyvjing.com` 完全一致**（同一个渲染器），
但**内容是我自己采集、自己写的**——不是镜像主站。

- 主站：`news.zhangyvjing.com`（他的 Daily Brief，内容是主仓库流水线生成的）
- 本站：同一套 HTML/CSS/分区编号，条目来自本仓库自己的采集与判断

## 结构

```
collect.py          采集 HN / GitHub Trending / arXiv（一手数据，无 key）
make_content.py     把 raw 数据 + 我写的摘要与判断组装成 content/YYYY-MM-DD.json
build.py            调 workflows/ 下的渲染器 → site/
verify_parity.py    版式一致性校验（CSS 逐字节 + 分区集合 + 渲染器版本）
sync_renderer.sh    从主仓库同步渲染器
workflows/          主仓库渲染器的 vendored 副本（唯一改动的补丁：新增 02 Worth Reading）
```

## 每天怎么跑

```bash
export https_proxy=http://127.0.0.1:7897 http_proxy=http://127.0.0.1:7897
python3 collect.py                 # 采集，约 1-2 分钟
python3 make_content.py            # 组装内容（摘要在脚本里维护）
python3 build.py                   # 渲染
python3 verify_parity.py           # 必须通过
```

## 分区（与主站同号）

| 编号 | 分区 | 来源 |
|---|---|---|
| 00 | Film / Book Chapter | 我选 |
| 01 | Insight | 我写 |
| 02 | Worth Reading | 我的挑选（本仓库新增） |
| 03 | Hacker News | HN 首页 + 近 30h 高分 |
| 04 | GitHub Trending | github.com/trending 日榜 |
| 05 | YouTube | 按上传日期搜索 + 频道最新 |
| 08 | Papers | arXiv cs.AI/cs.LG/cs.CL 最新 |
| 09 | Issue Monitor | 仅在有数据时渲染 |

## 两条硬规则（踩过坑）

1. **HN / GitHub Trending / Papers 的摘要必须 60–220 个汉字**。渲染器的安全清洗器会
   按 `minimum_cjk=60, maximum_cjk=220` 过滤，不在范围内会被整段丢弃，页面上只剩标题。
2. **摘要里不能出现「提示词」「输入 json」「输出要求」等词**——会被当成 prompt 回显过滤掉。

## 版式一致性

`verify_parity.py` 会比对本站与线上主站的 `<style>` 块：必须逐字节相同。
主站改版后跑 `./sync_renderer.sh` 同步渲染器，再重建即可跟上。
