"""阶段21 验收 - RAG 索引/检索/反馈"""
import os
import sys
import time
import asyncio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['EMBEDDING_MODEL'] = 'text-embedding-v3'  # v3 支持 dimensions 参数
os.environ['EMBEDDING_DIM'] = '1024'  # 改表后用 1024
os.environ['DASHSCOPE_API_KEY'] = 'sk-2917df2994074695b7b741ffb6382a3b'  # 测试用
import locale
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')
except Exception:
    pass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'A2AServer', 'src'))

# 加载 .env
try:
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(os.path.dirname(__file__), '..', '.env'))
    for k, v in env.items():
        if v is not None and (k not in os.environ or not os.environ.get(k)):
            os.environ[k] = v
except Exception as e:
    print(f'WARN: .env load failed: {e}')

# 本地 Windows 测试：host 端口（docker expose 5432→127.0.0.1）
# 容器内用 'postgres'（docker DNS），本机用 '127.0.0.1'
import socket
def _is_in_docker():
    try:
        with open('/proc/1/cgroup', 'r') as f:
            return 'docker' in f.read() or 'kubepods' in f.read()
    except Exception:
        return False
if not _is_in_docker() and os.environ.get('DB_HOST', '') == 'postgres':
    os.environ['DB_HOST'] = '127.0.0.1'
    print(f'[verify_stage21] running on host, switched DB_HOST to 127.0.0.1')

import httpx

print('=' * 70)
print('PHA v2 阶段21 验收 - RAG 索引 / 检索 / 反馈')
print('=' * 70)

total = 0
passed = 0


def check(name, ok, detail=''):
    global total, passed
    icon = '[OK]  ' if ok else '[FAIL]'
    print(f'  {icon} {name:55s} {detail}')
    total += 1
    if ok:
        passed += 1


# ---- 1. 单元测试：chunk_text ----
print('\n[1] chunk_text 文本分块')
from A2AServer.v2.rag import chunk_text

c = chunk_text("第一句。第二句！第三句；第四句。", chunk_size=5, overlap=0)
check('按标点切分 (4 块)', len(c) == 4, f'len={len(c)} pieces={c}')

text = "A" * 500
c = chunk_text(text, chunk_size=200, overlap=30)
check('长文本按 chunk_size 切', len(c) > 1, f'len={len(c)} chunks')
check('每块 <= chunk_size', all(len(x) <= 200 for x in c))

c = chunk_text("")
check('空文本返空列表', c == [])

c = chunk_text("  空格测试  ")
check('自动 trim', c == ["空格测试"])

# ---- 2. 单元测试：_to_pgvector / _from_pgvector ----
print('\n[2] vector 序列化')
from A2AServer.v2.rag import _to_pgvector, _from_pgvector

v = [0.1, 0.2, -0.3]
s = _to_pgvector(v)
check('to_pgvector 格式', s == "[0.1000000,0.2000000,-0.3000000]", f'got {s!r}')
v2 = _from_pgvector(s)
check('from_pgvector 还原', v == v2, f'got {v2}')

# ---- 3. 集成：index_document ----
print('\n[3] index_document 索引文档')
from A2AServer.v2.rag import get_rag_store
import psycopg

USER = f'verify_user_{int(time.time())}'
SAMPLE = (
    "高血压患者应该低盐饮食，每日食盐摄入量不应超过 5 克。\n"
    "糖尿病患者要控制碳水化合物摄入，多吃蔬菜和粗粮。\n"
    "规律运动可以降低血压，建议每周至少 150 分钟中等强度运动。\n"
    "戒烟限酒对心血管健康非常重要。\n"
    "保持心情舒畅，避免长期精神紧张，可以预防多种慢性病。"
)


def _conn():
    return psycopg.connect(
        host=os.environ.get('DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('DB_PORT', '5432')),
        user=os.environ.get('DB_USER', 'pha'),
        password=os.environ.get('DB_PASSWORD', ''),
        dbname=os.environ.get('DB_NAME', 'personal_health_assistant'),
    )


async def main():
    global passed
    print(f'[debug] DB_HOST={os.environ.get("DB_HOST")} DB_PORT={os.environ.get("DB_PORT")}')
    store = get_rag_store()
    # 清理旧数据（防残留）
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM rag_chunks WHERE user_id=%s", (USER,))
            cur.execute("DELETE FROM rag_documents WHERE user_id=%s", (USER,))
        conn.commit()

    try:
        result = await store.index_document(USER, "health_article", "art_001", SAMPLE, "article", "慢性病预防")
        check('index_document 返 indexed=True', result.get("indexed") is True)
        check('chunk_count > 0', result.get("chunk_count", 0) > 0, f'count={result.get("chunk_count")}')
        check('embedding_model 是 text-embedding-v3', result.get("embedding_model") == "text-embedding-v3")

        # 重复索引应跳过
        result2 = await store.index_document(USER, "health_article", "art_001", SAMPLE, "article", "慢性病预防")
        check('重复索引跳过 (sha 一致)', result2.get("skipped") is True, str(result2)[:80])

        # ---- 4. 集成：search ----
        print('\n[4] search 语义检索')
        results = await store.search(USER, "高血压怎么治疗", top_k=3, min_score=0.3)
        check('search 返列表', isinstance(results, list))
        check('search 至少 1 条', len(results) >= 1, f'got {len(results)}')
        if results:
            check('首条 score >= 0.3', results[0].score >= 0.3, f'score={results[0].score:.3f}')
            check('首条有 source', results[0].source_type == "health_article")
            check('首条 chunk_text 非空', len(results[0].chunk_text) > 10)

        # 不相关查询返回空
        no_results = await store.search(USER, "量子纠缠超弦理论", top_k=3, min_score=0.7)
        check('高阈值不相关返空', len(no_results) == 0, f'got {len(no_results)}')

        # 按 source_type 过滤
        with_source = await store.search(USER, "高血压", top_k=3, source_type="health_article")
        check('按 source_type 过滤', all(r.source_type == "health_article" for r in with_source))

        # ---- 5. 反馈 ----
        print('\n[5] add_feedback 反馈')
        if results:
            cid = results[0].chunk_id
            store.add_feedback(USER, cid, "高血压", +1.0)
            store.add_feedback(USER, cid, "高血压", +1.0)
            check('feedback 累加', store._feedback[cid] == 2.0, f'total={store._feedback[cid]}')

            # 再次检索，被点赞的 chunk 应排在前面
            r2 = await store.search(USER, "高血压", top_k=3, min_score=0.3)
            if r2:
                check('反馈加权排序正确', r2[0].chunk_id == cid, f'cid match')

        # ---- 6. recall_for_user ----
        print('\n[6] recall_for_user 召回')
        recall = await store.recall_for_user(USER, "高血压", top_k=3)
        check('recall 返 dict', isinstance(recall, dict))
        check('recall 含 query', recall.get("query") == "高血压")
        check('recall 含 rag_chunks', "rag_chunks" in recall)
        check('recall rag_count 匹配', recall.get("rag_count") == len(recall.get("rag_chunks", [])))

        # ---- 7. stats ----
        print('\n[7] stats 统计')
        s = store.stats()
        check('stats 含 doc_count', "doc_count" in s)
        check('stats 含 chunk_count', "chunk_count" in s)
        check('stats 含 user_count', "user_count" in s)
        check('stats 含 embedding_model', s["embedding_model"] == "text-embedding-v3")
        check('stats embedding_dim = 1024', s["embedding_dim"] == 1024)
        check('stats doc_count >= 1', s["doc_count"] >= 1, f'doc={s["doc_count"]}')

        # ---- 8. HTTP 端点 ----
        print('\n[8] HTTP 端点 (hostapi)')
        try:
            r = httpx.get('http://localhost:13002/v2/rag/stats', timeout=5)
            check('GET /v2/rag/stats 200', r.status_code == 200, f'code={r.status_code}')
        except Exception as e:
            check('GET /v2/rag/stats', False, str(e)[:80])

        try:
            r = httpx.post('http://localhost:13002/v2/rag/index', json={
                "user_id": USER + "_http",
                "source_type": "test",
                "source_id": "http_001",
                "text": "这是一段测试文本。\n用于验证 HTTP 索引端点。",
                "record_type": "test",
                "title": "HTTP 测试"
            }, timeout=30)
            check('POST /v2/rag/index 200', r.status_code == 200, f'code={r.status_code} body={r.text[:80]}')
            if r.status_code == 200:
                data = r.json()
                check('HTTP index 返 indexed=True', data.get("indexed") is True)
        except Exception as e:
            check('POST /v2/rag/index', False, str(e)[:80])

        try:
            r = httpx.get(f'http://localhost:13002/v2/rag/search?user_id={USER}_http&query=测试&top_k=3', timeout=30)
            check('GET /v2/rag/search 200', r.status_code == 200, f'code={r.status_code}')
            if r.status_code == 200:
                data = r.json()
                check('HTTP search 返 results 数组', "results" in data)
                check('HTTP search count > 0', data.get("count", 0) > 0, f'count={data.get("count")}')
        except Exception as e:
            check('GET /v2/rag/search', False, str(e)[:80])

        try:
            r = httpx.post('http://localhost:13002/v2/rag/feedback', json={
                "user_id": USER,
                "chunk_id": "00000000-0000-0000-0000-000000000000",
                "score_delta": 1.0
            }, timeout=5)
            check('POST /v2/rag/feedback 200', r.status_code == 200, f'code={r.status_code}')
        except Exception as e:
            check('POST /v2/rag/feedback', False, str(e)[:80])

    finally:
        # 清理
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM rag_chunks WHERE user_id=%s OR user_id=%s", (USER, USER + "_http"))
                cur.execute("DELETE FROM rag_documents WHERE user_id=%s OR user_id=%s", (USER, USER + "_http"))
            conn.commit()

    # ---- 总结 ----
    print('\n' + '=' * 70)
    print(f'阶段21 验收：{passed}/{total} 通过')
    if passed == total:
        print('[OK] 全部通过！阶段21 完成，RAG 索引/检索/反馈就绪。')
    else:
        print(f'[WARN] 有 {total - passed} 项失败')
    print('=' * 70)
    return passed == total


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
