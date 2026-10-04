"""AG-UI 端到端冒烟测试：四条关键路径。

只打 /api/copilotkit 这一个入口 —— 那是前端真正用的 AG-UI 端点，
不是 /v2/chat/stream。逐条验证：

  A 正常问答    : 应看到 RUN_STARTED → ... → TEXT_MESSAGE_* → RUN_FINISHED
  B 无 token    : 应收到 RUN_ERROR（带真实错误），而不是"一个字都没有的空回复"
  C 模糊问题    : 应收到 clarification（host_graph 的 clarify 节点）
  D 用药问题    : 应收到 PAGE_UPDATE（生成式 UI / AI 操控页面）
  E 幂等状态    : 应收到 STATE_DELTA，且含 /route 与 /healthRecords/filter
                  （阶段48-31 的 AG-UI 标准状态通道）
  F 事件合规    : 跨所有用例收集到的事件，type 要么在标准白名单里、要么包成 CUSTOM

用法：
    # 宿主机
    python tests/e2e/agui_smoke.py
    # 容器内（同一 docker 网络）
    PROBE_BASE=http://hostapi:13002 python tests/e2e/agui_smoke.py

退出码：A/B/D/E/F 五条硬断言全过才返回 0，便于接进 CI。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.getenv("PROBE_BASE") or "http://localhost:13002"
USERNAME = os.getenv("PROBE_USER") or "probe_agui_1"
PASSWORD = os.getenv("PROBE_PASS") or "ProbePass123!"


def post(path, body, token=None, timeout=300):
    """返回 (status, body, 耗时秒)。耗时是**整轮**——SSE 收完为止，即用户实际等待时间。"""
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace"), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), time.perf_counter() - t0


# 所有解析过的事件都进这里，供 F 用例做**全局**合规检查。
# 放在 parse_agui 内部累加，是为了不用在每个用例后面各加一行 —— 漏加一处就漏检一路。
_ALL_EVENTS = []


def parse_agui(body: str):
    """本项目 SSE 是 AG-UI 风格: 只有 `data: {...}`, 事件类型在 JSON 的 type 字段里"""
    kinds, events = {}, []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            ev = json.loads(line[5:].strip())
        except Exception:  # noqa: BLE001
            continue
        k = ev.get("type", "?")
        kinds[k] = kinds.get(k, 0) + 1
        events.append(ev)
    _ALL_EVENTS.extend(events)
    return kinds, events


def text_of(events):
    return "".join(
        e.get("delta", "") for e in events if e.get("type") == "TEXT_MESSAGE_CONTENT"
    )


# AG-UI 标准事件名白名单 —— 与 copilotkit_runtime._STANDARD_AGUI_EVENTS 同源
# （抄自 @ag-ui/core 0.0.57 的 EventType，去掉 deprecated 的 THINKING_*）。
# 这里存在的意义是**当守卫**：任何裸发的非标准事件都会被 F 用例抓出来。
STANDARD = {
    "RUN_STARTED", "RUN_FINISHED", "RUN_ERROR", "STEP_STARTED", "STEP_FINISHED",
    "TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT", "TEXT_MESSAGE_END", "TEXT_MESSAGE_CHUNK",
    "TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END", "TOOL_CALL_CHUNK",
    "TOOL_CALL_RESULT",
    "STATE_SNAPSHOT", "STATE_DELTA", "MESSAGES_SNAPSHOT",
    "ACTIVITY_SNAPSHOT", "ACTIVITY_DELTA",
    "RAW", "CUSTOM",
    "REASONING_START", "REASONING_MESSAGE_START", "REASONING_MESSAGE_CONTENT",
    "REASONING_MESSAGE_END", "REASONING_MESSAGE_CHUNK", "REASONING_END",
    "REASONING_ENCRYPTED_VALUE",
}


def custom_names(events):
    """取出所有 CUSTOM 事件里包着的 name（如 PAGE_UPDATE）。"""
    return [e.get("name") for e in events if e.get("type") == "CUSTOM" and e.get("name")]


out = []
status, raw, _t = post("/auth/login", {"username": USERNAME, "password": PASSWORD})
if status != 200:
    print(f"登录失败 HTTP {status}: {raw[:300]}")
    raise SystemExit(1)
token = json.loads(raw)["access_token"]
out.append(f"login -> HTTP {status}")

# 每一轮记一次耗时 —— 这是用户真实等待的时间（SSE 收完为止），
# 也是简历上"端到端延迟"唯一有意义的数字。
timings = {}

# ---------------------------------------------------------------- A 正常问答
status, body, elapsed = post("/api/copilotkit", {"message": "我最近血压控制得怎么样？"}, token)
timings["A"] = elapsed
kinds, events = parse_agui(body)
text = text_of(events)
out.append("\n[A] 正常问答  HTTP %s  bytes=%d  %.1fs" % (status, len(body), elapsed))
out.append("    events: " + json.dumps(kinds, ensure_ascii=False))
out.append("    回复前 120 字: " + text[:120].replace("\n", " "))
ok_a = (
    kinds.get("RUN_STARTED") == 1
    and kinds.get("RUN_FINISHED") == 1
    and len(text) > 20
)
out.append("    判定: " + ("PASS" if ok_a else "FAIL"))

# ---------------------------------------------------------------- B 无 token
status, body, elapsed = post("/api/copilotkit", {"message": "你好"})
timings["B"] = elapsed
kinds, events = parse_agui(body)
err = [e for e in events if e.get("type") == "RUN_ERROR"]
out.append("\n[B] 无 token    HTTP %s  bytes=%d  %.1fs" % (status, len(body), elapsed))
out.append("    events: " + json.dumps(kinds, ensure_ascii=False))
out.append("    RUN_ERROR 内容: " + json.dumps(err[:1], ensure_ascii=False)[:300])
ok_b = len(err) > 0 and bool(err[0].get("message"))
out.append("    判定: " + ("PASS" if ok_b else "FAIL（错误被吞成空回复）"))

# ---------------------------------------------------------------- C 模糊问题
status, body, elapsed = post("/api/copilotkit", {"message": "我不舒服"}, token)
timings["C"] = elapsed
kinds, events = parse_agui(body)
clar = [e for e in events if e.get("type") in ("clarification", "interrupt")]
out.append("\n[C] 模糊问题    HTTP %s  bytes=%d  %.1fs" % (status, len(body), elapsed))
out.append("    events: " + json.dumps(kinds, ensure_ascii=False))
out.append("    澄清事件: " + json.dumps(clar[:1], ensure_ascii=False)[:300])
out.append("    回复前 120 字: " + text_of(events)[:120].replace("\n", " "))

# ---------------------------------------------------------------- D 用药问题
status, body, elapsed = post("/api/copilotkit", {"message": "我今天要吃什么药？"}, token)
timings["D"] = elapsed
kinds, events = parse_agui(body)
# 阶段48-31: PAGE_UPDATE 现在**包在 CUSTOM 里**发（AG-UI 规定的扩展位），
# 不再是裸的 type。所以按 CUSTOM 里的 name 找，而不是按 type 找。
pu = [e for e in events if e.get("type") == "CUSTOM" and e.get("name") == "PAGE_UPDATE"]
out.append("\n[D] 用药问题    HTTP %s  bytes=%d  %.1fs" % (status, len(body), elapsed))
out.append("    events: " + json.dumps(kinds, ensure_ascii=False))
out.append("    CUSTOM 名单: " + json.dumps(custom_names(events), ensure_ascii=False))
for e in pu[:2]:
    out.append("    PAGE_UPDATE: " + json.dumps(e.get("value"), ensure_ascii=False)[:300])
ok_d = len(pu) > 0
out.append("    判定: " + ("PASS" if ok_d else "FAIL（生成式 UI 未触发）"))

# ------------------------------------------------- E 幂等状态（AG-UI 标准通道）
# 阶段48-31: 页面控制拆成两条通道 —— 幂等的「我在哪、我在看什么」走 AG-UI
# **标准** STATE_DELTA（RFC 6902 JSON Patch），瞬态副作用仍走自定义 PAGE_UPDATE。
# 用例 D 断言的是后者（setData 是动作）；这条断言前者，两条都要有人看着。
status, body, elapsed = post("/api/copilotkit", {"message": "帮我打开健康档案页，只看检查的"}, token)
timings["E"] = elapsed
kinds, events = parse_agui(body)
sd = [e for e in events if e.get("type") == "STATE_DELTA"]
paths = [op.get("path") for e in sd for op in (e.get("delta") or [])]
out.append("\n[E] 幂等状态    HTTP %s  bytes=%d  %.1fs" % (status, len(body), elapsed))
out.append("    events: " + json.dumps(kinds, ensure_ascii=False))
for e in sd[:1]:
    out.append("    STATE_DELTA: " + json.dumps(e.get("delta"), ensure_ascii=False)[:300])
# 断言三件事：确实发了；带 /route（跳转）；带 /healthRecords/filter（筛选）。
# 只看"有没有 STATE_DELTA"太弱 —— 路径写错照样发得出来。
ok_e = "/route" in paths and "/healthRecords/filter" in paths
out.append("    路径: " + json.dumps(paths, ensure_ascii=False))
out.append("    判定: " + ("PASS" if ok_e else "FAIL（幂等状态未走标准通道）"))

# ------------------------------------------------- F 事件合规（常驻守卫）
# 阶段48-31: 跨**所有**用例收集到的事件，逐个检查 type 是否合法。
# 合法的只有两种：① 在 AG-UI 标准白名单里；② 是 CUSTOM（标准扩展位）。
# 裸发的自定义事件（如以前那个 {"type":"PAGE_UPDATE"}）会被这条抓住 ——
# 官方客户端按 EventType 判别联合解析，认不出裸发的名字。
seen = sorted({e.get("type", "?") for e in _ALL_EVENTS})
illegal = [t for t in seen if t not in STANDARD]
wrapped = sorted(set(custom_names(_ALL_EVENTS)))
out.append("\n[F] 事件合规    HTTP -  bytes=-  收集 %d 个事件" % len(_ALL_EVENTS))
out.append("    出现过的 type: " + json.dumps(seen, ensure_ascii=False))
out.append("    其中 CUSTOM 包着: " + json.dumps(wrapped, ensure_ascii=False))
out.append("    非法（既非标准也未包 CUSTOM）: " + json.dumps(illegal, ensure_ascii=False))
ok_f = not illegal
out.append("    判定: " + ("PASS" if ok_f else "FAIL（有裸发的非标准事件）"))

out.append(
    "\n[耗时] 端到端（用户真实等待）: "
    + "  ".join(f"{k}={v:.1f}s" for k, v in timings.items())
    + f"   avg={sum(timings.values()) / len(timings):.1f}s"
)

report = "\n".join(out)
print(report)
# 报告写在脚本旁边，不污染 CWD
(Path(__file__).parent / "agui_smoke_report.txt").write_text(report, encoding="utf-8")

# C 不参与断言: clarify 是 host_graph 的节点, 而流式路径（前端实际走的这条）
# 压根不经过 host_graph, 所以 clarification 事件在产品链路上不会发出 ——
# agent 改用自然语言追问。这是已知的架构现状, 不是回归。
sys.exit(0 if (ok_a and ok_b and ok_d and ok_e and ok_f) else 1)
