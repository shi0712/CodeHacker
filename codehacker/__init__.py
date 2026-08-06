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
from .prompts import APPENDIX_L_PROMPTS, AppendixLPromptRunner, PromptTemplate

__all__ = [
    "CalibrationResult",
    "APPENDIX_L_PROMPTS",
    "AppendixLPromptRunner",
    "CheckerProbe",
    "HackCandidate",
    "Judge",
    "LLMConfig",
    "OpenAICompatibleLLM",
    "PromptTemplate",
    "PhaseTwoReport",
    "ValidationProbe",
    "Verdict",
    "TextLLM",
    "calibrate_checker",
    "calibrate_validator",
    "run_phase_two",
]
