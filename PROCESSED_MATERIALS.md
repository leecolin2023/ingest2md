# 处理后材料归档说明（2026-10-26）

`ingest2md/output/` 保持原样，仍是素材的来源与转写底稿。本次仅将更高层的加工产物（Transcript Refinement、Deep Read、Learning）按主题移交到知识仓库：

- AI 及其技术实践、RAG、模型服务、Agent、AI 求职材料： [HarnessLab/materials](https://github.com/leecolin2023/HarnessLab/tree/main/materials)。[完整映射清单](https://github.com/leecolin2023/HarnessLab/blob/main/materials/_migration/MIGRATION_MANIFEST.json)。
- 商业与生活材料： [knowledge-archive](https://github.com/leecolin2023/knowledge-archive) 的 `business/`、`life/`、`inbox/`。[完整映射清单](https://github.com/leecolin2023/knowledge-archive/blob/main/MIGRATION_MANIFEST.json)。

首次历史及本轮新产物的迁移清单共 195 条：HarnessLab 186 条、knowledge-archive 9 条（包含部分说明文件与历史索引，不等于不同原稿的数量）。原始来源快照的 Git commit 通过上述映射清单的 `source_commit` 字段追溯，逐文件记录源路径、目标路径以及迁移前后 SHA-256 校验值。

目标材料保存于原始素材标题命名的子目录中，分别使用 `refinement.md`、`deep-read.md`、`learning.md` 命名。原 `../output/` 相对链接已替换为 GitHub 原稿链接。保留旧版源码历史，供必要时找回之前的处理目录。

今后先将新素材保存到 `output/`，再独立加工并按主题保存到对应知识仓库，不再把二次加工材料沉淀在采集仓库中。

## 增量归档（2026-10-26）

再次归档 `output-Learning/` 的 20 份新增文件（10 组 Deep Read + Learning）：

- 16 份技术学习与 AI 求职材料已归入 [HarnessLab/materials](https://github.com/leecolin2023/HarnessLab/tree/main/materials)，按模型服务、RAG、Agent、AI Career 分类。
- 4 份经济与企业经营资料已归入 [knowledge-archive/business](https://github.com/leecolin2023/knowledge-archive/tree/main/business)。

累计迁移处理文件 **195** 份，其中 HarnessLab **186** 份（含首次迁移的 2 份历史管理文件），knowledge-archive **9** 份。映射清单内新增条目记有各自的 `source_commit`，并记录源与目标 SHA-256。迁移采取先写目标、核对相同 Git blob SHA、后删除源文件的顺序。

## 加工状态的持续维护

原稿保留在 `output/`；状态映射集中登记在 `output/processing-status.json`，全量可读清单位于仓库根目录 `PROCESSING_INDEX.md`，采集索引 `output/sources.md` 新增“是否已精读”列。

每次使用 Skill 完成新内容后，先将派生文稿提交到 HarnessLab 或 knowledge-archive，确认目标文件存在，然后更新 JSON 中对应原稿的 `source` 与 `method`：Refinement 须填写 `refinement` URL，DeepRead + Learning 须同时填写 `deep_read` 和 `learning` 两个 URL。然后运行：

```bash
python -m ingest2md.processing_status --output-dir output
```

新采集内容默认标记“否”，已有内容重新采集不会清除同路径原有“是”。跨仓库写入不是原子事务，务必先确认目标产物再更新状态；该字段仅表示对应 Skill 产物完成归档，不保证人工音频校对或独立 Review 隔离验收。
