#!/usr/bin/env node
/**
 * PHA v2 API Smoke Tests (Node.js)
 * 不依赖 Playwright，快速验证核心 API 端点
 *
 * 运行：
 *   node tests/api-smoke.js
 *
 * 环境变量：
 *   API_BASE=http://localhost:13002
 *   FRONTEND_BASE=http://localhost:5174
 */
const http = require("http");
const https = require("https");

const API_BASE = process.env.API_BASE || "http://localhost:13002";
const FRONTEND_BASE = process.env.FRONTEND_BASE || "http://localhost:5174";

let passed = 0;
let failed = 0;

function httpGet(url, timeout = 5000) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;
    const req = client.get(url, { timeout }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => resolve({ status: res.statusCode, body: data }));
    });
    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("timeout"));
    });
  });
}

function httpPost(url, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith("https") ? https : http;
    const bodyStr = typeof body === "string" ? body : JSON.stringify(body);
    const req = client.request(
      url,
      { method: "POST", headers: { "Content-Type": "application/json", ...headers } },
      (res) => {
        let data = "";
        res.on("data", (chunk) => (data += chunk));
        res.on("end", () => resolve({ status: res.statusCode, body: data }));
      },
    );
    req.on("error", reject);
    req.write(bodyStr);
    req.end();
  });
}

async function check(label, fn) {
  process.stdout.write(`  ${label}... `);
  try {
    const result = await fn();
    console.log(`✅ ${result}`);
    passed++;
  } catch (e) {
    console.log(`❌ ${e.message}`);
    failed++;
  }
}

async function main() {
  console.log("\n🏥 PHA v2 API Smoke Tests\n");

  // 1. Health checks
  console.log("[1] Health & Metrics");
  await check("hostapi /health", async () => {
    const r = await httpGet(`${API_BASE}/health`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  await check("hostapi /metrics (Prometheus)", async () => {
    const r = await httpGet(`${API_BASE}/metrics`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    if (!r.body.includes("pha_") && !r.body.includes("process_"))
      throw new Error("No PHA metrics found");
    return "OK";
  });

  await check("health_advisor AgentCard", async () => {
    const r = await httpGet(`${API_BASE}/.well-known/agent.json`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  await check("health_advisor ANP AgentCard", async () => {
    const r = await httpGet(`${API_BASE}/anp/agent/ad.json`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    const doc = JSON.parse(r.body);
    if (!doc.did) throw new Error("Missing DID in AgentCard");
    return `DID=${doc.did}`;
  });

  await check("health_advisor DID Document", async () => {
    const r = await httpGet(`${API_BASE}/anp/did/document/did:wba:pha.local:health_advisor`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  // 2. Sub-agent ANP endpoints
  console.log("\n[2] Sub-Agent ANP Endpoints");
  const agents = [
    { name: "health_records", port: 11010 },
    { name: "medication_reminder", port: 11012 },
    { name: "visit_summary", port: 11013 },
    { name: "health_advisor", port: 11011 },
  ];

  for (const agent of agents) {
    await check(`${agent.name} /anp/agent/ad.json`, async () => {
      const r = await httpGet(`http://localhost:${agent.port}/anp/agent/ad.json`);
      if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
      return "OK";
    });

    await check(`${agent.name} /anp/metrics`, async () => {
      const r = await httpGet(`http://localhost:${agent.port}/anp/metrics`);
      if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
      return "OK";
    });
  }

  // 3. ANP RPC call
  console.log("\n[3] ANP RPC");
  await check("ANP task/send RPC (health_advisor → medication_reminder)", async () => {
    const r = await httpPost(`${API_BASE}/anp/agent/rpc`, {
      jsonrpc: "2.0",
      method: "task/send",
      params: {
        task: {
          id: `e2e-${Date.now()}`,
          message: {
            role: "user",
            parts: [{ type: "text", text: "查询我的用药记录" }],
          },
        },
        userId: "test_user_e2e",
      },
      id: "test-1",
    });
    if (r.status >= 500) throw new Error(`HTTP ${r.status} - server error`);
    return `HTTP ${r.status}`;
  });

  // 4. Smart Chat API
  console.log("\n[4] Smart Chat");
  await check("POST /smart_chat (health question)", async () => {
    const r = await httpPost(
      `${API_BASE}/smart_chat`,
      { message: "我最近头疼，应该怎么办？" },
      { "Content-Type": "application/json" },
    );
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  // 5. Frontend static assets
  console.log("\n[5] Frontend");
  await check("frontend /index.html", async () => {
    const r = await httpGet(`${FRONTEND_BASE}/`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  await check("frontend /v2/chat route", async () => {
    const r = await httpGet(`${FRONTEND_BASE}/v2/chat`);
    if (r.status !== 200) throw new Error(`HTTP ${r.status}`);
    return "OK";
  });

  // Summary
  console.log(`\n${"=".repeat(40)}`);
  console.log(`Results: ${passed} ✅  ${failed} ❌`);
  if (failed > 0) {
    console.error("\n⚠️  Some checks failed. Review above.");
    process.exit(1);
  } else {
    console.log("\n🎉 All smoke tests passed!");
  }
}

main().catch((e) => {
  console.error("Fatal:", e);
  process.exit(1);
});
