"""A small guard for specific, easily-fabricated claims.

This is not a general truth checker. It targets the cases where an agent is
most likely to guess: prices, acquisitions, hardware capacities, exact latency
numbers, named people and dates. If the question asks for one of these and the
evidence contains neither the intent term nor the entity, the report should
abstain instead of inventing a number.
"""

from __future__ import annotations

import re

_ENTITY = re.compile(r"[A-Za-z]*\d+[A-Za-z0-9]*")

_SPECIFIC_INTENTS: dict[str, tuple[str, ...]] = {
    "price": ("价格", "售价", "授权费", "多少钱", "费用", "price", "pricing", "cost"),
    "acquisition": ("收购", "并购", "被哪家公司", "acquired", "acquisition", "merger"),
    "capacity": ("显存", "容量", "hbm", "vram", "memory capacity"),
    "latency": ("p99", "p95", "精确延迟", "exact latency"),
    "person_date": ("诺贝尔", "得主", "哪一年", "谁", "who won", "when did"),
}

_GENERIC_ENTITIES = {"3", "4", "5", "8", "70", "2026", "llm", "rag", "gpu", "api"}


def _entities(question: str) -> list[str]:
    return [
        value.lower()
        for value in _ENTITY.findall(question)
        if value.lower() not in _GENERIC_ENTITIES
    ]


def unsupported_specific_claim(question: str, evidence_text: str) -> str | None:
    question_lower = question.lower()
    evidence_lower = evidence_text.lower()
    entities = _entities(question)
    for intent, terms in _SPECIFIC_INTENTS.items():
        if not any(term in question_lower for term in terms):
            continue
        if entities and not any(entity in evidence_lower for entity in entities):
            return f"missing entity for {intent}"
        if not any(term in evidence_lower for term in terms):
            return f"missing {intent} evidence"
    return None
