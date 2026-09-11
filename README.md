# Latest Model News — AI 模型发布追踪器

每 30 分钟抓取 OpenAI / Anthropic / Qwen / DeepSeek 官方动态、HuggingFace / ModelScope 新模型、
OpenRouter 新上线、GitHub Releases、Reddit r/LocalLLaMA 与 Hacker News，
用 DeepSeek 判断「新模型发布 / 权重开源 / 重大版本升级」硬事件，通过 Server酱 推送到微信。

## 工作原理

GitHub Actions 每 30 分钟运行一轮：
抓取（10 个独立源，单源失败不影响其他）→ 去重（`state/seen.json` 提交回仓库）→
DeepSeek 判断硬事件（失败降级关键词规则，未判定条目下轮重试）→
Server酱 推送（多条合并一条，失败下轮重推）→ 事件追加到 `events.md`。

首次运行仅记录不推送（bootstrap，防止历史内容刷屏）。

## 部署

1. 在 GitHub 创建**公开**仓库并推送本项目（公开仓库 Actions 免费不限时）
2. 仓库 Settings → Secrets and variables → Actions 添加：
   - `DEEPSEEK_API_KEY` — [DeepSeek 开放平台](https://platform.deepseek.com/) 申请
   - `SERVERCHAN_SENDKEY` — [Server酱](https://sct.ftqq.com/) 微信扫码后获取
3. Actions 页面手动触发一次 `track-model-news`（bootstrap），之后每 30 分钟自动运行
4. 微信扫码关注 Server酱 的「方糖」服务号，消息才会送达微信

## 本地调试

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY / SERVERCHAN_SENDKEY
DRY_RUN=1 python -m src.run
python -m pytest tests/ -v
```

本地被墙的源（HF/Reddit/HN）会打印 FAILED 并跳过，不影响其他源。

## 调整追踪范围

`src/config.py`：`HF_ORGS`（HuggingFace 组织）、`MS_KEYWORDS`/`MS_ORG_MAP`（ModelScope）、
`GH_REPOS`（GitHub 仓库）、`HN_QUERIES`（HN 搜索词）。

## 成本

- GitHub Actions：公开仓库免费
- DeepSeek：约 ¥5-10/月（无新条目时不调用）
- Server酱：免费版（每天 5 条额度，多条事件自动合并）

## 常见问题

- **Actions 定时任务停了？** GitHub 对 60 天无提交的仓库停用 schedule；本项目每 30 分钟提交状态，不受影响。手动触发一次即可重新启用。
- **漏推了事件？** 判断标准偏严格（只推硬事件）。可调整 `src/judge.py` 的 SYSTEM_PROMPT 放宽。
