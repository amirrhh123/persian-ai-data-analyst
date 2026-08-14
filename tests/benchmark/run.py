from tests.benchmark.dataset import create_education_dataset
from tests.benchmark.evaluator import BenchmarkEvaluator, BenchmarkReport


def run_benchmark(tenant_id: str = "education_ministry") -> BenchmarkReport:
    print("Creating benchmark dataset...")
    dataset = create_education_dataset()
    print(f"Dataset created with {dataset.get_count()} cases")
    
    print(f"\nEvaluating with tenant: {tenant_id}")
    evaluator = BenchmarkEvaluator(tenant_id)
    
    results = evaluator.evaluate_dataset(dataset)
    
    report = BenchmarkReport(results)
    report.print_report()
    
    return report


if __name__ == "__main__":
    run_benchmark()
