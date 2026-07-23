# 健康档案 UX 体检表

> **最后体检日期**: 2026-07-22
> **下次体检触发**: 累积 3 项 ✓ 后, 或用户反馈"开发太乱"时
> **总项数**: 16 / 10 (上限突破, 见 #11 #12 #13 #14 #15 #16 附加)

## 进度总览

- ✅ 已完成: 8 项 (#1, #7, #11, #12, #13, #14, #15, #16)
- ❌ 待办: 8 项

---

## 高严重度 (用户立刻能感觉到)

### ✅ #1 统计卡片排列乱 (2026-07-21 完成)

- **现象**: 之前 5 个统计卡片 xs=6/md 模式在小屏出现 2x2 + 1, 留大块空白
- **修法**: 用 `display: grid; grid-template-columns: { xs: "1fr 1fr", sm: "repeat(5, 1fr)" }` 改成 5 等分
- **commit**: `refactor(v2): 统计卡片 5 等分排列`

### ✅ #7 列表卡片摘要提主次 (2026-07-21 完成)

- **现象**: 卡片摘要直接 OCR 前 140 字, 首段是 `病理号: 病人编号: 报告状态: ...` 一堆冒号
- **修法**: 加 `extractPreview()` 优先命中"临床诊断/病理诊断/肉眼所见/镜下所见/诊断"等关键 KV
- **commit**: `refactor(stage48-22 v6): 列表卡片 #1 体检整改`

---

## 中严重度 (影响观感)

### ❌ #2 头部紧凑

- **现象**: "健康档案"标题 + "共 17 条记录" + "刷新/新增档案" 按钮 — 分两行不紧凑
- **建议**: Stack direction="row" justifyContent="space-between" + 缩小按钮 size
- **优先级**: 中 (等下一轮验收 #7 后再做)

### ❌ #4 智能助手按钮缩小

- **现象**: 右下角蓝色圆形 FAB 按钮, 太大太抢眼, 把用户视线吸走
- **建议**: 缩小 + 半透明 + 移到右下角边缘更深处
- **优先级**: 中

### ❌ #8 OcrSummaryBlock 顶卡片

- **现象**: 详情弹窗基础页顶部"✏️ 从附件自动识别 · 400 字 [查看正文]" 头部跟按钮分两行不紧凑
- **建议**: 同 Row + spacing 1, 字号统一 caption
- **优先级**: 中

---

## 低严重度 (开发者自查)

### ❌ #3 头像 + 警示数

- **现象**: 顶部 "1111 1" — 用户名 + "1" 警示 pill, 视觉不统一
- **建议**: 合并到头像 Badge 或去掉 pill
- **优先级**: 低

### ❌ #5 顶部 header 调浅

- **现象**: 蓝色 #1976d2 太亮, 跟下面白色卡片对比突兀
- **建议**: 用主题色 alpha 0.7 调浅
- **优先级**: 低

### ❌ #6 搜索 vs 标签栏间距

- **现象**: 搜索框跟下方"全部/诊断/检查..." 间距大, 中间留空
- **建议**: 减少间距 16 → 8
- **优先级**: 低

### ❌ #9 列表卡片附件数字号

- **现象**: "2026-07-20 · 1 个附件" 日期跟附件数字号不统一
- **建议**: 同一 caption, 不变
- **优先级**: 低

### ❌ #10 Tab 文字对齐

- **现象**: "正文" 跟 "附件 (1)" 文字大小不齐
- **建议**: `<Tabs>` 用 sx={{ minHeight: 36 }}, `<Tab>` 用 sx={{ minHeight: 36, padding: '6px 16px' }}
- **优先级**: 低

---

## 待办优先级 (下一轮该走)

按"严重度 + 容易实现"综合排序:

1. **#2 头部紧凑** (中, 10 行 CSS)
2. **#4 智能助手按钮缩小** (中, 5 行 CSS)
3. **#8 OcrSummaryBlock 顶卡片** (中, 20 行)
4. **#5 顶部 header 调浅** (低, 5 行)
5. **#3 头像 + 警示数** (低, 改 1 个组件)
6. **#6 搜索间距** (低, 1 个常量)
7. **#10 Tab 对齐** (低, 改 Tabs sx)
8. **#9 列表附件数字号** (低, 改 1 个 sx)

> **触发**: 用户说"继续" → 一次改 1-2 项 → 验收 → 继续.

---

## 附加发现 (会话 2 启动后)

### ❌ #11 Login 响应形状不对齐 (2026-07-22, 阻塞)

- **现象**: 输入正确用户名密码后, 一直显示"登录失败", 即便 backend 200 OK
- **真因**: `Login.jsx` 期望 `{success, user:{id, username, email}, token}` 形状, 但 backend 实际返回 `{access_token, user:{user_id, ...}, token_type}`; 同时 `localStorage` 用了错误 key (`healthToken` 而非 `token`), 导致 `AuthContext.checkAuth()` 验证失败, 重定向回 login
- **修法**: `Login.jsx` handleSubmit 改读 `response.access_token` 和 `response.user.user_id`, localStorage 改用统一 key `token`; 加一个 `useEffect` 自动从 `?u=&p=` URL param 登录方便开发测试
- **优先级**: 高 (阻塞任何用户登录)

### ❌ #12 附件上传 404 (2026-07-22, 阻塞)

- **现象**: 新建健康档案页, 选择文件后弹 "HTTP 404, Not Found"
- **真因**: 前端 `HealthUploader.jsx` 调 POST `/v2/upload/file`, 但 `frontend/hostAgentAPI/api.py` 没 mount 这个 router. `A2AServer/v2/upload_pipeline.py` 里有 router, 但从未被 include. 同时 `/api/health-records/upload` (单文件) 工作 — 这是另一条路径, 老 upload 单条 + OCR
- **修法**: 在 hostapi.py 里加一段 `from A2AServer.v2.upload_pipeline import router as v2_upload_router; app.include_router(v2_upload_router)`, rebuild hostapi 镜像, recreate 容器. 之后 `/v2/upload/file` 返回 200 + file_id + queued OCR
- **优先级**: 高 (阻塞文件上传和 OCR 自动入库)

### ❌ #13 单步创建健康档案 404 (2026-07-22, 阻塞)

- **现象**: 点"新增健康档案 → 填好点保存" 后, 弹 "one-step create failed: 404 Not Found"
- **真因**: 前端 `HealthRecordForm.jsx` 调 POST `/api/v2/create-record-and-attach` (用 user_id query param). backend `A2AServer/v2/record_create_api.py` 里有 router = APIRouter(prefix='/api/v2'), 但跟 #12 一样, hostapi 没 mount 这个 router. 同文件里还有 PUT `/api/v2/update-record-and-attach` (编辑用), 也未 mount
- **修法**: hostapi.py 在 v2_upload_router 之后, registry_router 之前, 再加一段 `from A2AServer.v2.record_create_api import router as v2_record_create_router; app.include_router(v2_record_create_router)`. rebuild + recreate. 现在 `/api/v2/create-record-and-attach?user_id=...` POST 200, 返回 record_id, attached_count=0
- **优先级**: 高 (阻塞任何新建/编辑健康档案动作)

### ❌ #14 附件图片看不见 (2026-07-22, 阻塞)

- **现象**: 健康档案页附件列表显示 "1" 但点击/缩略图看不到实际图片
- **真因**: 前端 `getAttachmentUrl()` 生成 `/v2/files/<file_id>`, 这是 `static file serve`. backend `A2AServer/v2/upload_pipeline.py` 里定义了 `file_router = APIRouter(prefix='/v2/files')` + `@file_router.get('/{file_id}')` serve_file(), 但跟 #12 #13 一样, hostapi 也没 mount 这个 router
- **修法**: hostapi.py 在 v2_record_create_router 后, registry_router 前, 再加一段 `from A2AServer.v2.upload_pipeline import file_router as v2_file_router; app.include_router(v2_file_router)`. 现在 `/v2/files/<file_id>` GET 返回 200 + 内容 (curl 验过)
- **优先级**: 高 (图片/附件不可见)
- **附带 OCR 问题**: Qwen-VL 报告 "The image format is illegal" 只对真 PNG/JPG 触发. 如果你传的是合法图片, OCR 会被处理并入 `uploaded_files.ocr_text`. 前端轮询 `/v2/upload/files/<fid>/parsed?user_id=...`, 200 + `parsed` + `raw_text`(取前 5000 字). OCR 是异步, 几条后过, 直接刷新页面重试即可.

### ❌ #15 OCR 处理中页面无反馈 (2026-07-22, UX)

- **现象**: 上传文件提交后, OCR 要 5-15 秒. 这期间前端表单返回成功, 但页面"什么也没有", 用户不知道系统是在跑, 还是在卡. 健康档案页 (HealthRecords.jsx) 列表加载后, OCR 还没完成的附件连进度条都没有, user 必须在原地干等
- **真因**: HealthRecords.jsx 老页面是阶段 28 的实现 — 顶层列表 fetch 完后即使用户看到附件 `ocr_status='pending'`, 也没有任何横幅/进度条. 后端 OCR 是异步 background task, 完成后 update 数据库. user 看不到状态变化, 必须手动刷新
- **修法**: (1) 在 `<Header><Container>` 之间加一个 OCR 进度横幅. `records.some(r => r.files.some(f => f.ocr_status && !['done','failed','skipped'].includes(f.ocr_status)))` 时渲染: warning 色横幅 + CircularProgress spin + "X 个待处理" 计数 + 一句话文案 (1 行). (2) 加 `useEffect` 监听 records 变化, 任意 pending 时启动 5 秒 setInterval 调 fetchRecords, 全部 done/failed/skipped 时 clearInterval. (3) vite dev server 因长时间构建后死了, 重启 vite
- **优先级**: 中 (UX, 不阻塞功能, 但体验差)

### ❌ #16 OCR 横幅不显示 (2026-07-22, 阻塞)

- **现象**: 用户刷新后没看到 "正在识别附件内容" 横幅 (上一步 #15 加的)
- **真因 (双层)**:
  - **OCR 极快**: 真 PNG 只需 1-2 秒; 小测试 PNG 直接 `skipped`. 用户大图上传可能也 < 5s. 横幅只在 pending/running 时显示, 但自然 stale 等不到
  - **错误数据源**: #15 我代码里读 `record.files[i].ocr_status`, 但实际数据 `ocr_status` 在 **`record.metadata._attached_files_meta[i].ocr_status`**. `toUiRecord()` 只取 `r.files || r.file_attachments || r.metadata.files` (都是空的或者只含字符串 file_id), 永远拿不到 `ocr_status`
- **修法**: 重写 `toUiRecord()`, 优先 `record._attached_files_meta` (数据库 merge 后真实来源), 把每个 file 项 normalize 成 `{file_id, name, mime_type, ocr_status, ocr_text, public_url}`. 横幅判断还是同样 ocr_status. 这次 OCR 跑时就能看到横幅; OCR 完成的也能从 metadata 拿到 ocr_text 字段
- **优先级**: 高 (横幅不显示, #15 等于没修)

---

## 用户视角原则检查 (这一页)

| 原则         | 健康档案页        | 详情弹窗                  |
| ------------ | ----------------- | ------------------------- |
| 0 程序员术语 | ✅ (已清理)       | ✅ (已清理)               |
| 0 状态暴露   | ✅ (列表卡片已删) | ⚠️ "已存档 N 字" 还在底部 |
| 0 中间按钮   | ✅ (无 OCR 按钮)  | ✅ (无 OCR 按钮)          |

> **下一轮**: 把详情弹窗底部"已存档 N 字 (顶部和正文 Tab 都能看到内容)"也删了, 用户不需要被告知"内容已经被存档".
