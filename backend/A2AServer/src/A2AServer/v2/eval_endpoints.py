"""
v2/eval — admin agent evaluation endpoints (WS-A)

GET  /v2/eval/latest     读取最近一次评测结果（无需 job_id, dashboard 默认页用）
POST /v2/eval/run        启动后台评测（subprocess → 文件 → 状态 in-memory）
GET  /v2/eval/status/{id} 查 job 状态
GET  /v2/eval/jobs       列历史 job

设计:
- 评测 runner 是独立的 CLI 脚本 tests/performance/agent_eval.py，跑在子进程
  里 → 隔离栈空间、可被 dashboard 强制 kill、不会污染主进程内存
- job 状态保存在内存 dict（_JOBS），进程重启会清空（可接受：评测不是热路径）
- 输出文件路径: /tmp/agent_eval_metrics_{job_id}.json（容器内）；同 docker volume
  时宿主机可直接 cat
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from .admin_api import _get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v2/eval", tags=["eval"])


# ============================================================
# 内存 job 状态（重启清空，符合评测非热路径的定位）
# ============================================================
_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()

DEFAULT_DATASET = "/code/tests/performance/agent_eval_dataset.json"
DEFAULT_OUTPUT_DIR = "/tmp/agent_eval_runs"


class RunBody(BaseModel):
    categories: list[str] = []           # [] = 全部
    limit: int = 0                       # 0 = 不限
    base: str = ""                       # 留空 = runner 用 env PROBE_BASE
    user: str = ""
    password: str = ""
    dataset: str = ""                    # 留空 = DEFAULT_DATASET


def _pick_dataset_path(body: RunBody) -> str:
    """兼容开发机的不同挂载点"""
    if body.dataset:
        return body.dataset
    # 优先 /code（容器内 A2AServer 代码根），其次 /app, /tmp, 最后相对路径
    for p in [
        DEFAULT_DATASET,
        "/app/tests/performance/agent_eval_dataset.json",
        "/tmp/agent_eval_dataset.json",
    ]:
        if Path(p).exists():
            return p
    return DEFAULT_DATASET


def _find_runner() -> str:
    """定位 agent_eval.py；mount 路径不固定，挨个试"""
    candidates = [
        "/code/tests/performance/agent_eval.py",
        "/app/tests/performance/agent_eval.py",
        "/tmp/agent_eval.py",
        "tests/performance/agent_eval.py",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return candidates[0]


def _latest_output_path() -> Optional[str]:
    """扫一遍输出目录，返回最新 .json"""
    d = Path(DEFAULT_OUTPUT_DIR)
    if not d.exists():
        return None
    files = sorted(d.glob("agent_eval_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def _status_from_fs(output_path: str) -> str:
    """从文件系统推导 job 状态（避免跨 worker 内存不一致）。
       - 存在 .json → done
       - 存在 .err → error
       - 否则 → running
    """
    if Path(output_path).exists():
        return "done"
    if Path(output_path + ".err").exists():
        return "error"
    return "running"


@router.get("/latest")
async def get_latest(req: Request):
    """返回最近一次评测的完整 summary；没有就 404。"""
    _get_admin_user(req)
    p = _latest_output_path()
    if not p:
        raise HTTPException(status_code=404, detail="暂无评测结果，请先 POST /v2/eval/run")
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读评测结果失败: {e}")


@router.post("/run")
async def run_eval(body: RunBody, req: Request):
    """启动后台评测 → 立即返回 job_id"""
    _get_admin_user(req)
    job_id = f"eval_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    output_path = str(Path(DEFAULT_OUTPUT_DIR) / f"agent_eval_{job_id}.json")
    Path(DEFAULT_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "started_at": datetime.utcnow().isoformat() + "Z",
            "output_path": output_path,
            "categories": body.categories or "all",
            "limit": body.limit,
            "elapsed_sec": None,
            "error": None,
        }

    # 用线程跑 subprocess（subprocess 本身不会阻塞 FastAPI 事件循环，
    # 但我们要把 stdout 吸走避免管道填满，所以在线程里同步等）
    def _runner():
        try:
            with _JOBS_LOCK:
                _JOBS[job_id]["status"] = "running"
            t0 = time.perf_counter()
            runner = _find_runner()
            dataset = _pick_dataset_path(body)
            cmd = [
                sys.executable, runner,
                "--dataset", dataset,
                "--output", output_path,
            ]
            if body.categories:
                cmd += ["--categories", *body.categories]
            if body.limit > 0:
                cmd += ["--limit", str(body.limit)]
            if body.base:
                cmd += ["--base", body.base]
            if body.user:
                cmd += ["--user", body.user]
            if body.password:
                cmd += ["--password", body.password]
            logger.info(f"[eval] job={job_id} start: {' '.join(cmd)}")
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=900,  # 15 分钟硬上限
                cwd="/app" if Path("/app").exists() else "/code",
            )
            elapsed = round(time.perf_counter() - t0, 2)
            if proc.returncode != 0:
                # 写 .err sidecar，让其他 worker 也能看到错误
                err_msg = (proc.stderr or proc.stdout or "")[:1000]
                try:
                    Path(output_path + ".err").write_text(err_msg, encoding="utf-8")
                except Exception:
                    pass
            with _JOBS_LOCK:
                if job_id in _JOBS:
                    if proc.returncode == 0:
                        _JOBS[job_id]["status"] = "done"
                    else:
                        _JOBS[job_id]["status"] = "error"
                    _JOBS[job_id]["elapsed_sec"] = elapsed
            logger.info(f"[eval] job={job_id} returncode={proc.returncode} elapsed={elapsed}s")
        except subprocess.TimeoutExpired:
            try:
                Path(output_path + ".err").write_text("subprocess timeout (>900s)", encoding="utf-8")
            except Exception:
                pass
        except Exception as e:
            try:
                Path(output_path + ".err").write_text(str(e), encoding="utf-8")
            except Exception:
                pass
            logger.exception(f"[eval] job={job_id} crashed: {e}")

    threading.Thread(target=_runner, daemon=True).start()
    return {
        "job_id": job_id,
        "status": "queued",
        "output_path": output_path,
        "poll_url": f"/v2/eval/status/{job_id}",
    }


@router.get("/status/{job_id}")
async def get_status(job_id: str, req: Request):
    """状态从文件系统推导（多 worker 安全）。
       内存 dict 只用于补充 error message。
    """
    _get_admin_user(req)
    output_path = str(Path(DEFAULT_OUTPUT_DIR) / f"agent_eval_{job_id}.json")
    status = _status_from_fs(output_path)
    out: dict = {
        "job_id": job_id,
        "status": status,
        "output_path": output_path,
    }
    # 错误信息从 .err sidecar 读
    err_path = Path(output_path + ".err")
    if err_path.exists():
        try:
            out["error"] = err_path.read_text(encoding="utf-8")[:1000]
        except Exception:
            pass
    if status == "done":
        try:
            data = json.loads(Path(output_path).read_text(encoding="utf-8"))
            out["elapsed_sec"] = data.get("total_elapsed_sec")
        except Exception:
            pass
    if status in ("done", "error"):
        # 已结束的文件确实在磁盘上，说明 job 存在
        return out
    # 状态是 running：补 started_at 估计值（从 job_id 解析时间戳）
    try:
        ts = int(job_id.split("_")[1])
        out["started_at"] = datetime.utcfromtimestamp(ts).isoformat() + "Z"
    except Exception:
        pass
    return out


@router.get("/jobs")
async def list_jobs(req: Request):
    """从输出目录扫 .json/.err 文件得到 jobs 列表（多 worker 安全）"""
    _get_admin_user(req)
    d = Path(DEFAULT_OUTPUT_DIR)
    out = []
    if d.exists():
        for p in d.glob("agent_eval_*.json"):
            job_id = p.name.replace("agent_eval_", "").replace(".json", "")
            try:
                stat = p.stat()
                out.append({
                    "job_id": job_id,
                    "status": "done",
                    "output_path": str(p),
                    "mtime": stat.st_mtime,
                })
            except Exception:
                pass
        for p in d.glob("agent_eval_*.json.err"):
            job_id = p.name.replace("agent_eval_", "").replace(".json.err", "")
            out.append({
                "job_id": job_id,
                "status": "error",
                "output_path": str(p).replace(".err", ""),
                "mtime": p.stat().st_mtime,
            })
    out.sort(key=lambda x: x.get("mtime", 0), reverse=True)
    return {
        "jobs": out[:20],
        "latest_output": _latest_output_path(),
    }
