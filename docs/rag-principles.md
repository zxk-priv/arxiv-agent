# 双模式 RAG 原理

当前工程不是单一路径的“关键词搜论文”工具，而是两条推荐流共用同一套当天论文缓存：

1. 关键词模式
   - 输入 query
   - 对当天最新论文做混合检索
   - 对命中论文生成中文总结

2. 论文库偏好模式
   - 读取 `paper_datasets/` 里的 PDF
   - 先总结研究偏好
   - 再把偏好转换成检索 query
   - 用同一套 RAG 检索当天论文

## 共用的数据底座

- 当天论文缓存：`output/daily/cs_cv_latest.md`
- 偏好画像缓存：`output/preferences/profile_latest.md`
- 推荐结果缓存：
  - `output/results/keyword_latest.md`
  - `output/results/preference_latest.md`

这三类缓存的作用分别是：

- 当天论文缓存：保存标题、摘要、PDF 链接、HTML 链接
- 偏好画像缓存：保存 PDF 论文库的结构化兴趣画像
- 推荐结果缓存：保存最终推荐结果和中文总结

## 检索粒度

当前 RAG 没有对当天论文做 chunking，而是：

- 一篇论文 = 一个检索文档
- 文档内容 = `标题 + 英文摘要`

这样做的原因是当前目标是“找相关论文”，不是“定位长文中的某一段”。

## embedding 模型

当天论文索引用的是 SiliconFlow 的 OpenAI 兼容 embedding 接口，默认配置：

```env
SILICONFLOW_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-4B
```

## 向量库

当前使用的是 `FAISS`，不是 `Chroma`。

原因很直接：

- 每天论文只有几百篇
- 本地单机足够
- 依赖更轻
- 配合 LangChain 的接入更简单

## 检索流程

当前不是“BM25 + 向量检索”的标准混检，而是：

1. 先做向量召回
2. 再做轻量关键词加分
3. 最后做混合排序

### 向量阶段

- query 先做 embedding
- 用 FAISS 找相似文档
- 候选数默认取 `top_k * 4`
- 默认最终 `top_k = 20`
- 所以向量候选默认最多取 `80`

### 关键词阶段

关键词不是 BM25，而是启发式规则：

- 完整 query 命中标题：`+12`
- 完整 query 命中摘要：`+5`
- token 命中标题：每个 `+3`
- token 命中摘要：每个 `+1`

### 混合分数

最终总分：

```text
total_score = vector_score * 10 + keyword_score
```

然后按总分排序，返回前 `20` 篇。

## 偏好模式怎么接入 RAG

偏好模式不是“拿 PDF 全文直接做检索”，而是两步：

1. 先把 PDF 论文库归纳成偏好画像
2. 再把偏好画像转成英文检索 query

也就是说，偏好模式实际调用 RAG 时，仍然是：

```text
preference_profile.retrieval_query -> RAG -> latest daily papers
```

这样做的优点是：

- 解释性更强
- 缓存更稳定
- 成本低于“偏好库全集对当天全集做集合相似度”

## 命中结果如何映射回论文

每个检索文档的 metadata 里都会带：

- `arxiv_id`
- `title`
- `pdf_url`
- `html_url`
- `abs_url`

所以命中文档后，系统可以通过 `arxiv_id` 回到当天 digest 中找到原始论文对象，再补中文总结并展示成卡片。

## 为什么这套方案适合面试讲解

因为它把工程问题拆得很清楚：

- 缓存层：怎么保证重复运行不浪费 token
- 偏好分析层：怎么把 PDF 论文库转成研究兴趣画像
- 检索层：怎么把 query / 偏好画像映射到当天论文
- 展示层：怎么把结果以可解释卡片形式输出

如果面试官问“为什么不是更复杂的 RAG”，最合理的回答是：

> 当前项目优先解决的是“小规模本地缓存 + 高可解释性 + 低重复成本”的问题，所以选择了更轻量的 FAISS + 混合排序 + Markdown 缓存方案；如果场景升级到全文级问答或大规模文档库，再引入 BM25、chunking、reranker 或向量数据库会更自然。
