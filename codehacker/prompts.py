"""Engineering adaptations of the prompt set in CodeHacker Appendix L.

The paper's six prompt roles are preserved, including their inputs, attack
objectives, output schemas, and generator requirements. Wording is adapted for
direct reuse in code rather than copied verbatim from the paper.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .llm import TextLLM


_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


@dataclass(frozen=True)
class PromptTemplate:
    """A strict named-placeholder prompt template."""

    name: str
    template: str
    source: str = "CodeHacker Appendix L, pp. 2378-2382"

    @property
    def placeholders(self) -> frozenset[str]:
        return frozenset(_PLACEHOLDER.findall(self.template))

    def render(self, **values: object) -> str:
        missing = self.placeholders - values.keys()
        extra = values.keys() - self.placeholders
        if missing:
            raise ValueError(f"Missing placeholders for {self.name}: {sorted(missing)}")
        if extra:
            raise ValueError(f"Unknown placeholders for {self.name}: {sorted(extra)}")
        return _PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), self.template)


CHECKER_HACK_PROMPT = PromptTemplate(
    name="checker_hack",
    template="""You are auditing a competitive-programming output checker.
Find independent logical defects that can make it return an incorrect verdict.

# Inputs
Problem description:
{{problem_description}}

Checker code:
{{checker_code}}

# Procedure
1. Determine whether the problem has one answer or permits multiple valid
   answers, orderings, or constructions.
2. Map every output requirement to the exact checker branch that enforces it.
3. Probe both directions:
   - false_positive: an invalid or semantically wrong output that is accepted;
   - false_negative: a valid alternative output that is rejected.
4. Re-check input/output syntax and explain which checker condition is fooled.

# Required JSON
{
  "test_cases": [
    {
      "strategy": "short description of the checker weakness",
      "bug_type": "false_positive or false_negative",
      "test_input": "complete problem input",
      "fake_output": "candidate output presented to the checker"
    }
  ]
}
Return JSON only. Include separate cases for separate logical defects.
""",
)


VALIDATOR_HACK_PROMPT = PromptTemplate(
    name="validator_hack",
    template="""You are auditing a competitive-programming input validator.
Find independent mismatches between the written input domain and the code.

# Inputs
Problem constraints and input format:
{{problem_description}}

Validator code:
{{validator_code}}

# Procedure
1. Enumerate every range, count, formatting, uniqueness, and structural
   constraint. Include properties such as connectivity or acyclicity.
2. Map each written constraint to its parser check or assertion.
3. Probe both directions:
   - false_positive: an illegal input the validator is likely to accept;
   - false_negative: a legal boundary or structured input it may reject.
4. Make every proposed input complete and label its ground-truth validity.

# Required JSON
{
  "test_cases": [
    {
      "strategy": "constraint/code mismatch being exercised",
      "bug_type": "false_positive or false_negative",
      "test_input": "complete candidate input",
      "expected_validity": "valid or invalid"
    }
  ]
}
Return JSON only.
""",
)


CODE_ANALYST_TOOL_PROMPT = PromptTemplate(
    name="code_analyst_tool",
    template="""You are a competitive-programming Code Analyst. Find evidence
for WA, TLE, RE, or MLE defects in the target C++ submission. Static guesses are
not enough: use the execution tools to test hypotheses.

# Multi-turn protocol
For every turn, emit a concise Thought followed by exactly one tool call. The
environment will return that tool's observation before the next turn.

# Tools
- run_python(script_code): calculate exact bounds, construct cases, enumerate
  small instances, or verify mathematical properties.
- run_cpp(input_content): compile/run the target on one complete input and
  return stdout, stderr, and exit code.
- finish(code_analysis_report): submit the evidence-backed final analysis.

# Investigation policy
1. Read the specification and code before choosing a failure hypothesis.
2. Use Python for arithmetic, overflow, combinatorics, or systematic search.
3. Use small C++ probes to confirm logic/RE hypotheses, then derive a valid
   large generator when scale is required for TLE/MLE.
4. Distinguish observed behavior from inference. Do not claim a bug without a
   reproducible trigger or a precise bound calculation.
5. In the final report state the verdict type, vulnerable assumption, trigger
   conditions, and supporting tool observations.

# Task
Problem:
{{problem_description}}

Target code:
{{target_code}}
""",
)


STRESS_GENERATOR_PROMPT = PromptTemplate(
    name="stress_generator",
    template="""Write a complete randomized C++ generator for stress-testing
the problem below. It must print exactly one valid test case.

# Problem
{{problem_description}}

# Generator requirements
1. Seed a robust PRNG such as mt19937 from a time-based source.
2. Preserve every input constraint, including non-local graph/tree properties.
3. Bias samples toward maximum sizes and worst-case shapes, while retaining a
   smaller chance of boundary-sized cases.
4. Avoid undefined behavior in the generator, including empty ranges and
   modulo-by-zero.
5. Put range sampling in a helper when that makes correctness easier to audit.

# Output contract
Return only one C++ code block. The program must include bits/stdc++.h, contain
main(), and write one format-compliant input to stdout.
""",
)


BUG_DISCOVERY_GENERATOR_PROMPT = PromptTemplate(
    name="bug_discovery_generator",
    template="""Analyze the incorrect competitive-programming submission and
write a C++ program that generates an input exposing one concrete defect.

# Problem
{{problem_description}}

# Incorrect code
{{incorrect_code}}

# Optional collision material
{{hash_collision_data}}

# Attack requirements
1. The generated input must satisfy every original constraint.
2. It must deterministically trigger WA, TLE, MLE, or RE in the target.
3. A correct implementation must handle the same input.
4. First identify the vulnerable assumption, then choose values and structure
   that isolate it. Prefer clear, reproducible failures over random luck.
5. Use loops/calculation inside the generator when raw output would be too long.

# Output contract
Return only a complete C++ program. Include bits/stdc++.h, define main(), and
print exactly one complete test case in the required format.
""",
)


ANTI_HASH_GENERATOR_PROMPT = PromptTemplate(
    name="anti_hash_generator",
    template="""Audit the target for polynomial rolling-hash collision risk.

# Workflow
1. Locate every hash update expression and decide whether it is linear.
2. Extract, in order, every base and modulus. Treat unsigned 64-bit wraparound
   without an explicit modulus as arithmetic modulo 2^64.
3. Recover the valid alphabet and exact character-to-integer mapping.
4. Note random initialization or multiple independent hashes explicitly; never
   invent constants that cannot be recovered from the code.

# Inputs
Problem:
{{problem_description}}

Target code:
{{target_code}}

# Required JSON
{
  "vulnerability_type": "Hash Collision",
  "hash_parameters": {
    "base": ["integer or recovered expression"],
    "modulus": ["matching integer or expression"],
    "character_set": "valid alphabet",
    "mapping": "character-to-value rule"
  }
}
Return JSON only. The base and modulus arrays must correspond positionally.
""",
)


# The paper's Code Analyst assumes a sandboxed tool loop. The lightweight demo
# intentionally does not execute arbitrary model-authored Python/C++, so it uses
# this constrained final-report adapter while exposing the full tool prompt above.
CODE_ANALYST_JSON_PROMPT = PromptTemplate(
    name="code_analyst_json_demo",
    source="Safe single-turn adapter derived from CodeHacker Appendix L",
    template="""Act as the CodeHacker Code Analyst for one C++ submission.
Identify a specific WA, TLE, RE, or MLE hypothesis. Derive legal trigger values
from the specification and code; do not invent tool observations.

# Problem
{{problem_description}}

# Target code
{{target_code}}

# Required JSON
{
  "bug_type": "WA, RE, TLE, MLE, or unknown",
  "hypothesis": "brief explanation of the vulnerable assumption",
  "trigger_values": ["integer values valid for this demo's input domain"],
  "uses_hashing": false
}
Return one JSON object and no Markdown.
""",
)


APPENDIX_L_PROMPTS = {
    prompt.name: prompt
    for prompt in (
        CHECKER_HACK_PROMPT,
        VALIDATOR_HACK_PROMPT,
        CODE_ANALYST_TOOL_PROMPT,
        STRESS_GENERATOR_PROMPT,
        BUG_DISCOVERY_GENERATOR_PROMPT,
        ANTI_HASH_GENERATOR_PROMPT,
    )
}


class AppendixLPromptRunner:
    """Render and execute any Appendix L role with the configured LLM."""

    def __init__(self, llm: TextLLM) -> None:
        self.llm = llm

    def run(
        self,
        prompt_name: str,
        *,
        temperature: float = 0.7,
        **values: object,
    ) -> str:
        try:
            prompt = APPENDIX_L_PROMPTS[prompt_name]
        except KeyError as exc:
            available = ", ".join(sorted(APPENDIX_L_PROMPTS))
            raise ValueError(
                f"Unknown Appendix L prompt {prompt_name!r}; choose from: {available}"
            ) from exc
        rendered = prompt.render(**values)
        return self.llm.complete(
            f"Execute the CodeHacker Appendix L role: {prompt.name}. "
            "Follow its output contract exactly.",
            rendered,
            temperature=temperature,
        )
