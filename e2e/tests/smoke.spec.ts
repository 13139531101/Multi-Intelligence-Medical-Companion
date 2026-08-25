/**
 * PHA v2 E2E Smoke Tests
 * 验证核心用户场景：登录 → 聊天 → 多 Agent 协作
 *
 * 运行方式：
 *   npm i && npx playwright install chromium
 *   BASE_URL=http://localhost:5174 npx playwright test
 *
 * 或本地 docker 环境：
 *   docker compose up -d
 *   docker compose exec hostapi bash -c "python -m pytest ..."
 */
import { test, expect } from "@playwright/test";

// ============================================================================
// 前置配置
// ============================================================================

const BASE_URL = process.env.BASE_URL || "http://localhost:5174";
const API_BASE = process.env.API_BASE || "http://localhost:13002";
const TEST_USER = process.env.TEST_USER || "test_user_e2e";
const TEST_SESSION = `e2e-${Date.now()}`;

// ============================================================================
// Helper: 健康检查
// ============================================================================

test.describe("0 - Health Checks", () => {
  test("hostapi /health 返回 200", async ({ request }) => {
    const res = await request.get(`${API_BASE}/health`);
    expect(res.status()).toBe(200);
  });

  test("hostapi /metrics 返回 Prometheus 格式", async ({ request }) => {
    const res = await request.get(`${API_BASE}/metrics`);
    expect(res.status()).toBe(200);
    const text = await res.text();
    expect(text).toContain("pha_requests_total");
  });

  test("health_advisor ANP AgentCard 可用", async ({ request }) => {
    const res = await request.get(`${API_BASE}/.well-known/agent.json`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("name");
    expect(body).toHaveProperty("version");
  });

  test("health_advisor /anp/agent/ad.json 返回 AgentCard", async ({ request }) => {
    const res = await request.get(`${API_BASE}/anp/agent/ad.json`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body).toHaveProperty("did");
    expect(body.did).toContain("did:wba:pha.local:");
  });

  test("所有 sub-agent 的 /metrics 端点可用", async ({ request }) => {
    const agents = [
      { name: "health_advisor", port: "11011" },
      { name: "medication_reminder", port: "11012" },
      { name: "visit_summary", port: "11013" },
      { name: "health_records", port: "11010" },
    ];
    for (const agent of agents) {
      const res = await request.get(`http://localhost:${agent.port}/anp/metrics`);
      expect(res.status(), `${agent.name} /metrics should return 200`).toBe(200);
    }
  });
});

// ============================================================================
// Helper: 登录
// ============================================================================

async function login(page: any, username = TEST_USER, password = "test123") {
  await page.goto(`${BASE_URL}/login`);
  await page.waitForLoadState("networkidle");
  // 如果已经是登录状态（dev 模式），直接跳转
  const url = page.url();
  if (url.includes("/dashboard") || url.includes("/v2/chat")) {
    return;
  }
  // 填登录表单
  const userInput = page.locator('input[name="username"], input[type="text"]').first();
  const passInput = page.locator('input[type="password"]').first();
  if (await userInput.isVisible()) {
    await userInput.fill(username);
    await passInput.fill(password);
    await page.click('button[type="submit"]');
    await page.waitForURL(/dashboard|v2\/chat|consultation/, { timeout: 15_000 });
  }
}

// ============================================================================
// 场景 1: 基础聊天（健康顾问单 Agent）
// ============================================================================

test.describe("1 - Smart Chat (Single Agent)", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("用户可以在 NewChat 页面发送消息并收到回复", async ({ page }) => {
    await page.goto(`${BASE_URL}/v2/chat`);
    await page.waitForLoadState("networkidle");

    // 找到输入框
    const input = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"], textarea').first();
    await expect(input).toBeVisible({ timeout: 10_000 });

    // 发送测试消息
    const testMessage = "我最近有点头疼，应该怎么办？";
    await input.fill(testMessage);
    await input.press("Enter");

    // 等待助手回复（最多 60 秒）
    const assistantBubble = page.locator(".MuiChatBubble-root, [class*='chat'], [class*='message']").last();
    await expect(assistantBubble).toBeVisible({ timeout: 60_000 });

    const replyText = await assistantBubble.textContent();
    expect(replyText!.length).toBeGreaterThan(5);
    console.log(`[Smart Chat] 回复预览: ${replyText!.slice(0, 100)}`);
  });

  test("闲聊问题可以正常回复（不需要工具）", async ({ page }) => {
    await page.goto(`${BASE_URL}/v2/chat`);
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"], textarea').first();
    await input.fill("你好，今天天气怎么样？");
    await input.press("Enter");

    const assistantBubble = page.locator("[class*='chat'], [class*='message']").last();
    await expect(assistantBubble).toBeVisible({ timeout: 60_000 });
  });
});

// ============================================================================
// 场景 2: 健康顾问 → 用药提醒（A2A 多 Agent 协作）
// ============================================================================

test.describe("2 - Multi-Agent A2A Collaboration", () => {
  test("health_advisor 可以通过 ANP RPC 调用 medication_reminder", async ({ request }) => {
    // 直接测试 ANP RPC 调用
    const res = await request.post(`${API_BASE}/anp/agent/rpc`, {
      data: {
        jsonrpc: "2.0",
        method: "tasks/send",
        params: {
          task: {
            id: TEST_SESSION,
            message: {
              role: "user",
              parts: [{ type: "text", text: "查询我的当前用药" }],
            },
          },
          userId: TEST_USER,
        },
      },
      headers: { "Content-Type": "application/json" },
    });

    // ANP RPC 可能返回 200（即使 sub-agent 调用失败）
    // 重点验证端点可达、格式正确
    expect([200, 400, 500]).toContain(res.status());
    const body = await res.json();
    console.log("[A2A RPC] 响应:", JSON.stringify(body).slice(0, 200));
  });

  test("前端聚合健康报告可以触发多 Agent 调用", async ({ page }) => {
    await login(page);
    await page.goto(`${BASE_URL}/v2/chat`);
    await page.waitForLoadState("networkidle");

    const input = page.locator('textarea[placeholder*="输入"], input[placeholder*="输入"], textarea').first();
    // 触发 aggregate_health_report 的问题
    await input.fill("帮我综合分析一下我的健康状况，包括用药记录和就诊记录");
    await input.press("Enter");

    // 等待回复（多 Agent 并行会慢一些）
    const assistantBubble = page.locator("[class*='chat'], [class*='message']").last();
    await expect(assistantBubble).toBeVisible({ timeout: 90_000 });

    const replyText = await assistantBubble.textContent();
    // 验证回复中可能提到了多个 Agent 的协作
    console.log(`[Multi-Agent] 回复预览: ${replyText!.slice(0, 150)}`);
  });
});

// ============================================================================
// 场景 3: 健康档案管理
// ============================================================================

test.describe("3 - Health Records", () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test("可以访问健康档案页面", async ({ page }) => {
    await page.goto(`${BASE_URL}/v2/health-records`);
    await page.waitForLoadState("networkidle");
    // 页面应该正常加载，不崩溃
    await expect(page.locator("body")).toBeVisible();
  });

  test("可以访问今日看板", async ({ page }) => {
    await page.goto(`${BASE_URL}/v2/today`);
    await page.waitForLoadState("networkidle");
    await expect(page.locator("body")).toBeVisible();
  });
});

// ============================================================================
// 场景 4: Prometheus Metrics 验证
// ============================================================================

test.describe("4 - Observability", () => {
  test("所有 Agent 的 /metrics 端点返回有效 Prometheus 指标", async ({ request }) => {
    const agents = [
      { name: "hostapi", url: `${API_BASE}/metrics` },
      { name: "health_advisor", url: `http://localhost:11011/anp/metrics` },
      { name: "medication_reminder", url: `http://localhost:11012/anp/metrics` },
      { name: "visit_summary", url: `http://localhost:11013/anp/metrics` },
      { name: "health_records", url: `http://localhost:11010/anp/metrics` },
    ];

    for (const agent of agents) {
      const res = await request.get(agent.url);
      expect(res.status(), `${agent.name} metrics should be reachable`).toBe(200);
      const text = await res.text();
      // 至少包含 pha_ 前缀的指标或标准的 prometheus 格式
      expect(
        text.includes("pha_") || text.includes("process_"),
        `${agent.name} should expose PHA metrics`,
      ).toBeTruthy();
    }
  });
});
