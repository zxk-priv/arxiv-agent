# PDF 偏好分析流程

## 数据源

本地 PDF 论文库目录：

```text
paper_datasets/
```

当前工程会扫描其中所有 `.pdf` 文件。

## 为什么只读前几页

默认只读取前 `N` 页，当前建议值是 `5`。

原因：

- 标题、摘要、引言通常已经足够做偏好判断
- 比读全文更快
- 更不容易被正文噪声影响
- token 成本更低

## 单篇 PDF 分析输出

每篇 PDF 会产出一个结构化条目，包含：

- `paper_title`
- `tech_fields`
- `methods`
- `tasks`
- `zh_summary`

以及缓存需要的文件元信息：

- 文件名
- 文件大小
- 修改时间
- 提取页数

## 为什么缓存单篇 PDF 分析

因为偏好论文库通常不会频繁变化。

缓存后：

- 下次运行时只补新 PDF
- 未变化的旧 PDF 直接复用
- 可以避免重复消耗模型调用

## 整体偏好画像

在所有单篇 PDF 都分析完成后，再做一次汇总，得到：

- `dominant_fields`
- `method_keywords`
- `task_keywords`
- `research_focus_summary`
- `retrieval_query`

其中最关键的是：

- `research_focus_summary`
  - 给人看的，说明“最近在研究什么”
- `retrieval_query`
  - 给 RAG 检索用的英文查询文本
