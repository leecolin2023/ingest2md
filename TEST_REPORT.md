# ingest2md v0.8.3 Test Report

测试日期：2026-09-19

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
34 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

默认 batch 调整后的 PR CI run：

```text
35413320927
```

## v0.8.3 SenseVoice 本地性能优化

本版只优化本地 SenseVoice 路径，不改变字幕优先、ASR backend 选择或 Markdown 输出结构。

1. SenseVoice 默认切片从 20 秒调整为 **30 秒**；
2. 默认 `sensevoice_batch_size` 从 1 调整为 **2**，优先兼顾普通 8 GB 级 Windows 笔记本的稳定性；
3. 推理改为真正的多文件 batch 调用，不再只是初始化模型时传入 batch_size 后仍逐片调用；
4. 30 秒 WAV 切片改为单次 ffmpeg segment，避免按 chunk 重复启动进程；
5. 新增 `--sensevoice-batch-size`，资源余量较大的机器可显式尝试 `4`；
6. 增加 preprocess / model setup / inference / total / model_calls / realtime speed / RTF 性能日志；
7. `local-asr` extra 增加 `onnxscript`，降低首次 ONNX 导出阶段缺依赖失败的概率。

默认配置：

```yaml
sensevoice_chunk_seconds: 30
sensevoice_batch_size: 2
sensevoice_quantize: true
```

## 新增回归

在 v0.8.2 的 32 项基础上新增 2 项：

- 5 个 chunk、batch=2 时必须只调用模型 3 次（2 + 2 + 1），并保持 5 个 Segment 的文本与时间顺序不变；
- SenseVoice WAV 分段必须通过单次 ffmpeg segment 调用完成。

因此当前：

```text
34 passed
```

## 保持不动的边界

本版刻意没有引入：

- 音频/ASR 持久缓存；
- GPU / CUDA 路径；
- ONNX Runtime 线程调优；
- VideoSubtitleMixin；
- ASR backend 公共 pipeline；
- 对 OpenAI / LLM MP3 切片行为的改变。

其中 batch=4 仅作为更高资源机器的手动 benchmark 选项，不作为公共默认值。

## CI 边界

基础 CI 不下载真实 SenseVoiceSmall 模型，也不执行真实长音频性能 benchmark；当前测试验证 batch 契约、顺序保持、单进程 WAV segmentation 和既有功能回归。真实速度与内存占用仍需在目标机器上用同一段音频比较 batch=2 / 4。
