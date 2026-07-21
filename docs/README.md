# docs/ - 项目文档索引

> **从这次对话起, 任何"开发模式 / UX 原则 / 待办优先级"都要先写文档, 再写代码.**

---

## 📋 三份核心文档 (按重要性)

1. **[USER_PERSPECTIVE_PRINCIPLES.md](USER_PERSPECTIVE_PRINCIPLES.md)** ⭐
   > 写 UI 时**必须过一遍**的 3 条铁律: 0 程序员术语 / 0 状态暴露 / 0 中间按钮.
   > 含反例库, 看到 ❌ 立刻知道怎么改.

2. **[DEVELOPMENT_RHYTHM.md](DEVELOPMENT_RHYTHM.md)** ⭐
   > "集中重整 + 验收" 4 阶段流程. 不东改一点西改一点.

3. **[HEALTH_RECORDS_UX_AUDIT.md](HEALTH_RECORDS_UX_AUDIT.md)**
   > 健康档案页的体检表 (10 项, 含严重度, 待办优先级).
   > 每改一项 ✓ 一项. 改完所有高/中严重度后再重新体检.

---

## 怎么用

### 接到新反馈时

```
1. 打开 HEALTH_RECORDS_UX_AUDIT.md
2. 看现在有哪些 ❌ 待办, 用户的反馈跟哪个匹配?
3. 如果匹配 → 选它, 改
4. 如果不匹配 → 加到体检表, 标严重度
5. 改完 → ✓ + commit + 验收
```

### 写新 UI 时

```
1. 打开 USER_PERSPECTIVE_PRINCIPLES.md
2. 扫一遍"体检清单" (5 个是/否)
3. 任意一条答"是, 但必要" → 在体检表里登记
```

### 一段时间后

```
1. 体检表累积到 5+ 项 ✓ 时, 重写一份体检表
2. 把"用户体验阶段"也写进 HEALTH_RECORDS_UX_AUDIT.md 顶部
```

---

## 文档维护规则

- **每次 commit, 如果涉及 UX 改动 → 体检表 +1 ✓**
- **每发现新用户视角原则 → 加进 PRINCIPLES.md**
- **每月扫一遍 3 份文档, 删过时内容, 写新内容**

---

## 文件清单

| 文件 | 用途 | 何时更新 |
|---|---|---|
| `USER_PERSPECTIVE_PRINCIPLES.md` | 3 条铁律 + 反例库 | 发现新原则时 |
| `DEVELOPMENT_RHYTHM.md` | 开发节奏 + 提交模板 | 节奏变化时 |
| `HEALTH_RECORDS_UX_AUDIT.md` | 健康档案体检表 | 每次改 UX 时 |
| `README.md` (本文件) | 文档索引 | 添加新文档时 |