# ingest2md v0.9.2 Test Report

测试日期：2026-09-21

## 结果

GitHub Actions 在 Python 3.10 与 3.12 均通过：

```text
51 passed
```

执行链路：

```bash
python -m pip install -e ".[test]"
python -m compileall -q ingest2md
python -m pytest -q
ingest2md --help
```

首轮 Scanner CI run：

```text
35560835240
```

## v0.9.2 Free-text Reference Scanner

TXT batch manifest 从严格的“一行一个任务”升级为自由文本输入：

1. `urlutils.extract_references(text)` 按原文顺序扫描全部 http/https URL 与 Bilibili BV 号；
2. 同一物理行可以拆出多个 BatchItem；
3. 精确重复引用保留第一次；
4. URL 内部出现的 BV id 不会被重复拆成第二个任务；
5. URL 继续做保守的尾部中英文标点清理；
6. TXT 中独占一行的现有本地文件继续支持，并按 manifest 所在目录解析相对路径；
7. 独占一行的裸域名继续兼容；
8. 没有 Reference 的普通说明文字直接忽略；
9. CSV / JSONL 保持原有严格结构化语义。

## 回归重点

新增/增强测试覆盖：

- 任意分享文字中混合 URL + BV 的顺序扫描；
- 同一行连续多个 URL 拆成多个任务；
- 空行不影响拆分；
- 多个任务来自同一行时保留相同行号；
- 本地文件与裸域名兼容；
- prose-only 文本不会生成伪 URL；
- Bilibili URL 中嵌入的 BV id 不重复生成任务。

## 保持不变的边界

- Scanner 只负责 Content Reference 发现，不判断来源平台；
- Router / Adapter 完全不感知 TXT 如何排版；
- SQLite 继续负责规范化后的任务级去重、resume 与失败状态；
- RuntimeContext / SenseVoice / BrowserRuntime 不受本次修改影响；
- 不引入抖音专用批量解析规则。

这样 TXT 可以作为低门槛的“随手粘贴区”，CSV/JSONL 则继续承担结构化任务清单角色。
