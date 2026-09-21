# Online smoke corpus

这里放的是**平台在线可靠性**测试，不进入普通 GitHub Actions CI。普通 CI 负责工程正确性；这里负责回答另一件事：代码没有坏时，真实平台是否仍然允许当前 Adapter 正常工作。

按需要设置测试源：

```bash
export INGEST2MD_SMOKE_WEB="https://example.com/article"
export INGEST2MD_SMOKE_YOUTUBE="https://www.youtube.com/watch?v=..."
export INGEST2MD_SMOKE_BILIBILI="https://www.bilibili.com/video/BV..."
export INGEST2MD_SMOKE_XIAOYUZHOU="https://www.xiaoyuzhoufm.com/episode/..."
export INGEST2MD_SMOKE_DOUYIN="https://v.douyin.com/..."
export INGEST2MD_ONLINE_CONFIG="./config.yaml"   # 可选：Cookie / ASR / LLM 配置
python -m pytest tests_online -q
```

未设置的来源自动 skip。Cookie 不进入仓库或 CI。

建议每个大版本或平台 Adapter 明显变化时手工跑一次；如果失败，可据此区分“代码回归”与“平台行为变化”。
