# Regression benchmark

This benchmark protects real Persian UI/API scenarios that previously failed.

Run the fast pytest gate:

```powershell
python -m pytest tests/test_regression_benchmark.py -q
```

Run and save timestamped JSON results:

```powershell
python run_regression.py
```

Results are written to:

- `tests/results/latest_regression.json`
- `tests/results/regression_YYYYMMDD_HHMMSS.json`

Useful SQL-C16 commands:

```powershell
# Run only one case while debugging
python run_regression.py --case-id reg_student_count_tehran_001 --no-save

# Run only critical cases inferred from case ids/metadata
python run_regression.py --priority critical

# Run one category, for example student SQL paths
python run_regression.py --category student

# CI/product gate: fail the command if pass rate is below the threshold
python run_regression.py --min-pass-rate 95

# Machine-readable output for dashboards or scripts
python run_regression.py --json
```

Add new cases to `tests/benchmark/regression_cases.json` whenever a UI bug is found.
Each case can assert:

- `success`, `group`, `report`, `valid`
- `intent` fields
- SQL snippets that must exist or must not exist
- `row_count`
- expected values in the first result row
- trace steps and statuses, for example `result_shape_validation`
- expected structured error codes, for example `result.shape_mismatch`
