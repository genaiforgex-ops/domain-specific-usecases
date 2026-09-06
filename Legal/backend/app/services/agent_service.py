"""Coding-agent and GitHub seams for the Build Studio.

Two pluggable interfaces:

  * `CodingAgentService` — analyses a request, drafts a plan, "implements"
    the change, summarises a diff. Production swaps in a Claude Code SDK or
    Anthropic-API-driven agent.
  * `GitHubService` — creates issues / branches / PRs, merges PRs, triggers
    deploys. Production swaps in a GitHub App client (PyGithub /
    ghapi / direct REST).

The stubs here are deterministic and produce realistic-looking artefacts so
the end-to-end demo flow works without external dependencies.
"""

from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.config import settings


# ── Result types ──────────────────────────────────────────────────────────────


@dataclass
class AnalysisResult:
    summary: str
    plan: list[dict[str, Any]]
    files_touched: list[str]
    loc_estimate: int
    confidence: float


@dataclass
class ImplementationResult:
    diff_summary: str
    branch_name: str
    commit_count: int
    tests_passed: int
    tests_total: int


@dataclass
class GitHubIssue:
    number: int
    url: str


@dataclass
class GitHubPR:
    number: int
    url: str
    branch: str


@dataclass
class Deployment:
    url: str
    environment: str


# ── Interfaces ────────────────────────────────────────────────────────────────


class CodingAgentService(ABC):
    """Implement this to plug in a real coding agent (Claude Code SDK, etc.)."""

    model_version: str

    @abstractmethod
    def analyse(self, title: str, description: str, request_type: str) -> AnalysisResult: ...

    @abstractmethod
    def implement(
        self,
        title: str,
        description: str,
        plan: list[dict[str, Any]],
        files_touched: list[str],
        request_id: int,
    ) -> ImplementationResult: ...

    @abstractmethod
    def score_priority(
        self, title: str, description: str, request_type: str
    ) -> tuple[str, float, str]:
        """Return (priority_label, score, rationale)."""


class GitHubService(ABC):
    """Implement this to plug in real GitHub App integration."""

    @abstractmethod
    def create_issue(self, title: str, body: str, labels: list[str], request_id: int) -> GitHubIssue: ...

    @abstractmethod
    def open_pull_request(
        self,
        title: str,
        body: str,
        branch: str,
        issue_number: int | None,
        request_id: int,
    ) -> GitHubPR: ...

    @abstractmethod
    def merge_pull_request(self, pr_number: int, request_id: int) -> str: ...

    @abstractmethod
    def trigger_deployment(self, pr_number: int, request_id: int) -> Deployment: ...


# ── Stub implementations ──────────────────────────────────────────────────────


def _slugify(text: str, max_len: int = 48) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:max_len] or "request"


def _stable_int(seed: str, lo: int, hi: int) -> int:
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    return lo + (h % (hi - lo + 1))


_BUG_FILE_PATTERNS = [
    "backend/app/api/{slug}.py",
    "backend/app/services/{slug}_service.py",
    "frontend/src/pages/{Slug}.tsx",
    "frontend/src/lib/api.ts",
]

_FEATURE_FILE_PATTERNS = [
    "backend/app/models/{slug}.py",
    "backend/app/schemas/{slug}.py",
    "backend/app/api/{slug}.py",
    "frontend/src/pages/{Slug}.tsx",
    "frontend/src/components/{Slug}Card.tsx",
    "frontend/src/lib/api.ts",
    "frontend/src/types/index.ts",
    "README.md",
]


class StubCodingAgentService(CodingAgentService):
    def __init__(self, model_version: str = "legalos-agent-stub-0.1") -> None:
        self.model_version = model_version

    def analyse(self, title: str, description: str, request_type: str) -> AnalysisResult:
        slug = _slugify(title)
        slug_pascal = "".join(w.capitalize() for w in slug.split("-") if w) or "Feature"
        templates = _BUG_FILE_PATTERNS if request_type == "bug" else _FEATURE_FILE_PATTERNS
        n_files = _stable_int(slug, 2, min(6, len(templates)))
        files = [
            t.format(slug=slug, Slug=slug_pascal) for t in templates[:n_files]
        ]
        loc = _stable_int(slug + "loc", 40, 280)
        plan_steps: list[dict[str, Any]]
        if request_type == "bug":
            plan_steps = [
                {"step": "Reproduce the reported behaviour locally", "files": []},
                {"step": "Identify the root cause", "files": files[:1]},
                {"step": "Apply the fix", "files": files[:2]},
                {"step": "Add a regression test", "files": ["backend/tests/test_" + slug + ".py"]},
                {"step": "Verify other call-sites are unaffected", "files": files},
            ]
        elif request_type == "enhancement":
            plan_steps = [
                {"step": "Survey current implementation", "files": files[:2]},
                {"step": "Design the enhancement and validate against playbook", "files": []},
                {"step": "Implement backend changes", "files": [f for f in files if f.startswith("backend/")]},
                {"step": "Wire the frontend surface", "files": [f for f in files if f.startswith("frontend/")]},
                {"step": "Update documentation", "files": ["README.md"]},
            ]
        else:  # feature
            plan_steps = [
                {"step": "Add the data model", "files": [f for f in files if "models/" in f]},
                {"step": "Define Pydantic schemas", "files": [f for f in files if "schemas/" in f]},
                {"step": "Build the API router with RBAC + audit logging", "files": [f for f in files if "api/" in f]},
                {"step": "Implement the React page + components", "files": [f for f in files if "frontend/" in f]},
                {"step": "Add the route, sidebar nav, and dashboard tile", "files": []},
                {"step": "Smoke test end-to-end", "files": []},
            ]
        summary = (
            f"Analysed {request_type}: '{title[:80]}'. {n_files} files in scope, "
            f"~{loc} LOC. Plan has {len(plan_steps)} step(s)."
        )
        confidence = round(0.6 + (_stable_int(slug + "conf", 0, 30) / 100), 2)
        return AnalysisResult(
            summary=summary,
            plan=plan_steps,
            files_touched=files,
            loc_estimate=loc,
            confidence=confidence,
        )

    def implement(
        self,
        title: str,
        description: str,
        plan: list[dict[str, Any]],
        files_touched: list[str],
        request_id: int,
    ) -> ImplementationResult:
        slug = _slugify(title)
        branch = f"agent/{slug}-{request_id}"
        loc_per_file = max(8, sum(len(f) for f in files_touched) // 3)
        commit_count = max(1, len(plan) // 2)
        tests_total = _stable_int(slug + "tests", 6, 28)
        tests_passed = tests_total  # green build (stub success scenario)
        diff_summary = (
            f"Applied {len(files_touched)} file change(s) across {commit_count} commit(s). "
            f"Tests: {tests_passed}/{tests_total} passed. Estimated lines changed: ~{loc_per_file * len(files_touched)}."
        )
        return ImplementationResult(
            diff_summary=diff_summary,
            branch_name=branch,
            commit_count=commit_count,
            tests_passed=tests_passed,
            tests_total=tests_total,
        )

    def score_priority(
        self, title: str, description: str, request_type: str
    ) -> tuple[str, float, str]:
        text = (title + " " + description).lower()
        score = 0.0
        reasons: list[str] = []
        if request_type == "bug":
            score += 18
            reasons.append("bug type")
        if any(w in text for w in ["urgent", "asap", "critical", "blocking", "p0", "broken"]):
            score += 35
            reasons.append("urgency language")
        if any(w in text for w in ["regulator", "rbi", "sebi", "irdai", "audit", "compliance"]):
            score += 18
            reasons.append("regulatory relevance")
        if any(w in text for w in ["security", "vulnerab", "leak", "breach"]):
            score += 30
            reasons.append("security concern")
        if any(w in text for w in ["nice to have", "minor", "cosmetic", "polish"]):
            score -= 10
            reasons.append("low-impact phrasing")
        if score >= 55:
            label = "P0"
        elif score >= 32:
            label = "P1"
        elif score >= 15:
            label = "P2"
        else:
            label = "P3"
        rationale = f"Priority {label} (score {round(score)}). " + (
            "; ".join(reasons) + "." if reasons else "No strong signals; default priority."
        )
        return label, round(score, 1), rationale


class StubGitHubService(GitHubService):
    """Generates realistic-looking GitHub URLs without making any HTTP calls.

    A production replacement implements the same interface with a GitHub
    App client (e.g. PyGithub) and real API calls. The rest of the platform
    is unaffected.
    """

    def __init__(self, owner: str = "jfpsl", repo: str = "legalos") -> None:
        self.owner = owner
        self.repo = repo
        self._base = f"https://github.com/{owner}/{repo}"

    def _issue_number(self, seed: str) -> int:
        return _stable_int(seed + "issue", 100, 999)

    def _pr_number(self, seed: str) -> int:
        return _stable_int(seed + "pr", 100, 999)

    def create_issue(
        self, title: str, body: str, labels: list[str], request_id: int
    ) -> GitHubIssue:
        n = self._issue_number(f"{request_id}|{title}")
        return GitHubIssue(number=n, url=f"{self._base}/issues/{n}")

    def open_pull_request(
        self,
        title: str,
        body: str,
        branch: str,
        issue_number: int | None,
        request_id: int,
    ) -> GitHubPR:
        n = self._pr_number(f"{request_id}|{title}")
        return GitHubPR(number=n, url=f"{self._base}/pull/{n}", branch=branch)

    def merge_pull_request(self, pr_number: int, request_id: int) -> str:
        sha = hashlib.sha1(f"{request_id}|{pr_number}|merge".encode()).hexdigest()[:7]
        return sha

    def trigger_deployment(self, pr_number: int, request_id: int) -> Deployment:
        # Pretend we deploy to a per-request preview env, with prod going to
        # the stable URL once the PR is on main. Demo uses a "staging" env.
        sub = _slugify(f"pr-{pr_number}")
        return Deployment(
            url=f"https://staging-{sub}.legalos.jfpsl.in",
            environment="staging",
        )


# ── Factories ─────────────────────────────────────────────────────────────────

_agent: CodingAgentService | None = None
_gh: GitHubService | None = None


def get_agent_service() -> CodingAgentService:
    global _agent
    if _agent is None:
        backend = settings.ai_backend.lower()
        if backend == "stub":
            _agent = StubCodingAgentService()
        else:
            raise NotImplementedError(
                f"AGENT backend '{backend}' is not implemented. Add a CodingAgentService "
                "subclass and register it in get_agent_service()."
            )
    return _agent


def get_github_service() -> GitHubService:
    global _gh
    if _gh is None:
        _gh = StubGitHubService()
    return _gh
