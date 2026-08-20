from backend.llm.context_budget import ContextBudget
from backend.llm.models import TokenUsage
from backend.llm.token_counter import ApproximateTokenCounter


def test_approximate_counter_counts_text():
    assert ApproximateTokenCounter().count("سلام دنیا") == 2


def test_context_budget_trims_to_available_tokens():
    counter = ApproximateTokenCounter()
    budget = ContextBudget(maximum_tokens=10, reserved_output_tokens=3)
    result = budget.fit("یک دو سه چهار پنج شش هفت هشت نه ده", counter)
    assert result.truncated
    assert result.final_tokens <= budget.available_input_tokens


def test_token_usage_total():
    usage = TokenUsage(10, 4, 14)
    assert usage.total_tokens == usage.input_tokens + usage.output_tokens
