from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Iterable

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


@dataclass(frozen=True)
class QuestionStats:
    question: object
    keywords: tuple[str, ...]
    difficulty: int
    risk_score: int


class QuestionBank:
    def __init__(self, questions: Iterable[object]) -> None:
        self._stats: list[QuestionStats] = []
        self._index: dict[str, list[QuestionStats]] = defaultdict(list)
        for question in questions:
            keywords = self._extract_keywords(question.text)
            difficulty = self._difficulty_from_text(question.text)
            risk_score = difficulty * max(1, len(keywords))
            stats = QuestionStats(
                question=question,
                keywords=tuple(keywords),
                difficulty=difficulty,
                risk_score=risk_score,
            )
            self._stats.append(stats)
            for keyword in keywords:
                self._index[keyword].append(stats)
        for keyword, items in self._index.items():
            self._index[keyword] = self._merge_sort(items, key=lambda s: s.risk_score, reverse=True)

    @property
    def stats(self) -> list[QuestionStats]:
        return list(self._stats)

    def ranked(self) -> list[QuestionStats]:
        return self._merge_sort(self._stats, key=lambda s: s.risk_score, reverse=True)

    def keyword_matches(self, keyword: str) -> list[QuestionStats]:
        return list(self._index.get(keyword, []))

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        words = ["".join(ch for ch in token if ch.isalpha()) for token in text.lower().split()]
        return [word for word in words if word and word not in STOP_WORDS and len(word) > 3]

    @staticmethod
    def _difficulty_from_text(text: str) -> int:
        hash_value = 0
        for idx, char in enumerate(text.lower()):
            hash_value = (hash_value * 31 + ord(char) + idx) % 97
        return 1 + (hash_value % 5)

    def _merge_sort(self, items: list[QuestionStats], key, reverse: bool) -> list[QuestionStats]:
        if len(items) <= 1:
            return items
        mid = len(items) // 2
        left = self._merge_sort(items[:mid], key=key, reverse=reverse)
        right = self._merge_sort(items[mid:], key=key, reverse=reverse)
        return self._merge(left, right, key=key, reverse=reverse)

    @staticmethod
    def _merge(left: list[QuestionStats], right: list[QuestionStats], key, reverse: bool) -> list[QuestionStats]:
        merged: list[QuestionStats] = []
        i = 0
        j = 0
        while i < len(left) and j < len(right):
            if (key(left[i]) >= key(right[j])) == reverse:
                merged.append(left[i])
                i += 1
            else:
                merged.append(right[j])
                j += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged


class SafetyGraph:
    def __init__(self) -> None:
        self._edges: dict[str, set[str]] = defaultdict(set)

    def add_edge(self, start: str, end: str) -> None:
        self._edges[start].add(end)
        self._edges.setdefault(end, set())

    def topological_order(self) -> list[str]:
        visited: set[str] = set()
        stack: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            for neighbor in self._edges.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor)
            stack.append(node)

        for node in list(self._edges.keys()):
            if node not in visited:
                dfs(node)
        stack.reverse()
        return stack

    def reachable(self, start: str) -> list[str]:
        visited: set[str] = {start}
        queue: deque[str] = deque([start])
        order: list[str] = []
        while queue:
            node = queue.popleft()
            order.append(node)
            for neighbor in self._edges.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return order


class AdaptiveQuizEngine:
    TOOL_PREREQS = {
        "Laser Cutter": ["protection", "ventilation", "materials"],
        "Bandsaw": ["hands", "guards", "push"],
    }

    def __init__(self, questions: Iterable[object], tool_name: str) -> None:
        self._bank = QuestionBank(questions)
        self._tool_name = tool_name

    def select_question_ids(self, limit: int) -> list[int]:
        ranked = self._bank.ranked()
        prereqs = self.TOOL_PREREQS.get(self._tool_name, [])
        selected: list[QuestionStats] = []
        used_ids: set[int] = set()

        def backtrack(index: int, covered: set[str]) -> bool:
            if len(selected) >= limit:
                return True
            if index >= len(prereqs):
                return False
            keyword = prereqs[index]
            candidates = self._bank.keyword_matches(keyword)
            for candidate in candidates:
                qid = candidate.question.id
                if qid in used_ids:
                    continue
                selected.append(candidate)
                used_ids.add(qid)
                new_covered = covered | {keyword}
                if backtrack(index + 1, new_covered):
                    return True
                selected.pop()
                used_ids.remove(qid)
            return backtrack(index + 1, covered)

        backtrack(0, set())

        for stats in ranked:
            if len(selected) >= limit:
                break
            if stats.question.id not in used_ids:
                selected.append(stats)
                used_ids.add(stats.question.id)

        return [stats.question.id for stats in selected]

    def difficulty_map(self) -> dict[int, int]:
        return {stats.question.id: stats.difficulty for stats in self._bank.stats}


class SafetyScorePolicy:
    def __init__(self, tool_name: str) -> None:
        self._tool_name = tool_name

    def pass_threshold(self) -> float:
        prereq_count = len(AdaptiveQuizEngine.TOOL_PREREQS.get(self._tool_name, []))
        return 60 + (prereq_count * 5)

    @staticmethod
    def weighted_score(correct: dict[int, bool], difficulty_map: dict[int, int]) -> float:
        total_weight = 0.0
        earned_weight = 0.0
        for question_id, is_correct in correct.items():
            difficulty = difficulty_map.get(question_id, 1)
            weight = 1 + (difficulty - 1) * 0.25
            total_weight += weight
            if is_correct:
                earned_weight += weight
        if total_weight == 0:
            return 0.0
        return (earned_weight / total_weight) * 100


class ToolSafetyPlanner:
    def __init__(self) -> None:
        self._graph = SafetyGraph()
        self._graph.add_edge("Intro Safety", "Laser Cutter")
        self._graph.add_edge("Intro Safety", "Bandsaw")
        self._graph.add_edge("Laser Cutter", "Advanced CNC")

    def learning_path(self) -> list[str]:
        return self._graph.topological_order()

    def reachable_tools(self, start: str) -> list[str]:
        return self._graph.reachable(start)
