"""A small, executable reproduction of CodeHacker's two-phase workflow."""

from .core import (
    CalibrationResult,
    CheckerProbe,
    HackCandidate,
    Judge,
    PhaseTwoReport,
    ValidationProbe,
    Verdict,
    calibrate_checker,
    calibrate_validator,
    run_phase_two,
)
from .llm import LLMConfig, OpenAICompatibleLLM, TextLLM

__all__ = [
    "CalibrationResult",
    "CheckerProbe",
    "HackCandidate",
    "Judge",
    "LLMConfig",
    "OpenAICompatibleLLM",
    "PhaseTwoReport",
    "ValidationProbe",
    "Verdict",
    "TextLLM",
    "calibrate_checker",
    "calibrate_validator",
    "run_phase_two",
]
