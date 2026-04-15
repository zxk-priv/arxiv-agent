# 缓存布局说明

## 当天论文缓存

```text
output/daily/cs_cv_latest.md
output/daily/cs_cv_YYYY-MM-DD.md
```

用途：

- 保存最新一天抓取到的论文基础信息
- 给两种推荐模式共用

## 偏好分析缓存

```text
output/preferences/profile_latest.md
```

当前实现中，`profile_latest.md` 会同时包含：

- 所有单篇 PDF 的结构化偏好条目
- 聚合后的整体研究偏好

## 最终推荐结果缓存

```text
output/results/keyword_latest.md
output/results/preference_latest.md
```

分模式存储的原因是：

- 关键词模式和偏好模式来源不同
- 便于回看
- 避免结果文件相互覆盖

## 为什么缓存全部使用 Markdown

原因有两个：

1. 人可以直接打开看
2. 程序也可以稳定解析

这比只存 JSON 更适合本项目的“调试 + 面试展示 + 本地可读性”目标。
