"""阶段30-1 测试：多 agent 并行调用"""
import asyncio
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

async def main():
    from A2AServer.v2.host_graph import build_host_graph, route_and_invoke
    from A2AServer.v2.sub_agents import (
        HealthAdvisorV2,
        HealthRecordsV2,
        MedicationReminderV2,
        VisitSummaryV2,
    )

    # 测试 1：构建 single 模式图（向后兼容）
    print("=== Test 1: build_host_graph(mode='single') ===")
    g_single = build_host_graph(use_checkpointer=False, mode="single")
    print(f"  single graph: {g_single}")

    # 测试 2：构建 multi 模式图
    print("\n=== Test 2: build_host_graph(mode='multi') ===")
    g_multi = build_host_graph(use_checkpointer=False, mode="multi")
    print(f"  multi graph: {g_multi}")

    # 测试 3：single 模式调用（向后兼容）
    print("\n=== Test 3: route_and_invoke single mode ===")
    t0 = time.time()
    result = await route_and_invoke(
        query="我头疼",
        conversation_id="test_conv_1",
        user_id="test_user",
        mode="single",
    )
    elapsed = time.time() - t0
    print(f"  elapsed: {elapsed:.2f}s")
    print(f"  result keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
    print(f"  result content (前 200): {str(result.get('content', ''))[:200] if isinstance(result, dict) else 'N/A'}")

    # 测试 4：multi 模式调用（4 个 agent 并行）
    print("\n=== Test 4: route_and_invoke multi mode (4 agents parallel) ===")
    t0 = time.time()
    result_multi = await route_and_invoke(
        query="综合分析我的健康状况",
        conversation_id="test_conv_2",
        user_id="test_user",
        mode="multi",
    )
    elapsed_multi = time.time() - t0
    print(f"  elapsed: {elapsed_multi:.2f}s")
    if isinstance(result_multi, dict):
        routing = result_multi.get("routing", {})
        summaries = routing.get("worker_summaries", [])
        print(f"  routing mode: {routing.get('mode')}")
        print(f"  worker_summaries ({len(summaries)}):")
        for s in summaries:
            print(f"    - {s}")
        print(f"  parallel_status: {result_multi.get('parallel_status')}")

    # 对比：single 4 次串行 vs multi 1 次 4 并行
    print("\n=== Test 5: 比较耗时 ===")
    print(f"  single mode (1 agent): {elapsed:.2f}s")
    print(f"  multi mode (4 agents parallel): {elapsed_multi:.2f}s")
    if elapsed_multi < elapsed * 4:
        print(f"  [OK] multi 模式比 4 次串行快")
    else:
        print(f"  [WARN] multi 模式没省时间")


if __name__ == "__main__":
    asyncio.run(main())