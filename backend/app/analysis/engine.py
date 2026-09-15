from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.models import AnalysisResult, AnalysisTask, ContextSummary, Message, TaskLog
from app.services.chat import add_message, conversation_dirs, ensure_conversation_dirs, list_messages
from app.services.config_service import get_config

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]


async def _emit(emit: EmitFn, event_type: str, payload: dict[str, Any]) -> None:
    await emit({"type": event_type, **payload})


def _log(db: Session, task_id: int, content: str, level: str = "INFO", log_type: str = "runtime") -> None:
    db.add(TaskLog(task_id=task_id, log_level=level, log_type=log_type, log_content=content))
    db.commit()


def _update_task(db: Session, task: AnalysisTask, status: str, step: str, error: str | None = None) -> None:
    task.task_status = status
    task.current_step = step
    if status == "running" and not task.started_at:
        task.started_at = datetime.now(timezone.utc)
    if status in {"success", "failed", "cancelled"}:
        task.finished_at = datetime.now(timezone.utc)
    if error:
        task.error_message = error
    db.commit()


def _detect_scenario(text: str) -> str:
    t = text.lower()
    if any(k in text for k in ["退款", "退货", "refund"]):
        return "refund"
    if any(k in text for k in ["商品", "类目", "目录", "曝光", "点击", "转化", "搜索"]):
        return "catalog"
    if "退款" in t or "refund" in t:
        return "refund"
    return "catalog"


def _query_sqlite_samples(scenario: str) -> dict[str, Any]:
    """Read pre-seeded CSV aggregates from data/samples without requiring extra DB schemas."""
    settings = get_settings()
    sample_dir = settings.data_root / "samples" / scenario
    metrics: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    if scenario == "catalog":
        # Prefer JSON summary if present
        summary_path = sample_dir / "summary.json"
        if summary_path.exists():
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            return data
        metrics = [
            {"metric_name": "搜索曝光总量", "metric_value": 128450, "metric_unit": "次", "metric_period": "近30天"},
            {"metric_name": "点击率 CTR", "metric_value": 3.2, "metric_unit": "%", "metric_period": "近30天"},
            {"metric_name": "转化率 CVR", "metric_value": 1.1, "metric_unit": "%", "metric_period": "近30天"},
            {"metric_name": "低转化类目数", "metric_value": 4, "metric_unit": "个", "metric_period": "近30天"},
        ]
        evidence = [
            {
                "source_type": "table",
                "source_name": "search_impressions / clicks / conversions",
                "evidence_text": "家电配件、宠物用品类目曝光高但点击率低于均值 40%",
                "related_metric": "点击率 CTR",
                "confidence": 0.86,
            },
            {
                "source_type": "table",
                "source_name": "products / categories",
                "evidence_text": "标题关键词与类目标签不一致的商品占比约 18%",
                "related_metric": "转化率 CVR",
                "confidence": 0.81,
            },
        ]
        return {
            "problem_definition": "商品目录结构与搜索流量匹配度偏低，导致曝光未能有效转化为点击与成交",
            "key_metrics": metrics,
            "evidence_list": evidence,
            "conclusion_text": "主要归因于类目标签噪声与标题关键词覆盖不足，家电配件与宠物用品两个类目贡献了大部分无效曝光。",
            "missing_data_text": "缺少商品主图质量评分、搜索词意图标注、以及竞品同款价格带数据。",
            "next_action_text": "1. 对低 CTR 类目批量校正类目标签与标题关键词\n2. 对高曝光低转化 SKU 做 A/B 主图与详情页优化",
        }

    # refund scenario
    summary_path = sample_dir / "summary.json"
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    metrics = [
        {"metric_name": "退款申请量", "metric_value": 1860, "metric_unit": "单", "metric_period": "近30天"},
        {"metric_name": "退款率", "metric_value": 4.8, "metric_unit": "%", "metric_period": "近30天"},
        {"metric_name": "质量问题占比", "metric_value": 37, "metric_unit": "%", "metric_period": "近30天"},
        {"metric_name": "物流超时占比", "metric_value": 22, "metric_unit": "%", "metric_period": "近30天"},
    ]
    evidence = [
        {
            "source_type": "table",
            "source_name": "refund_requests / refund_reasons",
            "evidence_text": "质量问题与描述不符合计占比超过一半，集中在服饰与3C 配件",
            "related_metric": "退款率",
            "confidence": 0.9,
        },
        {
            "source_type": "table",
            "source_name": "orders / users",
            "evidence_text": "新客首单退款率显著高于老客，且物流超时订单退款概率提升约 2.1 倍",
            "related_metric": "物流超时占比",
            "confidence": 0.84,
        },
    ]
    return {
        "problem_definition": "近期退款率上升，需要识别主要退款模式与可干预环节",
        "key_metrics": metrics,
        "evidence_list": evidence,
        "conclusion_text": "退款抬升主要由质量/描述不符与物流超时驱动；服饰与 3C 配件是重点品类，新客首单风险更高。",
        "missing_data_text": "缺少仓配时效明细、客服会话文本、以及售后质检抽检记录。",
        "next_action_text": "1. 针对服饰/3C 强化质检与详情页一致性校验\n2. 对高风险线路设置物流时效预警并提前触达用户",
    }


def _to_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# 经营归因分析报告",
        "",
        "## 问题定义",
        data.get("problem_definition", ""),
        "",
        "## 关键指标",
    ]
    for m in data.get("key_metrics", []):
        lines.append(
            f"- {m['metric_name']}: {m['metric_value']}{m.get('metric_unit', '')} ({m.get('metric_period', '')})"
        )
    lines += ["", "## 证据列表"]
    for e in data.get("evidence_list", []):
        lines.append(
            f"- [{e.get('source_name')}] {e.get('evidence_text')} (置信度 {e.get('confidence', '')})"
        )
    lines += [
        "",
        "## 归因结论",
        data.get("conclusion_text", ""),
        "",
        "## 待补充数据",
        data.get("missing_data_text", ""),
        "",
        "## 下一步建议",
        data.get("next_action_text", ""),
    ]
    return "\n".join(lines)


async def _maybe_llm(prompt: str) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.llm_api_key:
        return None
    engine = get_config("analysis.engine", "auto")
    if engine == "rule":
        return None
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是经营归因分析助手。请严格输出 JSON，字段："
                                "problem_definition, key_metrics(数组含 metric_name/metric_value/metric_unit/metric_period),"
                                "evidence_list(数组含 source_type/source_name/evidence_text/related_metric/confidence),"
                                "conclusion_text, missing_data_text, next_action_text(至少两条建议)。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
    except Exception:
        return None


def _maybe_summarize(db: Session, conversation_id: int) -> None:
    settings = get_settings()
    messages = list_messages(db, conversation_id)
    if len(messages) < settings.context_summary_threshold:
        return
    # Summarize oldest half not yet covered
    last_summary = (
        db.query(ContextSummary)
        .filter(ContextSummary.conversation_id == conversation_id)
        .order_by(ContextSummary.end_seq_no.desc())
        .first()
    )
    start = (last_summary.end_seq_no + 1) if last_summary else 1
    candidates = [m for m in messages if m.seq_no >= start]
    if len(candidates) < settings.context_summary_threshold // 2:
        return
    chunk = candidates[: settings.context_summary_threshold // 2]
    text = "；".join(f"{m.role}:{m.content[:80]}" for m in chunk)
    summary = ContextSummary(
        conversation_id=conversation_id,
        start_seq_no=chunk[0].seq_no,
        end_seq_no=chunk[-1].seq_no,
        summary_text=f"历史摘要：{text[:800]}",
    )
    db.add(summary)
    db.commit()


async def run_analysis_task(task_id: int, emit: EmitFn) -> None:
    db = SessionLocal()
    try:
        task = db.get(AnalysisTask, task_id)
        if not task:
            return
        if task.task_status == "cancelled":
            return

        await _emit(emit, "message_start", {"task_id": task.id, "conversation_id": task.conversation_id})
        _update_task(db, task, "running", "preparing")
        await _emit(
            emit,
            "task_status",
            {"task_id": task.id, "task_status": "running", "current_step": "preparing"},
        )
        _log(db, task.id, "任务开始")

        # Simulate streaming thought
        for delta in ["正在理解业务问题…", "正在检索相关数据…", "正在归纳归因结论…"]:
            task = db.get(AnalysisTask, task_id)
            if task and task.task_status == "cancelled":
                await _emit(emit, "error", {"task_id": task_id, "error_message": "任务已取消"})
                return
            await _emit(emit, "message_delta", {"task_id": task_id, "delta_text": delta + "\n"})
            await asyncio.sleep(0.25)

        # Tool: db query
        await _emit(emit, "tool_start", {"task_id": task_id, "tool_name": "db_query"})
        _update_task(db, task, "running", "db_query")
        await _emit(
            emit,
            "task_status",
            {"task_id": task_id, "task_status": "running", "current_step": "db_query"},
        )
        scenario = _detect_scenario(task.input_text)
        await asyncio.sleep(0.3)
        rule_data = _query_sqlite_samples(scenario)
        await _emit(
            emit,
            "tool_finish",
            {
                "task_id": task_id,
                "tool_name": "db_query",
                "tool_result_summary": f"场景={scenario}，指标数={len(rule_data.get('key_metrics', []))}",
            },
        )
        add_message(
            db,
            task.conversation_id,
            role="tool",
            content=f"db_query:{scenario}",
            message_type="tool",
            tool_name="db_query",
            tool_status="success",
        )

        # Tool: file write workspace
        await _emit(emit, "tool_start", {"task_id": task_id, "tool_name": "file_write"})
        dirs = ensure_conversation_dirs(task.user_id, task.conversation_id)
        tmp = dirs["workspace"] / f"task_{task_id}_scratch.json"
        tmp.write_text(json.dumps(rule_data, ensure_ascii=False, indent=2), encoding="utf-8")
        await _emit(
            emit,
            "tool_finish",
            {
                "task_id": task_id,
                "tool_name": "file_write",
                "tool_result_summary": f"写入 {tmp.name}",
            },
        )

        # Optional LLM enrichment
        _update_task(db, task, "running", "reasoning")
        await _emit(
            emit,
            "task_status",
            {"task_id": task_id, "task_status": "running", "current_step": "reasoning"},
        )
        history = list_messages(db, task.conversation_id)
        prompt = f"用户问题：{task.input_text}\n已有分析结果：{json.dumps(rule_data, ensure_ascii=False)}"
        llm_data = await _maybe_llm(prompt)
        data = llm_data or rule_data

        md = _to_markdown(data)
        export_path = dirs["exports"] / f"result_task_{task_id}.md"
        export_path.write_text(md, encoding="utf-8")

        result = AnalysisResult(
            task_id=task.id,
            conversation_id=task.conversation_id,
            problem_definition=data.get("problem_definition", ""),
            key_metrics_json=data.get("key_metrics", []),
            evidence_list_json=data.get("evidence_list", []),
            conclusion_text=data.get("conclusion_text", ""),
            missing_data_text=data.get("missing_data_text", ""),
            next_action_text=data.get("next_action_text", ""),
            result_markdown=md,
            result_file_path=str(export_path),
        )
        db.add(result)
        db.commit()
        db.refresh(result)

        add_message(db, task.conversation_id, role="assistant", content=md, message_type="result")
        _maybe_summarize(db, task.conversation_id)

        _update_task(db, task, "success", "done")
        await _emit(
            emit,
            "task_status",
            {"task_id": task_id, "task_status": "success", "current_step": "done"},
        )
        await _emit(emit, "result_ready", {"task_id": task_id, "result_id": result.id})
        finished = datetime.now(timezone.utc).isoformat()
        await _emit(emit, "done", {"task_id": task_id, "finished_at": finished})
        _log(db, task.id, "任务完成")
    except Exception as exc:  # noqa: BLE001
        task = db.get(AnalysisTask, task_id)
        if task:
            _update_task(db, task, "failed", "error", error=str(exc))
            _log(db, task.id, f"失败: {exc}", level="ERROR")
        await _emit(emit, "error", {"task_id": task_id, "error_message": str(exc)})
        await _emit(
            emit,
            "done",
            {"task_id": task_id, "finished_at": datetime.now(timezone.utc).isoformat()},
        )
    finally:
        db.close()
