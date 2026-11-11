"""Sequential, reproducible evaluation runner."""

from __future__ import annotations

import time

from ..config import ScoutConfig
from ..llm import LLMClient
from ..models import EvalResult, EvalTask
from ..retrieval import HybridIndex
from ..storage import SQLiteStore
from .baselines import (
    EvalOutput,
    run_react_no_reflect,
    run_scout,
    run_single_shot_rag,
)
from .graders import RuleGrader
from .metrics import summarize


class EvalRunner:
    def __init__(
        self,
        config: ScoutConfig,
        store: SQLiteStore,
        index: HybridIndex,
        tasks: list[EvalTask],
    ) -> None:
        self.config = config
        self.store = store
        self.index = index
        self.tasks = tasks
        self.grader = RuleGrader(store)

    def run(
        self,
        *,
        system: str = "scout",
        planner: str = "mock",
        limit: int | None = None,
        categories: set[str] | None = None,
        split: str | None = None,
    ) -> list[EvalResult]:
        selected = [
            task
            for task in self.tasks
            if (categories is None or task.category.value in categories)
            and (split is None or split == "all" or task.split == split)
        ]
        if limit:
            selected = selected[:limit]
        llm: LLMClient | None = None
        if system != "scout" and planner == "deepseek":
            if not self.config.deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY is not configured")
            if not self.config.model_allowed(self.config.model_planner):
                raise ValueError(f"model is not allowed: {self.config.model_planner}")
            llm = LLMClient(
                self.config.deepseek_base_url,
                self.config.deepseek_api_key,
                timeout=self.config.llm_timeout_seconds,
                max_retries=self.config.llm_max_retries,
                backoff=self.config.llm_backoff_seconds,
            )
        results: list[EvalResult] = []
        try:
            for task in selected:
                started = time.perf_counter()
                try:
                    output = self._run_one(task, system, planner, llm)
                    grade = self.grader.grade(
                        task,
                        output.answer,
                        output.citations,
                        report=output.report,
                    )
                    result = EvalResult(
                        task_id=task.id,
                        passed=grade.passed,
                        answer=output.answer,
                        citation_support_rate=grade.citation_support_rate,
                        metrics={
                            "steps": float(output.steps),
                            "tokens": float(output.tokens),
                        },
                        failure_category=grade.failure_category,
                        cost_usd=output.cost_usd,
                        latency_ms=(time.perf_counter() - started) * 1000.0,
                    )
                    results.append(result)
                except Exception:  # noqa: BLE001 - one bad task must not stop the suite
                    results.append(
                        EvalResult(
                            task_id=task.id,
                            passed=False,
                            answer="",
                            failure_category="runtime_error",
                            metrics={"steps": 0.0, "tokens": 0.0},
                            latency_ms=(time.perf_counter() - started) * 1000.0,
                        )
                    )
        finally:
            if llm is not None:
                llm.close()
        return results

    def _run_one(
        self,
        task: EvalTask,
        system: str,
        planner: str,
        llm: LLMClient | None,
    ) -> EvalOutput:
        if system == "scout":
            return run_scout(
                task.question,
                self.config,
                self.store,
                self.index,
                planner_name=planner,
                max_steps=task.max_steps,
                constraints=task.constraints,
            )
        if system == "single_shot_rag":
            return run_single_shot_rag(
                task.question,
                self.index,
                llm,
                model=self.config.model_planner,
            )
        if system == "react_no_reflect":
            return run_react_no_reflect(
                task.question,
                self.index,
                llm,
                model=self.config.model_planner,
            )
        raise ValueError(f"unknown system: {system}")

    def summary(self, results: list[EvalResult]) -> dict:
        return summarize(results, self.tasks)
