# 处理后材料归档说明（2026-10-26）

`ingest2md/output/` 保持原样，仍是素材的来源与转写底稿。本次仅将更高层的加工产物（Transcript Refinement、Deep Read、Learning）按主题移交到知识仓库：

- AI 及其技术实践、RAG、模型服务、Agent、AI 求职材料： [HarnessLab/materials](https://github.com/leecolin2023/HarnessLab/tree/main/materials)。[完整映射清单](https://github.com/leecolin2023/HarnessLab/blob/main/materials/_migration/MIGRATION_MANIFEST.json)。
- 商业与生活材料： [knowledge-archive](https://github.com/leecolin2023/knowledge-archive) 的 `business/`、`life/`、`inbox/`。[完整映射清单](https://github.com/leecolin2023/knowledge-archive/blob/main/MIGRATION_MANIFEST.json)。

迁移文件合计 175 个：HarnessLab 170 个（含原处理索引和说明 2 份）、knowledge-archive 5 个。原始来源快照的 Git commit 通过上述映射清单的 `source_commit` 字段追溯，逐文件记录源路径、目标路径以及迁移前后 SHA-256 校验值。

目标材料保存于原始素材标题命名的子目录中，分别使用 `refinement.md`、`deep-read.md`、`learning.md` 命名。原 `../output/` 相对链接已替换为 GitHub 原稿链接。保留旧版源码历史，供必要时找回之前的处理目录。

今后先将新素材保存到 `output/`，再独立加工并按主题保存到对应知识仓库，不再把二次加工材料沉淀在采集仓库中。
