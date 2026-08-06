"""Offline CodeHacker demo based on the paper's Codeforces 1388A case study."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Iterable, Sequence

from .core import (
    CalibrationResult,
    Checker,
    CheckerProbe,
    HackCandidate,
    Judge,
    PhaseTwoReport,
    ValidationProbe,
    Validator,
    calibrate_checker,
    calibrate_validator,
    run_phase_two,
)
from .llm import LLMConfig, OpenAICompatibleLLM, TextLLM


PROBLEM_SPEC = """Codeforces 1388A - Captain Flint and Crew Recruitment
Input: t test cases (1 <= t <= 10000), followed by n (1 <= n <= 10^9).
Output: NO if impossible; otherwise YES and four distinct positive integers
whose sum is n, at least three of which are products of two distinct primes.
"""


VULNERABLE_CPP = r"""
if (n < 31) {
    cout << "NO\n";
} else {
    cout << "YES\n";
    cout << "6 10 14 " << n - 30 << "\n";
}
"""


def _parse_problem_input(input_data: str) -> tuple[int, ...] | None:
    try:
        tokens = [int(token) for token in input_data.split()]
    except ValueError:
        return None
    if not tokens:
        return None
    test_count, *values = tokens
    if test_count != len(values):
        return None
    return tuple(values)


@dataclass(frozen=True)
class CaptainFlintValidator:
    """Configurable validator used to make Phase I's repair visible."""

    minimum_n: int
    maximum_n: int | None
    enforce_case_count: bool

    def __call__(self, input_data: str) -> bool:
        try:
            tokens = [int(token) for token in input_data.split()]
        except ValueError:
            return False
        if not tokens:
            return False

        test_count, *values = tokens
        if not 1 <= test_count <= 10_000:
            return False
        if self.enforce_case_count and len(values) != test_count:
            return False
        if not values:
            return False
        return all(
            value >= self.minimum_n
            and (self.maximum_n is None or value <= self.maximum_n)
            for value in values
        )


class CaptainFlintValidatorAgent:
    def initial(self, problem_spec: str) -> Validator:
        del problem_spec
        # The draft is both too strict at the lower boundary and too loose at
        # the upper/count boundaries.
        return CaptainFlintValidator(
            minimum_n=2,
            maximum_n=None,
            enforce_case_count=False,
        )

    def attack(
        self, problem_spec: str, validator: Validator
    ) -> Sequence[ValidationProbe]:
        del problem_spec, validator
        return (
            ValidationProbe("1\n1\n", True, "valid-minimum-rejected"),
            ValidationProbe("1\n1000000001\n", False, "n-overflow-accepted"),
            ValidationProbe("2\n31\n", False, "missing-case-accepted"),
        )

    def refine(
        self,
        problem_spec: str,
        validator: Validator,
        failures: Sequence[ValidationProbe],
    ) -> Validator:
        del problem_spec, validator
        if not failures:
            raise ValueError("refine requires at least one failure")
        return CaptainFlintValidator(
            minimum_n=1,
            maximum_n=1_000_000_000,
            enforce_case_count=True,
        )


def _is_prime(value: int) -> bool:
    if value < 2:
        return False
    divisor = 2
    while divisor * divisor <= value:
        if value % divisor == 0:
            return False
        divisor += 1
    return True


def _is_nearly_prime(value: int) -> bool:
    """Return whether value is the product of two distinct primes."""

    divisor = 2
    while divisor * divisor <= value:
        if value % divisor == 0:
            other = value // divisor
            return divisor != other and _is_prime(divisor) and _is_prime(other)
        divisor += 1
    return False


@dataclass(frozen=True)
class CaptainFlintChecker:
    """A special judge with switches representing common checker flaws."""

    enforce_distinct: bool
    enforce_nearly_prime: bool
    require_first_value_six: bool

    def __call__(self, input_data: str, output_data: str) -> bool:
        values = _parse_problem_input(input_data)
        if values is None:
            return False

        tokens = output_data.split()
        cursor = 0
        for n in values:
            if cursor >= len(tokens):
                return False
            decision = tokens[cursor].upper()
            cursor += 1

            if decision == "NO":
                if n > 30:
                    return False
                continue
            if decision != "YES" or cursor + 4 > len(tokens):
                return False

            try:
                answer = tuple(int(token) for token in tokens[cursor : cursor + 4])
            except ValueError:
                return False
            cursor += 4

            if any(value <= 0 for value in answer) or sum(answer) != n:
                return False
            if self.require_first_value_six and answer[0] != 6:
                return False
            if self.enforce_distinct and len(set(answer)) != 4:
                return False
            if self.enforce_nearly_prime:
                nearly_prime_count = sum(_is_nearly_prime(value) for value in answer)
                if nearly_prime_count < 3:
                    return False

        return cursor == len(tokens)


class CaptainFlintCheckerAgent:
    def initial(self, problem_spec: str) -> Checker:
        del problem_spec
        # This draft accepts invalid canonical-looking answers while rejecting
        # valid answers whose first value is not six.
        return CaptainFlintChecker(
            enforce_distinct=False,
            enforce_nearly_prime=False,
            require_first_value_six=True,
        )

    def attack(self, problem_spec: str, checker: Checker) -> Sequence[CheckerProbe]:
        del problem_spec, checker
        input_data = "1\n36\n"
        return (
            CheckerProbe(
                input_data,
                "YES\n6 10 14 6\n",
                False,
                "duplicate-output-accepted",
            ),
            CheckerProbe(
                input_data,
                "YES\n6 8 9 13\n",
                False,
                "non-semiprime-output-accepted",
            ),
            CheckerProbe(
                input_data,
                "YES\n5 15 10 6\n",
                True,
                "valid-reordered-output-rejected",
            ),
        )

    def refine(
        self,
        problem_spec: str,
        checker: Checker,
        failures: Sequence[CheckerProbe],
    ) -> Checker:
        del problem_spec, checker
        if not failures:
            raise ValueError("refine requires at least one failure")
        return CaptainFlintChecker(
            enforce_distinct=True,
            enforce_nearly_prime=True,
            require_first_value_six=False,
        )


def captain_flint_reference(input_data: str) -> str:
    values = _parse_problem_input(input_data)
    if values is None:
        raise ValueError("invalid problem input")

    lines: list[str] = []
    for n in values:
        if n <= 30:
            lines.append("NO")
            continue
        if n - 30 in {6, 10, 14}:
            answer = (6, 10, 15, n - 31)
        else:
            answer = (6, 10, 14, n - 30)
        lines.extend(("YES", " ".join(map(str, answer))))
    return "\n".join(lines) + "\n"


def captain_flint_vulnerable(input_data: str) -> str:
    values = _parse_problem_input(input_data)
    if values is None:
        raise ValueError("invalid problem input")

    lines: list[str] = []
    for n in values:
        if n < 31:
            lines.append("NO")
        else:
            lines.extend(("YES", f"6 10 14 {n - 30}"))
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class HackPlan:
    bug_type: str
    hypothesis: str
    trigger_values: tuple[int, ...]
    uses_hashing: bool


class CaptainFlintAnalyst:
    """Deterministic stand-in for the paper's code-aware LLM analyst."""

    def analyze(self, target_source: str) -> HackPlan:
        fixed_construction = "6 10 14" in target_source and "n - 30" in target_source
        if not fixed_construction:
            return HackPlan(
                bug_type="unknown",
                hypothesis="No known vulnerable construction was recognized.",
                trigger_values=(),
                uses_hashing="hash" in target_source.lower(),
            )
        return HackPlan(
            bug_type="WA",
            hypothesis=(
                "The fourth value n-30 can collide with one of the fixed values "
                "6, 10, or 14, violating the distinctness constraint."
            ),
            trigger_values=(36, 40, 44),
            uses_hashing=False,
        )


class LLMCaptainFlintAnalyst:
    """Optional real-LLM analyst using an OpenAI-compatible endpoint."""

    def __init__(self, llm: TextLLM) -> None:
        self.llm = llm

    def analyze(self, target_source: str) -> HackPlan:
        response = self.llm.complete(
            """You are the Code Analyst in the CodeHacker framework.
Analyze a competitive-programming submission and return only one JSON object:
{
  "bug_type": "WA|RE|TLE|MLE|unknown",
  "hypothesis": "short explanation",
  "trigger_values": [integer test values],
  "uses_hashing": false
}
Every trigger must satisfy the stated input constraints. Do not include Markdown.""",
            f"Problem specification:\n{PROBLEM_SPEC}\nTarget code:\n{target_source}",
            temperature=0.7,
        )
        payload = _parse_json_object(response)
        trigger_values = tuple(int(value) for value in payload.get("trigger_values", ()))
        if any(not 1 <= value <= 1_000_000_000 for value in trigger_values):
            raise ValueError("LLM returned a trigger outside the legal input range")
        return HackPlan(
            bug_type=str(payload.get("bug_type", "unknown")),
            hypothesis=str(payload.get("hypothesis", "No hypothesis returned.")),
            trigger_values=trigger_values,
            uses_hashing=bool(payload.get("uses_hashing", False)),
        )


def _parse_json_object(text: str) -> dict[str, object]:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM response does not contain a JSON object")
    payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")
    return payload


class StressGenerator:
    name = "stress"

    def generate(self, plan: object) -> Iterable[HackCandidate]:
        del plan
        for n in (1, 31, 1_000_000_000):
            yield HackCandidate(
                strategy=self.name,
                input_data=f"1\n{n}\n",
                rationale=f"probe a legal boundary value n={n}",
            )


class LogicGuidedGenerator:
    name = "logic-guided"

    def generate(self, plan: object) -> Iterable[HackCandidate]:
        if not isinstance(plan, HackPlan):
            raise TypeError("LogicGuidedGenerator expects a HackPlan")
        for n in plan.trigger_values:
            yield HackCandidate(
                strategy=self.name,
                input_data=f"1\n{n}\n",
                rationale=f"force n-30 to equal a fixed summand ({n - 30})",
            )


class AntiHashGenerator:
    name = "anti-hash"

    def generate(self, plan: object) -> Iterable[HackCandidate]:
        if not isinstance(plan, HackPlan):
            raise TypeError("AntiHashGenerator expects a HackPlan")
        # The module is part of the Phase II portfolio but correctly stays idle
        # because the target contains no rolling hash.
        if plan.uses_hashing:
            raise NotImplementedError("the minimal demo does not implement LLL collisions")
        return ()


@dataclass(frozen=True)
class DemoReport:
    validator_calibration: CalibrationResult[Validator]
    checker_calibration: CalibrationResult[Checker]
    plan: HackPlan
    phase_two: PhaseTwoReport


def run_demo(
    *,
    stop_on_first: bool = False,
    analyst: CaptainFlintAnalyst | LLMCaptainFlintAnalyst | None = None,
) -> DemoReport:
    validator_result = calibrate_validator(
        PROBLEM_SPEC,
        CaptainFlintValidatorAgent(),
        stable_rounds=2,
    )
    checker_result = calibrate_checker(
        PROBLEM_SPEC,
        CaptainFlintCheckerAgent(),
        stable_rounds=2,
    )

    plan = (analyst or CaptainFlintAnalyst()).analyze(VULNERABLE_CPP)
    judge = Judge(
        validator=validator_result.tool,
        checker=checker_result.tool,
        reference_solution=captain_flint_reference,
        target_submission=captain_flint_vulnerable,
    )
    phase_two = run_phase_two(
        judge,
        plan,
        (StressGenerator(), LogicGuidedGenerator(), AntiHashGenerator()),
        stop_on_first=stop_on_first,
    )
    return DemoReport(
        validator_calibration=validator_result,
        checker_calibration=checker_result,
        plan=plan,
        phase_two=phase_two,
    )


def _print_calibration(name: str, result: CalibrationResult[object]) -> None:
    print(f"{name}: {result.refinements} refinement(s)")
    for round_trace in result.trace:
        failures = ", ".join(round_trace.failed_labels) or "none"
        print(
            f"  round {round_trace.index}: failures=[{failures}], "
            f"clean_streak={round_trace.consecutive_clean_rounds}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help="use LLM_API_KEY/LLM_BASE_URL/LLM_MODEL for the Code Analyst",
    )
    parser.add_argument(
        "--stop-on-first",
        action="store_true",
        help="stop Phase II after the first successful hack",
    )
    args = parser.parse_args()

    analyst: CaptainFlintAnalyst | LLMCaptainFlintAnalyst | None = None
    if args.use_llm:
        config = LLMConfig.from_env()
        analyst = LLMCaptainFlintAnalyst(OpenAICompatibleLLM(config))
        print(f"LLM: model={config.model}, base_url={config.base_url}")

    report = run_demo(stop_on_first=args.stop_on_first, analyst=analyst)

    print("=== Phase I: evaluation-tool calibration ===")
    _print_calibration("validator", report.validator_calibration)
    _print_calibration("checker", report.checker_calibration)

    print("\n=== Phase II: adversarial case generation ===")
    print(f"analyst hypothesis: {report.plan.hypothesis}")
    for attempt in report.phase_two.attempts:
        input_value = " ".join(attempt.candidate.input_data.split())
        marker = "  <-- successful hack" if attempt.is_successful_hack else ""
        print(
            f"  [{attempt.candidate.strategy}] input={input_value!r} "
            f"verdict={attempt.verdict.value}{marker}"
        )

    successful = report.phase_two.successful_hacks
    print(
        f"\nsummary: {len(successful)} successful hack(s) from "
        f"{len(report.phase_two.attempts)} candidate(s)"
    )


if __name__ == "__main__":
    main()
