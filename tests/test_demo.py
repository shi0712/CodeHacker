from codehacker.core import HackCandidate, Judge, Verdict
from codehacker.demo import (
    CaptainFlintCheckerAgent,
    CaptainFlintValidatorAgent,
    LLMCaptainFlintAnalyst,
    PROBLEM_SPEC,
    captain_flint_reference,
    captain_flint_vulnerable,
    run_demo,
)
from codehacker.core import calibrate_checker, calibrate_validator
from codehacker.llm import LLMConfig, OpenAICompatibleLLM


def test_phase_one_repairs_false_positives_and_false_negatives() -> None:
    validator_result = calibrate_validator(
        PROBLEM_SPEC, CaptainFlintValidatorAgent(), stable_rounds=2
    )
    checker_result = calibrate_checker(
        PROBLEM_SPEC, CaptainFlintCheckerAgent(), stable_rounds=2
    )

    assert validator_result.refinements == 1
    assert checker_result.refinements == 1
    assert validator_result.tool("1\n1\n")
    assert not validator_result.tool("1\n1000000001\n")
    assert not checker_result.tool("1\n36\n", "YES\n6 10 14 6\n")
    assert checker_result.tool("1\n36\n", "YES\n5 15 10 6\n")


def test_phase_two_finds_the_three_collision_hacks() -> None:
    report = run_demo()

    hacked_values = {
        int(result.candidate.input_data.split()[1])
        for result in report.phase_two.successful_hacks
    }
    assert hacked_values == {36, 40, 44}
    assert all(
        result.verdict is Verdict.WRONG_ANSWER
        for result in report.phase_two.successful_hacks
    )


def test_invalid_generated_input_is_not_counted_as_a_hack() -> None:
    validator = calibrate_validator(
        PROBLEM_SPEC, CaptainFlintValidatorAgent(), stable_rounds=1
    ).tool
    checker = calibrate_checker(
        PROBLEM_SPEC, CaptainFlintCheckerAgent(), stable_rounds=1
    ).tool
    judge = Judge(
        validator=validator,
        checker=checker,
        reference_solution=captain_flint_reference,
        target_submission=captain_flint_vulnerable,
    )

    result = judge.evaluate(
        HackCandidate(
            strategy="test",
            input_data="1\n1000000001\n",
            rationale="outside the legal range",
        )
    )

    assert result.verdict is Verdict.INVALID_INPUT
    assert not result.is_successful_hack


def test_llm_config_reads_key_base_url_and_model(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "secret-test-key")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:8000/v1/")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")

    config = LLMConfig.from_env(load_dotenv_file=False)

    assert config.api_key == "secret-test-key"
    assert config.base_url == "http://localhost:8000/v1"
    assert config.model == "test-model"
    assert config.timeout_seconds == 30
    assert "secret-test-key" not in repr(config)


def test_real_llm_adapter_can_drive_the_analyst_without_network() -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            self.kwargs = kwargs
            message = type(
                "Message",
                (),
                {
                    "content": (
                        '{"bug_type":"WA","hypothesis":"collision",'
                        '"trigger_values":[36,40,44],"uses_hashing":false}'
                    )
                },
            )()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice]})()

    completions = FakeCompletions()
    fake_client = type(
        "FakeClient",
        (),
        {"chat": type("Chat", (), {"completions": completions})()},
    )()
    config = LLMConfig(
        api_key="not-used",
        base_url="http://localhost:8000/v1",
        model="test-model",
    )
    llm = OpenAICompatibleLLM(config, client=fake_client)

    report = run_demo(analyst=LLMCaptainFlintAnalyst(llm))

    assert len(report.phase_two.successful_hacks) == 3
    assert completions.kwargs["model"] == "test-model"
