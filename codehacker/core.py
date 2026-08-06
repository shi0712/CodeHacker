"""Framework-agnostic primitives for the CodeHacker two-phase workflow.

Phase I calibrates the validator and checker with adversarial probes. Phase II
uses the calibrated tools to judge submission-specific candidate inputs. The
interfaces deliberately do not depend on a particular LLM or sandbox backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, Iterable, Protocol, Sequence, TypeVar


class Verdict(str, Enum):
    """Verdicts produced by the minimal judge."""

    ACCEPTED = "AC"
    WRONG_ANSWER = "WA"
    RUNTIME_ERROR = "RE"
    TIME_LIMIT_EXCEEDED = "TLE"
    MEMORY_LIMIT_EXCEEDED = "MLE"
    INVALID_INPUT = "INVALID"
    JUDGE_ERROR = "JUDGE_ERROR"


class Validator(Protocol):
    def __call__(self, input_data: str) -> bool:
        """Return whether ``input_data`` satisfies the problem constraints."""


class Checker(Protocol):
    def __call__(self, input_data: str, output_data: str) -> bool:
        """Return whether ``output_data`` is a valid answer for ``input_data``."""


class Submission(Protocol):
    def __call__(self, input_data: str) -> str:
        """Execute a solution and return its standard output."""


@dataclass(frozen=True)
class ValidationProbe:
    input_data: str
    expected_valid: bool
    label: str


@dataclass(frozen=True)
class CheckerProbe:
    input_data: str
    output_data: str
    expected_accepted: bool
    label: str


class ValidatorAgent(Protocol):
    def initial(self, problem_spec: str) -> Validator:
        """Generate the first validator draft."""

    def attack(
        self, problem_spec: str, validator: Validator
    ) -> Sequence[ValidationProbe]:
        """Propose valid and invalid inputs that may fool the validator."""

    def refine(
        self,
        problem_spec: str,
        validator: Validator,
        failures: Sequence[ValidationProbe],
    ) -> Validator:
        """Regenerate or patch the validator using observed failures."""


class CheckerAgent(Protocol):
    def initial(self, problem_spec: str) -> Checker:
        """Generate the first checker draft."""

    def attack(self, problem_spec: str, checker: Checker) -> Sequence[CheckerProbe]:
        """Propose false-positive and false-negative checker probes."""

    def refine(
        self,
        problem_spec: str,
        checker: Checker,
        failures: Sequence[CheckerProbe],
    ) -> Checker:
        """Regenerate or patch the checker using oracle-confirmed failures."""


@dataclass(frozen=True)
class CalibrationRound:
    index: int
    failed_labels: tuple[str, ...]
    consecutive_clean_rounds: int


ToolT = TypeVar("ToolT")


@dataclass(frozen=True)
class CalibrationResult(Generic[ToolT]):
    tool: ToolT
    trace: tuple[CalibrationRound, ...]
    refinements: int
    stable_rounds: int


def _validate_calibration_limits(stable_rounds: int, max_rounds: int) -> None:
    if stable_rounds < 1:
        raise ValueError("stable_rounds must be at least 1")
    if max_rounds < stable_rounds:
        raise ValueError("max_rounds must be >= stable_rounds")


def calibrate_validator(
    problem_spec: str,
    agent: ValidatorAgent,
    *,
    stable_rounds: int = 2,
    max_rounds: int = 20,
) -> CalibrationResult[Validator]:
    """Implement Algorithm 1's attack/refine loop for a validator.

    ``stable_rounds`` corresponds to the paper's maximum consecutive failure
    count ``K``: a clean attack round increments the counter, while a newly
    exposed flaw resets it to zero and triggers refinement.
    """

    _validate_calibration_limits(stable_rounds, max_rounds)
    validator = agent.initial(problem_spec)
    clean_rounds = 0
    refinements = 0
    trace: list[CalibrationRound] = []

    for round_index in range(1, max_rounds + 1):
        probes = tuple(agent.attack(problem_spec, validator))
        failures = tuple(
            probe
            for probe in probes
            if bool(validator(probe.input_data)) != probe.expected_valid
        )

        if failures:
            clean_rounds = 0
            validator = agent.refine(problem_spec, validator, failures)
            refinements += 1
        else:
            clean_rounds += 1

        trace.append(
            CalibrationRound(
                index=round_index,
                failed_labels=tuple(probe.label for probe in failures),
                consecutive_clean_rounds=clean_rounds,
            )
        )
        if clean_rounds >= stable_rounds:
            return CalibrationResult(
                tool=validator,
                trace=tuple(trace),
                refinements=refinements,
                stable_rounds=stable_rounds,
            )

    raise RuntimeError("validator calibration did not converge within max_rounds")


def calibrate_checker(
    problem_spec: str,
    agent: CheckerAgent,
    *,
    stable_rounds: int = 2,
    max_rounds: int = 20,
) -> CalibrationResult[Checker]:
    """Implement Algorithm 2's attack/refine loop for a checker."""

    _validate_calibration_limits(stable_rounds, max_rounds)
    checker = agent.initial(problem_spec)
    clean_rounds = 0
    refinements = 0
    trace: list[CalibrationRound] = []

    for round_index in range(1, max_rounds + 1):
        probes = tuple(agent.attack(problem_spec, checker))
        failures = tuple(
            probe
            for probe in probes
            if bool(checker(probe.input_data, probe.output_data))
            != probe.expected_accepted
        )

        if failures:
            clean_rounds = 0
            checker = agent.refine(problem_spec, checker, failures)
            refinements += 1
        else:
            clean_rounds += 1

        trace.append(
            CalibrationRound(
                index=round_index,
                failed_labels=tuple(probe.label for probe in failures),
                consecutive_clean_rounds=clean_rounds,
            )
        )
        if clean_rounds >= stable_rounds:
            return CalibrationResult(
                tool=checker,
                trace=tuple(trace),
                refinements=refinements,
                stable_rounds=stable_rounds,
            )

    raise RuntimeError("checker calibration did not converge within max_rounds")


@dataclass(frozen=True)
class HackCandidate:
    strategy: str
    input_data: str
    rationale: str


class CaseGenerator(Protocol):
    name: str

    def generate(self, plan: object) -> Iterable[HackCandidate]:
        """Yield valid candidate inputs guided by an analyst plan."""


@dataclass(frozen=True)
class EvaluationResult:
    candidate: HackCandidate
    verdict: Verdict
    expected_output: str | None
    actual_output: str | None
    detail: str

    @property
    def is_successful_hack(self) -> bool:
        return self.verdict in {
            Verdict.WRONG_ANSWER,
            Verdict.RUNTIME_ERROR,
            Verdict.TIME_LIMIT_EXCEEDED,
            Verdict.MEMORY_LIMIT_EXCEEDED,
        }


@dataclass(frozen=True)
class PhaseTwoReport:
    attempts: tuple[EvaluationResult, ...]

    @property
    def successful_hacks(self) -> tuple[EvaluationResult, ...]:
        return tuple(attempt for attempt in self.attempts if attempt.is_successful_hack)


@dataclass(frozen=True)
class Judge:
    """A minimal judge enforcing the paper's three hack conditions."""

    validator: Validator
    checker: Checker
    reference_solution: Submission
    target_submission: Submission

    def evaluate(self, candidate: HackCandidate) -> EvaluationResult:
        input_data = candidate.input_data
        if not self.validator(input_data):
            return EvaluationResult(
                candidate=candidate,
                verdict=Verdict.INVALID_INPUT,
                expected_output=None,
                actual_output=None,
                detail="the calibrated validator rejected the generated input",
            )

        try:
            expected_output = self.reference_solution(input_data)
        except Exception as exc:  # pragma: no cover - defensive boundary
            return EvaluationResult(
                candidate=candidate,
                verdict=Verdict.JUDGE_ERROR,
                expected_output=None,
                actual_output=None,
                detail=f"reference solution failed: {exc}",
            )

        if not self.checker(input_data, expected_output):
            return EvaluationResult(
                candidate=candidate,
                verdict=Verdict.JUDGE_ERROR,
                expected_output=expected_output,
                actual_output=None,
                detail="the calibrated checker rejected the reference solution",
            )

        try:
            actual_output = self.target_submission(input_data)
        except Exception as exc:
            return EvaluationResult(
                candidate=candidate,
                verdict=Verdict.RUNTIME_ERROR,
                expected_output=expected_output,
                actual_output=None,
                detail=f"target submission raised {type(exc).__name__}: {exc}",
            )

        accepted = self.checker(input_data, actual_output)
        return EvaluationResult(
            candidate=candidate,
            verdict=Verdict.ACCEPTED if accepted else Verdict.WRONG_ANSWER,
            expected_output=expected_output,
            actual_output=actual_output,
            detail=(
                "target output satisfies the calibrated checker"
                if accepted
                else "target output violates the calibrated checker"
            ),
        )


def run_phase_two(
    judge: Judge,
    plan: object,
    generators: Iterable[CaseGenerator],
    *,
    stop_on_first: bool = True,
) -> PhaseTwoReport:
    """Generate and judge adversarial cases using the calibrated Phase I tools."""

    attempts: list[EvaluationResult] = []
    for generator in generators:
        for candidate in generator.generate(plan):
            result = judge.evaluate(candidate)
            attempts.append(result)
            if stop_on_first and result.is_successful_hack:
                return PhaseTwoReport(attempts=tuple(attempts))
    return PhaseTwoReport(attempts=tuple(attempts))
