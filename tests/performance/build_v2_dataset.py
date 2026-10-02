"""从库里现有的 rag_documents 生成 v2 评测集（阶段48-p4）。

为什么需要它
------------
v2 链路的评测集必须按 **source_id**（业务 id）标注，而这些 id 是每个环境
自己产生的 —— 没法硬编码进仓库。所以给一个生成器：读本机库里的档案，
为每篇生成 1~2 个「这篇文档应该能回答」的自然提问。

两种模式
--------
heuristic : 用 title / record_type 拼问题，零依赖、零成本、可复现
llm       : 让 DeepSeek 生成更像真实患者的提问（需要 DEEPSEEK_API_KEY）

生成结果**需要人工过一遍**：自动标注只是起点，明显不合理的 case 删掉再拿去评测，
否则指标好看但没意义。

用法
----
    python tests/performance/build_v2_dataset.py --out tests/performance/rag_v2_eval_dataset.json
    python tests/performance/build_v2_dataset.py --mode llm --per-doc 2 --out ...
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _dsn() -> str:
    if os.getenv("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    user = os.getenv("DB_USER", os.getenv("POSTGRES_USER", "pha"))
    pwd = os.getenv("DB_PASSWORD", os.getenv("POSTGRES_PASSWORD", "pha_pass"))
    name = os.getenv("DB_NAME", os.getenv("POSTGRES_DB", "personal_health_assistant"))
    return f"postgresql://{user}:{pwd}@{host}:{port}/{name}"


def fetch_documents(embedding_model: str, limit: int) -> list[dict]:
    """只取栈 A（v2 主链路）写的文档 —— 栈 B 那套向量空间不同，混进来没意义"""
    import psycopg

    sql = """
        SELECT user_id, source_type, source_id, COALESCE(record_type,''), COALESCE(title,''),
               COALESCE(full_text,'')
        FROM rag_documents
        WHERE embedding_model = %s
        ORDER BY updated_at DESC NULLS LAST
        LIMIT %s
    """
    with psycopg.connect(_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (embedding_model, limit))
            rows = cur.fetchall()
    return [
        {
            "user_id": str(r[0] or ""),
            "source_type": str(r[1] or ""),
            "source_id": str(r[2] or ""),
            "record_type": str(r[3] or ""),
            "title": str(r[4] or ""),
            "full_text": str(r[5] or ""),
        }
        for r in rows
    ]


# ---------------------------------------------------------------- heuristic

_TYPE_HINT = {
    "blood_pressure": "血压",
    "blood_sugar": "血糖",
    "medication": "用药",
    "lab_result": "化验结果",
    "visit_summary": "就诊记录",
    "health_record": "体检报告",
    "symptom": "症状",
}


def queries_heuristic(doc: dict, per_doc: int) -> list[str]:
    out: list[str] = []
    title = doc["title"].strip()
    hint = _TYPE_HINT.get(doc["record_type"], "") or doc["source_type"]
    if title:
        out.append(title)
        if hint and hint not in title:
            out.append(f"{hint}：{title}")
    elif hint:
        out.append(f"我的{hint}情况怎么样")
    # 兜底：从正文里截一句
    if len(out) < per_doc and doc["full_text"]:
        first = doc["full_text"].strip().splitlines()[0][:40]
        if first:
            out.append(first)
    return out[:per_doc]


# ---------------------------------------------------------------- llm

def queries_llm(doc: dict, per_doc: int, timeout: int = 30) -> list[str]:
    key = (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return queries_heuristic(doc, per_doc)
    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=key,
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=timeout,
        )
        body = (doc["title"] + "\n" + doc["full_text"])[:1200]
        prompt = (
            "下面是一段个人健康档案。请生成 " + str(per_doc) + " 个**患者本人会问的**中文问题，"
            "这些问题必须能且只能靠这段档案回答。\n"
            "只输出 JSON 数组，例如 [\"问题1\",\"问题2\"]，不要任何解释。\n\n"
            f"档案：\n{body}"
        )
        resp = client.chat.completions.create(
            model=os.getenv("PHA_LLM_MODEL", "deepseek-chat"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        content = (resp.choices[0].message.content or "").strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        parsed = json.loads(content.strip())
        if isinstance(parsed, list):
            return [str(q).strip() for q in parsed if str(q).strip()][:per_doc]
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] LLM 生成失败，退回 heuristic: {e}", file=sys.stderr)
    return queries_heuristic(doc, per_doc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path(__file__).parent / "rag_v2_eval_dataset.json"))
    ap.add_argument("--mode", choices=["heuristic", "llm"], default="heuristic")
    ap.add_argument("--per-doc", type=int, default=1)
    ap.add_argument("--limit", type=int, default=60, help="最多读多少篇文档")
    ap.add_argument(
        "--embedding-model",
        default=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
        help="只取该模型索引的文档（栈 A）",
    )
    ap.add_argument("--category", default="local_hit", help="生成的 case 归到哪一类")
    args = ap.parse_args()

    docs = fetch_documents(args.embedding_model, args.limit)
    if not docs:
        print(
            f"库里没有 embedding_model={args.embedding_model} 的文档。\n"
            "先跑一次索引（/v2/rag/index 或让 agent 写入健康档案）再来生成评测集。",
            file=sys.stderr,
        )
        sys.exit(2)

    gen = queries_llm if args.mode == "llm" else queries_heuristic
    dataset: list[dict] = []
    for doc in docs:
        for q in gen(doc, args.per_doc):
            dataset.append({
                "query": q,
                "relevant_ids": [doc["source_id"]],
                "user_id": doc["user_id"],
                "category": args.category,
            })

    Path(args.out).write_text(json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成 {len(dataset)} 条 case（来自 {len(docs)} 篇文档）→ {args.out}")
    print("提示：自动标注是起点，请人工过一遍再拿去评测。")


if __name__ == "__main__":
    main()
