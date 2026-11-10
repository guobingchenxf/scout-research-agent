"""Rule grader and LLM judge for Scout evaluation."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from ..llm import ChatModel, LLMError, extract_json
from ..models import Citation, EvalCategory, EvalTask, Report
from ..storage import SQLiteStore

_ASCII = re.compile(r"[A-Za-z0-9_]+")
_CJK = re.compile(r"[一-鿿]+")
_WHITESPACE = re.compile(r"\s+")

_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "are",
    "was",
    "were",
    "have",
    "has",
    "into",
    "using",
    "based",
    "their",
    "which",
    "when",
    "what",
    "how",
    "does",
    "not",
    "can",
    "may",
    "use",
    "used",
}


def _normalize(text: str) -> str:
    return _WHITESPACE.sub(" ", text.lower()).strip()


def key_terms_by_language(text: str) -> tuple[set[str], set[str]]:
    english = {
        word
        for word in _ASCII.findall(text.lower())
        if len(word) >= 3 and word not in _STOPWORDS
    }
    chinese: set[str] = set()
    for run in _CJK.findall(text):
        chinese.update(run[index : index + 2] for index in range(len(run) - 1))
    return english, chinese


def fact_coverage(gold: str, answer: str) -> float:
    english, chinese = key_terms_by_language(gold)
    answer_norm = _normalize(answer)
    english_coverage = (
        sum(1 for term in english if term in answer_norm) / len(english) if english else 0.0
    )
    chinese_coverage = (
        sum(1 for term in chinese if term in answer) / len(chinese) if chinese else 0.0
    )
    if english or chinese:
        return max(english_coverage, chinese_coverage)
    return 1.0 if _normalize(gold) in answer_norm else 0.0


class GradeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    passed: bool
    score: float = 0.0
    citation_support_rate: float = 0.0
    failure_category: str | None = None
    reasons: list[str] = Field(default_factory=list)


class RuleGrader:
    def __init__(self, store: SQLiteStore | None = None, *, min_fact_coverage: float = 0.6) -> None:
        self.store = store
        self.min_fact_coverage = min_fact_coverage

    def grade(
        self,
        task: EvalTask,
        answer: str,
        citations: list[Citation],
        *,
        report: Report | None = None,
    ) -> GradeResult:
        reasons: list[str] = []
        answer_norm = _normalize(answer)
        insufficient = (
            "insufficient_evidence" in answer_norm
            or "insufficient evidence" in answer_norm
            or "证据不足" in answer
            or "没有足够" in answer
        )

        if task.category == EvalCategory.ABSTENTION:
            if insufficient:
                for phrase in task.forbidden_claims:
                    if _normalize(phrase) and _normalize(phrase) in answer_norm:
                        return GradeResult(
                            task_id=task.id,
                            passed=False,
                            failure_category="over_answer",
                            reasons=[f"forbidden claim in abstention: {phrase}"],
                        )
                return GradeResult(
                    task_id=task.id,
                    passed=True,
                    score=1.0,
                    citation_support_rate=1.0,
                )
            return GradeResult(
                task_id=task.id,
                passed=False,
                failure_category="over_answer",
                reasons=["abstention task was answered without abstaining"],
            )

        if insufficient:
            return GradeResult(
                task_id=task.id,
                passed=False,
                failure_category="over_abstention",
                reasons=["answer abstained on an answerable task"],
            )

        for phrase in task.forbidden_claims:
            if _normalize(phrase) and _normalize(phrase) in answer_norm:
                return GradeResult(
                    task_id=task.id,
                    passed=False,
                    failure_category="forbidden_claim",
                    reasons=[f"forbidden claim present: {phrase}"],
                )

        coverage = fact_coverage(task.gold_answer, answer)
        if coverage < self.min_fact_coverage:
            reasons.append(f"gold fact coverage {coverage:.2f} < {self.min_fact_coverage}")

        citation_ids = {citation.doc_id for citation in citations}
        citation_ids.update(re.findall(r"\[([A-Za-z0-9_:\-./]+)\]", answer))
        missing = [doc_id for doc_id in task.required_citations if doc_id not in citation_ids]
        if missing:
            reasons.append(f"missing required citations: {missing}")

        support_rate = self._citation_support_rate(citations)
        if citations and support_rate < 0.5:
            reasons.append(f"citation support rate {support_rate:.2f} < 0.50")

        if task.category == EvalCategory.CONFLICT and task.require_conflict:
            has_conflict = bool(report and report.conflicts)
            if not has_conflict:
                has_conflict = any(
                    marker in answer_norm
                    for marker in ("conflict", "disagree", "contradiction", "矛盾", "分歧")
                )
            if not has_conflict:
                reasons.append("conflict task did not expose a conflict")

        if reasons:
            return GradeResult(
                task_id=task.id,
                passed=False,
                score=coverage,
                citation_support_rate=support_rate,
                failure_category=self._categorize(reasons),
                reasons=reasons,
            )
        return GradeResult(
            task_id=task.id,
            passed=True,
            score=coverage,
            citation_support_rate=support_rate,
        )

    def _citation_support_rate(self, citations: list[Citation]) -> float:
        if not citations:
            return 0.0
        if self.store is None:
            return 0.0
        supported = 0
        checked = 0
        for citation in citations:
            document = self.store.get_document(citation.doc_id)
            if document is None:
                continue
            checked += 1
            quote = _normalize(citation.quote)
            if quote and quote in _normalize(document.text):
                supported += 1
        return supported / checked if checked else 0.0

    def _categorize(self, reasons: list[str]) -> str:
        joined = " ".join(reasons)
        if "coverage" in joined:
            return "missing_fact"
        if "citations" in joined:
            return "missing_citation"
        if "citation support" in joined:
            return "citation_mismatch"
        if "conflict" in joined:
            return "conflict_missed"
        return "rule_failure"


class JudgeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: float
    rationale: str = ""


class LLMJudge:
    def __init__(self, llm: ChatModel, model: str = "deepseek-flash") -> None:
        self.llm = llm
        self.model = model

    def judge(self, task: EvalTask, answer: str) -> JudgeResult:
        prompt = (
            "You are an evaluation judge. Score the answer from 1 to 5.\n"
            "Rubric: factual correctness, citation support, completeness, conflict handling.\n"
            f"Question: {task.question}\n"
            f"Gold answer: {task.gold_answer}\n"
            f"Required citations: {task.required_citations}\n"
            f"Answer: {answer}\n"
            'Return JSON: {"score": 1-5, "rationale": "..."}'
        )
        response = self.llm.chat(
            [{"role": "user", "content": prompt}],
            model=self.model,
            temperature=0.0,
            max_tokens=300,
        )
        try:
            data = extract_json(response.content)
        except LLMError:
            return JudgeResult(score=0.0, rationale="judge returned invalid JSON")
        if not isinstance(data, dict):
            return JudgeResult(score=0.0, rationale="judge returned non-object JSON")
        try:
            score = float(data.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
        return JudgeResult(score=score, rationale=str(data.get("rationale", "")))
