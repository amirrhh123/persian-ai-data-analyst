from backend.evaluation.runner import run_evaluation


def test_evaluation_layers():
    result = run_evaluation(expected_retrieval=["schema"], ranked_retrieval=["schema"],
                            generated_sql="SELECT 1", expected_sql="select 1;",
                            answer="تعداد 10", reference_answer="تعداد 10", rejected=True)
    assert result.passed
    assert result.metrics["retrieval_mrr"] == 1.0
    assert result.metrics["sql_exact_match"] == 1.0
