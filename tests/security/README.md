# 安全回归门禁（Security Gates）

这里放**安全不变式**的回归测试。它们和产品测试的性质不同：

| | 产品测试 | 安全门禁 |
|---|---|---|
| 守住什么 | 功能没坏 | **攻击面没重新打开** |
| 失败意味着 | 有 bug | **有洞** |
| 能不能靠改测试让它变绿 | 能（那就是它没测到点子上） | **不能** |
| 谁维护 | 功能开发 | 安全 |

所以这里每个文件都是 `tests/` 里的 `test_*.py`，但同时支持两种跑法：

```bash
python tests/security/test_authz_idor.py    # 独立运行，退出码即结论（CI 用这个）
pytest tests/security/test_authz_idor.py    # pytest 收集
```

**零外部依赖**：不碰 DB / 网络 / LLM / pytest 本身，毫秒级跑完。
门禁一旦需要起数据库，就等于门禁迟早会被人 skip 掉。

---

## 当前门禁

### `test_authz_idor.py` — 身份越权（IDOR）

守的不变式：

1. 身份不可被请求体覆盖（`body.user_id` 无效）
2. 身份别名同样无效（`uid` / `userId` / `sub`）
3. 客户端元数据只有白名单 key 能进
4. 没有已认证身份就拒绝（fail-closed，不许退到 `default_user`）
5. 两处入口必须走单一收口模块（结构守卫，防止有人绕过它自己写一遍）

对应漏洞：**F-001 / F-002 / F-003 / F-012**

漏洞与修复的完整记录在 llm-security-lab 仓库：
<https://github.com/13139531101/llm-security-lab>

---

## 红 → 绿：怎么证明一个门禁是有效的

一个**从来没有红过**的测试，不能证明任何修复 —— 它可能只是在测一个恒真的东西。
所以每个漏洞都留一对 tag，两端跑同一条命令：

```bash
git checkout vuln-001  && python tests/security/test_authz_idor.py   # 红
git checkout fixed-001 && python tests/security/test_authz_idor.py   # 绿
```

同一份测试文件、同一条命令、两种结果。这就是修复有效性的唯一可信证明。

CI 里也配了 `tags: ['vuln-*', 'fixed-*']`，所以 **Actions 历史里能看到这次红→绿**，
而不是只有一句"已修复"。

---

## 加新门禁的规矩

1. **先让它红。** 写完测试先在有漏洞的代码上跑，确认它 FAIL。
2. **失败信息要能自解释。** 断言消息里直接写"期望什么、实际是什么"，
   不要只写 `assert False` —— 看 CI 日志的人不知道你要什么。
3. **零外部依赖。** 起不了数据库就别写在这个目录，另想办法。
4. **先在 security-lab 分支做**，出了 `vuln-XXX` / `fixed-XXX` 一对 tag，
   再把修复带回产品分支。
5. **进 CI 就是阻塞的**（`continue-on-error: false`）。
   非阻塞的门禁等于没有门禁。
