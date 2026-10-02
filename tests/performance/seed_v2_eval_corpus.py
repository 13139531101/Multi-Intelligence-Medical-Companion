"""为 v2 主链路 RAG 评测灌一份**确定性语料**（阶段48-p4）。

为什么要单独灌语料
------------------
`build_v2_dataset.py` 是从"当前库里恰好有什么"反推评测集 —— 在开发机上跑出来的
query 基本就是文档标题本身，任何检索器都能排第一，四组消融全是 MRR=1.0，指标好看
但没有任何区分度。评测要有意义，语料必须满足两点：

  1. **可复现**：谁 clone 下来跑都是同一批文档、同一批 query、同一组数字。
  2. **有干扰**：存在与目标文档**词汇高度重叠但内容不同**的干扰项（比如"血压监测
     记录"旁边放一份"体位性低血压记录"）。没有干扰项，rerank 就没有用武之地，
     消融实验也就测不出 rerank 的价值。

所以这里手写 14 篇语料：既覆盖 v2 多跳检索依赖的全部 record_type 枚举
（vital_signs / prescription / lab_result / other / medical_report / symptom），
也刻意埋入成对的近似文档。

用法
----
    python tests/performance/seed_v2_eval_corpus.py            # 走 HTTP 索引（推荐）
    python tests/performance/seed_v2_eval_corpus.py --dry-run  # 只看会灌什么

默认打到 `http://localhost:13002`，可用 `--base` 或 `PHA_EVAL_BASE` 覆盖。
语料灌给 `rag_eval_user`，与真实用户数据完全隔离，可随时重灌。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

EVAL_USER_ID = "rag_eval_user"

# record_type 必须是 rag_chunks 里实际写入的枚举值 —— magnetic_rag 的
# RECORD_TYPE_TO_DB_TYPE 把 blood_pressure→vital_signs、medication→prescription
# 之后**按 record_type 精确过滤**，写成中文标签（如"慢性病管理"）在多跳检索里
# 一条都匹配不到，只有单跳向量检索能召回，会让"多跳 vs 单跳"的对比失真。
CORPUS: list[dict] = [
    # ---------------- vital_signs ----------------
    {
        "source_type": "health_records",
        "source_id": "eval-bp-001",
        "record_type": "vital_signs",
        "title": "家庭血压监测记录（近三个月）",
        "text": (
            "患者规律家庭自测血压，近三个月共记录 62 次。晨起服药前收缩压 128-138 mmHg，"
            "舒张压 80-88 mmHg；晚间睡前收缩压 122-132 mmHg，舒张压 76-84 mmHg。"
            "整体控制平稳，未出现持续高于 140/90 的读数。期间有 4 次晨起读数偏高至 "
            "145/92 mmHg，均出现在前一晚睡眠不足或进食咸食之后，次日复测即回落。"
            "心率维持在 68-78 次/分。医生评价：当前降压方案有效，继续维持。"
        ),
    },
    {
        # 干扰项：与 bp-001 词汇高度重叠，但讲的是相反的问题
        "source_type": "health_records",
        "source_id": "eval-bp-002",
        "record_type": "vital_signs",
        "title": "体位性低血压监测记录",
        "text": (
            "患者主诉起床或久蹲后站起时眼前发黑、头晕，偶有站立不稳。行卧立位血压测定："
            "平卧 5 分钟后血压 126/78 mmHg，站立 1 分钟降至 102/64 mmHg，站立 3 分钟 "
            "98/60 mmHg，收缩压下降超过 20 mmHg，符合体位性低血压诊断。"
            "建议起床时分步进行，先坐起 1 分钟再站立；避免长时间站立与热水浴；"
            "如正在服用α受体阻滞剂需评估减量。日常血压本身并不高。"
        ),
    },
    {
        "source_type": "health_records",
        "source_id": "eval-bs-001",
        "record_type": "vital_signs",
        "title": "空腹与餐后血糖自我监测记录",
        "text": (
            "近四周血糖仪自测记录。空腹血糖多在 6.8-7.6 mmol/L 之间，平均 7.2 mmol/L；"
            "早餐后 2 小时血糖 9.5-11.2 mmol/L，午餐后 2 小时 8.8-10.4 mmol/L，"
            "晚餐后 2 小时 8.2-9.6 mmol/L。饮食控制后餐后峰值较前下降约 1.5 mmol/L。"
            "夜间未出现心慌出汗等低血糖表现。患者希望了解是否需要调整降糖药物剂量。"
        ),
    },
    {
        "source_type": "health_records",
        "source_id": "eval-bs-002",
        "record_type": "vital_signs",
        "title": "糖化血红蛋白与连续血糖监测报告",
        "text": (
            "本次糖化血红蛋白 HbA1c 为 7.4%，较三个月前的 7.9% 下降 0.5 个百分点，"
            "但仍高于 7.0% 的控制目标。连续血糖监测（CGM）显示 24 小时葡萄糖目标范围内"
            "时间 TIR 为 63%，低于 70% 的目标；高于目标范围时间 34%，低于目标范围时间 3%。"
            "血糖波动主要出现在晚餐后。结论：需强化晚餐时段管理。"
        ),
    },
    # ---------------- prescription ----------------
    {
        "source_type": "health_records",
        "source_id": "eval-rx-001",
        "record_type": "prescription",
        "title": "降压药物处方",
        "text": (
            "苯磺酸氨氯地平片 5mg，每日早 8 点口服一次；缬沙坦胶囊 80mg，每晚 8 点口服一次。"
            "两药联合用于原发性高血压 3 级（高危）。用药后家庭血压维持在 132/84 mmHg 左右。"
            "注意事项：氨氯地平可能引起踝部水肿，如出现可告知医生；缬沙坦用药期间需监测"
            "血钾与肾功能；不可自行停药或减量，突然停用可能导致血压反跳。"
        ),
    },
    {
        "source_type": "health_records",
        "source_id": "eval-rx-002",
        "record_type": "prescription",
        "title": "降糖药物处方",
        "text": (
            "二甲双胍缓释片 500mg，每日午餐时随餐服用；阿卡波糖片 50mg，随三餐第一口饭嚼服。"
            "用于 2 型糖尿病血糖控制。二甲双胍常见不良反应为腹胀、腹泻，多在用药初期，"
            "随餐服用可减轻；肾功能不全者需减量。阿卡波糖需与第一口主食同服才有效，"
            "单服无效，可能引起排气增多。用药期间建议每 3 个月复查糖化血红蛋白。"
        ),
    },
    {
        "source_type": "health_records",
        "source_id": "eval-rx-003",
        "record_type": "prescription",
        "title": "冠心病二级预防用药处方",
        "text": (
            "阿司匹林肠溶片 100mg，每日一次，餐前空腹服用；阿托伐他汀钙片 20mg，每晚一次。"
            "用于冠心病劳力型心绞痛二级预防。阿司匹林需注意消化道出血风险，如出现黑便、"
            "牙龈异常出血需及时就医；肠溶片应整片吞服不可嚼碎。阿托伐他汀需监测肝功能与"
            "肌酸激酶，如出现不明原因肌肉酸痛无力应立即就诊。"
        ),
    },
    # ---------------- lab_result ----------------
    {
        "source_type": "health_records",
        "source_id": "eval-lab-001",
        "record_type": "lab_result",
        "title": "血脂四项检验报告",
        "text": (
            "总胆固醇 5.82 mmol/L（参考值 <5.2，偏高）；甘油三酯 2.14 mmol/L（参考值 <1.7，偏高）；"
            "高密度脂蛋白胆固醇 1.02 mmol/L（参考值 >1.0，正常下限）；"
            "低密度脂蛋白胆固醇 3.76 mmol/L（参考值 <2.6，明显偏高）。"
            "结合冠心病病史，LDL-C 目标值应控制在 1.8 mmol/L 以下，目前未达标，"
            "提示他汀剂量可能需要加强。"
        ),
    },
    {
        "source_type": "health_records",
        "source_id": "eval-lab-002",
        "record_type": "lab_result",
        "title": "肝肾功能与电解质检验报告",
        "text": (
            "谷丙转氨酶 32 U/L，谷草转氨酶 28 U/L，均在正常范围；肌酐 88 μmol/L，"
            "估算肾小球滤过率 eGFR 78 mL/min/1.73m²，轻度下降；血钾 4.3 mmol/L，"
            "血钠 140 mmol/L，均在正常范围。服用缬沙坦与他汀期间肝肾功能可耐受，"
            "建议继续每半年复查一次。"
        ),
    },
    # ---------------- other (就诊摘要) ----------------
    {
        "source_type": "visit_summaries",
        "source_id": "eval-vs-001",
        "record_type": "other",
        "title": "心内科门诊复诊记录",
        "text": (
            "主诉：活动后胸闷两周。现病史：两周前开始快走或爬楼时出现胸闷，持续 3-5 分钟，"
            "休息后缓解，无放射痛及大汗。既往高血压、2 型糖尿病病史。查体：血压 138/86 mmHg，"
            "心率 76 次/分，律齐。心电图示窦性心律、ST-T 改变；心脏彩超示左室舒张功能减低。"
            "初步诊断：冠心病，劳力型心绞痛。处理：加用阿司匹林与他汀，建议行冠状动脉 CTA，"
            "一月后门诊随访。"
        ),
    },
    {
        "source_type": "visit_summaries",
        "source_id": "eval-vs-002",
        "record_type": "other",
        "title": "内分泌科门诊复诊记录",
        "text": (
            "主诉：多饮多尿伴双足麻木两月。查体：双足痛觉、温度觉减退，10g 尼龙丝试验"
            "双足部分感觉缺失，足背动脉搏动可。辅助检查：糖化血红蛋白 7.4%，尿微量白蛋白 "
            "28 mg/g（轻度升高）。诊断：2 型糖尿病伴周围神经病变、早期糖尿病肾病。"
            "处理：加用甲钴胺营养神经，建议每年查眼底，控制血糖与血压以延缓肾病进展。"
        ),
    },
    {
        # 干扰项：同样是"门诊记录"，但讲的是与慢病无关的急性问题
        "source_type": "visit_summaries",
        "source_id": "eval-vs-003",
        "record_type": "other",
        "title": "急诊就诊记录（急性胃肠炎）",
        "text": (
            "主诉：进食不洁食物后呕吐腹泻 8 小时。查体：体温 37.8℃，腹软，脐周轻压痛，"
            "无反跳痛。血常规白细胞 11.2×10⁹/L，中性粒细胞比例升高。诊断：急性胃肠炎。"
            "处理：补液、止吐、口服补液盐，必要时抗感染。嘱清淡饮食，如出现持续高热或"
            "血便及时复诊。既往慢病用药本次照常服用，未调整。"
        ),
    },
    # ---------------- medical_report ----------------
    {
        "source_type": "health_records",
        "source_id": "eval-mr-001",
        "record_type": "medical_report",
        "title": "年度健康体检报告",
        "text": (
            "身高 172cm，体重 78kg，BMI 26.4（超重）。血压 136/84 mmHg。"
            "腹部超声：轻度脂肪肝。颈动脉超声：双侧颈动脉内中膜增厚，未见明显斑块。"
            "胸部 X 线未见异常。心电图示窦性心律。体检结论：超重、脂肪肝、"
            "颈动脉内中膜增厚，结合高血压与糖尿病病史属心血管高危人群，"
            "建议减重、限盐、规律运动并严格控制血压血糖血脂。"
        ),
    },
    # ---------------- symptom ----------------
    {
        "source_type": "health_records",
        "source_id": "eval-sym-001",
        "record_type": "symptom",
        "title": "症状自述记录",
        "text": (
            "近期自述：快走或上楼时胸口发闷，像有东西压着，停下休息三五分钟就好；"
            "起床过快时会短暂头晕眼前发黑；夜间偶有双足麻木、像蚂蚁爬的感觉；"
            "没有明显心慌、没有夜间憋醒、没有下肢水肿。希望了解这些症状分别可能是什么原因，"
            "以及哪些需要尽快就医。"
        ),
    },
]


def post(base: str, path: str, body: dict, timeout: int = 300) -> tuple[int, str]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    req.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:400]
    except Exception as e:  # noqa: BLE001
        return -1, f"EXC {type(e).__name__}: {e}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--base",
        default=os.getenv("PHA_EVAL_BASE") or "http://localhost:13002",
        help="hostapi 地址（容器内跑用 http://hostapi:13002）",
    )
    ap.add_argument("--user-id", default=EVAL_USER_ID)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.dry_run:
        for d in CORPUS:
            print(f"{d['source_id']:16s} {d['record_type']:15s} {d['title']}")
        print(f"共 {len(CORPUS)} 篇 → user_id={args.user_id}")
        return

    ok = 0
    for d in CORPUS:
        status, body = post(
            args.base,
            "/v2/rag/index",
            {
                "user_id": args.user_id,
                "source_type": d["source_type"],
                "source_id": d["source_id"],
                "text": d["text"],
                "record_type": d["record_type"],
                "title": d["title"],
            },
        )
        mark = "OK " if status == 200 else "ERR"
        print(f"[{mark}] {d['source_id']:16s} HTTP {status} {body[:120]}")
        if status == 200:
            ok += 1

    print(f"\n灌入 {ok}/{len(CORPUS)} 篇 → user_id={args.user_id} @ {args.base}")
    if ok != len(CORPUS):
        sys.exit(1)


if __name__ == "__main__":
    main()
