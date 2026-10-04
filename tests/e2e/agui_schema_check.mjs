/**
 * AG-UI 事件**合规**校验：拿官方 SDK 的 zod schema 逐个校验真实 wire 上的事件。
 *
 * 为什么要有这个（而不只是 agui_smoke.py）
 * --------------------------------------
 * agui_smoke.py 的 F 用例只能检查「type 在不在标准白名单里」—— 那是**名字**层面的
 * 合规。但一个事件名字对了、字段错了，照样过不了官方客户端。这个脚本补的就是这一层：
 * 它直接 require 前端 node_modules 里的 `@ag-ui/core`，用**官方 schema 本体**
 * 做 safeParse。
 *
 * 写这个脚本当场就抓到一个真 bug：TOOL_CALL_RESULT 缺必填字段 `messageId`，
 * 而它在白名单里、F 用例是绿的。**名字合规 ≠ 结构合规。**
 *
 * 依赖 @ag-ui/core（前端 node_modules 里有），所以用 Node 跑、不是 Python。
 *
 * 用法：
 *     node tests/e2e/agui_schema_check.mjs
 *     BASE=http://localhost:13002 node tests/e2e/agui_schema_check.mjs
 *
 * 退出码：全部事件通过 schema 才返回 0。
 */
import { createRequire } from 'module';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const BASE = process.env.BASE || 'http://localhost:13002';
const USERNAME = process.env.PROBE_USER || 'probe_agui_1';
const PASSWORD = process.env.PROBE_PASS || 'ProbePass123!';

// 从仓库里解析 @ag-ui/core —— 前端装的那份就是官方 SDK
const here = dirname(fileURLToPath(import.meta.url));
const frontDir = join(here, '..', '..', 'frontend', 'multiagent_front');
const require = createRequire(join(frontDir, 'package.json'));
const agui = require('@ag-ui/core');
const version = require('@ag-ui/core/package.json').version;

// EventType.FOO_BAR -> FooBarEventSchema 的反查表
const schemaByType = {};
for (const key of Object.keys(agui)) {
  const m = /^(.+)EventSchema$/.exec(key);
  if (!m) continue;
  schemaByType[m[1].replace(/([a-z])([A-Z])/g, '$1_$2').toUpperCase()] = agui[key];
}

/** 覆盖标准事件与各种自定义事件（routing / rag_context / PAGE_UPDATE）。 */
const QUESTIONS = [
  '我今天要吃什么药？',
  '帮我打开健康档案页，只看检查的',
  '我最近血压控制得怎么样？',
];

async function post(path, body, token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  const r = await fetch(BASE + path, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  return r.text();
}

function parseSse(text) {
  const out = [];
  for (const line of text.split('\n')) {
    if (!line.startsWith('data:')) continue;
    try {
      out.push(JSON.parse(line.slice(5).trim()));
    } catch {
      /* 非 JSON 的 data 行忽略 */
    }
  }
  return out;
}

const loginRaw = await post('/auth/login', { username: USERNAME, password: PASSWORD });
let token;
try {
  token = JSON.parse(loginRaw).access_token;
} catch {
  console.error('登录失败:', loginRaw.slice(0, 200));
  process.exit(1);
}

const events = [];
for (const q of QUESTIONS) {
  events.push(...parseSse(await post('/api/copilotkit', { message: q }, token)));
}

const kinds = {};
const failures = [];
for (const ev of events) {
  const t = ev.type;
  kinds[t] = (kinds[t] || 0) + 1;

  const schema = schemaByType[t];
  if (!schema) {
    // 裸发的非标准事件 —— 官方客户端按 EventType 判别联合解析，认不出它
    failures.push([t, '不是标准事件，也没包成 CUSTOM']);
    continue;
  }
  const res = schema.safeParse(ev);
  if (!res.success) {
    const issue = res.error.issues?.[0];
    failures.push([t, `${issue?.path?.join('.') || '?'}: ${issue?.message}`]);
  }
}

const customs = [...new Set(events.filter((e) => e.type === 'CUSTOM').map((e) => e.name))];

console.log(`@ag-ui/core ${version}  |  ${BASE}`);
console.log(`收集 ${events.length} 个事件`);
console.log('type 分布:', JSON.stringify(kinds));
console.log('CUSTOM 包着:', JSON.stringify(customs));

if (failures.length) {
  console.log(`\n未过 schema 的事件 (${failures.length}):`);
  const seen = new Set();
  for (const [t, msg] of failures) {
    const key = `${t}|${msg}`;
    if (seen.has(key)) continue;
    seen.add(key);
    console.log(`  ✗ ${t} -> ${msg}`);
  }
  process.exit(1);
}

console.log(`\n全部 ${events.length} 个事件通过官方 schema ✓`);
