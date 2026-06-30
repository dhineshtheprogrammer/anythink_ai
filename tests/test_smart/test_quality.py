"""Tests for smart/quality.py."""

from anythink.smart.quality import QualityGate


def test_empty_response_scores_zero():
    gate = QualityGate(threshold=50)
    result = gate.evaluate("", "general", "What is 2+2?")
    assert result.score == 0
    assert result.passed is False


def test_full_quality_response_passes():
    response = (
        "The Pythagorean theorem states that a² + b² = c². "
        "This means that in a right triangle, the square of the hypotenuse equals "
        "the sum of squares of the other two sides. For example, a 3-4-5 triangle satisfies "
        "this: 9 + 16 = 25. You can use it to calculate any unknown side when the other two are known."
    )
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "math", "Explain the Pythagorean theorem")
    assert result.passed is True
    assert result.score >= 50


def test_refusal_penalises_nonrefusal_score():
    response = "I'm sorry, I cannot answer this question as an AI assistant."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "general", "Tell me a joke")
    assert result.nonrefusal_score < 30


def test_refusal_with_content_gives_partial_credit():
    # Long response that starts with a refusal phrase but continues with content
    response = "As an AI, I should note this is a complex topic. " + (
        "However, the main answer is X. " * 10
    )
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "general", "Explain quantum entanglement")
    # Should get partial nonrefusal score (10), not 0
    assert result.nonrefusal_score == 10


def test_code_category_rewards_code_blocks():
    response = "Here is the solution:\n```python\ndef add(a, b):\n    return a + b\n```"
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "code", "Write an add function")
    assert result.coherence_score == 30


def test_code_category_with_formula_partial_credit():
    # Numeric expression with no spaces — should match the formula regex
    response = "The answer is: 3^2+4^2=5^2 which satisfies the equation."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "math", "Simplify the expression")
    assert result.coherence_score == 22


def test_prose_only_code_answer_low_coherence():
    response = "You would write a function that takes two parameters and returns their sum."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "code", "Write an add function")
    assert result.coherence_score == 10


def test_writing_category_multi_sentence_coherence():
    response = "This is the first sentence. Here is the second. And a third one follows."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "writing", "Write a short paragraph")
    assert result.coherence_score == 30


def test_truncated_response_low_completion():
    response = "The main idea is that quantum computers work by using..."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "research", "Explain quantum computing")
    assert result.completion_score == 5


def test_natural_ending_full_completion():
    response = "The capital of France is Paris."
    gate = QualityGate(threshold=50)
    result = gate.evaluate(response, "research", "What is the capital of France?")
    assert result.completion_score == 20


def test_checks_detail_keys():
    gate = QualityGate(threshold=50)
    result = gate.evaluate("Short answer.", "general", "Q?")
    assert "length" in result.checks_detail
    assert "nonrefusal" in result.checks_detail
    assert "coherence" in result.checks_detail
    assert "completion" in result.checks_detail


def test_threshold_clamped():
    gate = QualityGate(threshold=200)
    assert gate.threshold == 100
    gate2 = QualityGate(threshold=-10)
    assert gate2.threshold == 0


def test_set_threshold():
    gate = QualityGate(threshold=50)
    gate.set_threshold(70)
    assert gate.threshold == 70


def test_score_components_sum_to_total():
    gate = QualityGate(threshold=50)
    response = "The answer is 42. This is because of the fundamental nature of the universe."
    result = gate.evaluate(response, "general", "What is the ultimate answer?")
    total = (
        result.length_score
        + result.nonrefusal_score
        + result.coherence_score
        + result.completion_score
    )
    assert total == result.score
