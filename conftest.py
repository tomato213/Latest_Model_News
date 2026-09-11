import os

# 测试环境兜底：notify.push_events 依赖 SERVERCHAN_SENDKEY 才走推送路径。
# 生产 key 从 .env / CI Secrets 提供；测试只保证存在，不保证真实。
# setdefault：真实环境变量优先，不覆盖。
os.environ.setdefault("SERVERCHAN_SENDKEY", "SCT_test_dummy_key")
