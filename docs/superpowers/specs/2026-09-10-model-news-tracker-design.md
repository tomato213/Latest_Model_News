# AI 模型发布追踪器 — 设计文档

日期：2026-09-10
状态：已确认

## 目标

自动追踪热门 AI 模型的发布/开源动态，事件触发实时推送到微信。用户在事件发生后 1 小时内收到「XX 模型发布新版本 / 权重开源」的通知。

## 已确认的决策

| 决策点 | 选择 |
|---|---|
| 推送渠道 | 微信，Server酱（免费版，每日 5 条额度） |
| 运行环境 | GitHub Actions 公开仓库，cron 每 30 分钟 |
| 信息源 | 官方博客 + HuggingFace + 社区热帖 + 国内模型动态 |
| 推送标准 | 只推硬事件：新模型发布、权重开源、重大版本升级 |
| 事件判断 | DeepSeek 官方 API（deepseek-chat），用户自购 API Key |
| 状态持久化 | `state/seen.json` 提交回仓库 |

## 架构

```
GitHub Actions (每30分钟 cron, 公开仓库免费不限时)
    │
    ├─ ① 抓取器 × N (每个信息源一个独立模块，互不影响)
    │      → OpenAI RSS / Anthropic /news / Qwen RSS / DeepSeek 文档站
    │      → HuggingFace API (追踪的组织新模型) / ModelScope / GitHub Releases
    │      → Reddit r/LocalLLaMA RSS / Hacker News Algolia API
    │      全部输出统一的「候选条目」格式
    │
    ├─ ② 去重 (state/seen.json 提交回仓库，持久化已见条目)
    │
    ├─ ③ LLM 事件判断 (DeepSeek 官方 API, deepseek-chat)
    │      只对「新条目」批量调用一次：判断是否硬事件
    │      (新模型发布/新版本开源/重大版本升级)，输出结构化 JSON
    │      └ API 失败时降级为关键词规则，未判断条目下轮重试
    │
    └─ ④ Server酱 推送到微信 (Markdown 模板，一次运行合并为一条消息)
           └ 推送失败的事件保持 pending，下轮重试
```

## 数据源（已验证可达性）

| 来源 | 方式 | 状态 |
|---|---|---|
| OpenAI | RSS `openai.com/news/rss.xml` | ✅ 已验证 |
| Anthropic | 解析 `/news` 页面文章 slug | ✅ 已验证 |
| Qwen | RSS `qwenlm.github.io/blog/index.xml` | ✅ 已验证 |
| DeepSeek | 文档站/新闻页解析 | 待实现时确认 |
| HuggingFace | API 追踪指定组织的新模型 | ✅ Actions 上可达（本地被墙） |
| ModelScope | API/页面解析 | ✅ 已验证 |
| GitHub Releases | API 追踪指定仓库 | 标准公开 API |
| Reddit r/LocalLLaMA | RSS | ✅ Actions 上可达 |
| Hacker News | Algolia API | 标准公开 API |

## 候选条目格式

```json
{
  "id": "<源内唯一ID，用于去重>",
  "source": "openai|anthropic|qwen|deepseek|hf|modelscope|github|reddit|hn",
  "title": "条目标题",
  "url": "原文链接",
  "published_at": "ISO8601 时间或 null",
  "extra": "给 LLM 判断用的补充上下文（如 HF 的 downloads/likes、HN 的分数）"
}
```

## 硬事件标准

- 新模型发布（闭源 API 模型上线）
- 权重开源（开源权重发布）
- 重大版本升级（大版本号变更、能力代际提升）

不推：榜单变化、评测文章、行业新闻、rumor、小版本修复。

## 事件判断

- 只对去重后的「新条目」调用一次 DeepSeek（deepseek-chat），批量判断，输出结构化 JSON
- Prompt 要求：返回每条是否为硬事件、事件类型、1-2 句中文摘要
- API 失败时降级为关键词规则；未判断条目保持 pending 下轮重试
- 无新条目时跳过 LLM 调用（零成本）

## 推送

- Server酱 Markdown 模板，一轮内多条事件合并为一条消息
- 推送失败的事件保持 pending，下轮重试
- 免费版每日 5 条额度：正常事件量（全球每日 0-5 个硬事件）足够

## 状态与错误处理

- `state/seen.json`：已见条目 ID 集合 + pending 事件队列，每轮结束提交回仓库
- concurrency 串行化，避免并行运行冲突
- 任何抓取源失败 → 记日志跳过，不影响其他源和推送
- LLM 调用失败 → 关键词规则兜底 + 原文下轮重判
- 推送失败 → 事件标记 pending，下轮重推

## 仓库结构

```
Latest_Model_News/
├── .github/workflows/track.yml      # 定时任务入口
├── src/
│   ├── sources/                     # 每个源一个模块 + 统一基类
│   ├── judge.py                     # LLM 事件判断
│   ├── notify.py                    # Server酱 推送
│   ├── state.py                     # 去重存储
│   └── run.py                       # 主编排
├── state/seen.json                  # 已见条目（自动提交回仓库）
└── tests/                           # 单测（fetcher 用录制的 fixture）
└── .env.example
```

## 需要用户配置的 Secrets

- `DEEPSEEK_API_KEY` — DeepSeek 官方 API Key
- `SERVERCHAN_SENDKEY` — Server酱 SendKey

## 本地调试

- `.env` 配置密钥；本地被墙的源（HF/Reddit）独立 try/except 静默跳过，不阻塞其他源

## 成本

- GitHub Actions：公开仓库免费
- DeepSeek：估算 ¥5-10/月
- Server酱：免费版
