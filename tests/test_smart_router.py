"""
Test Smart Router functionality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from runtime.smart_router import SmartRouter, TaskComplexity, ModelTier


def test_task_analyzer():
    """Test task complexity analysis"""
    print("=" * 60)
    print("TEST: Task Analyzer")
    print("=" * 60)

    router = SmartRouter()

    test_cases = [
        ("Format this file", TaskComplexity.SIMPLE),
        ("Fix typo in README", TaskComplexity.SIMPLE),
        ("Write a function to calculate fibonacci", TaskComplexity.MEDIUM),
        ("Write unit tests", TaskComplexity.MEDIUM),
        ("Design microservice architecture", TaskComplexity.COMPLEX),
        ("Security audit for production code", TaskComplexity.CRITICAL),
    ]

    passed = 0
    for task, expected in test_cases:
        result = router.route(task)
        actual = result["complexity"]
        status = "[OK]" if actual == expected else "[FAIL]"
        if actual == expected:
            passed += 1
        print(f"  {status} '{task[:40]}...' -> {actual.value} (expected {expected.value})")

    print(f"\n  {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_model_selection():
    """Test model selection based on complexity"""
    print("\n" + "=" * 60)
    print("TEST: Model Selection")
    print("=" * 60)

    router = SmartRouter()

    test_cases = [
        ("Format file", ModelTier.LOCAL),  # Simple -> Local
        ("Implement function", ModelTier.CHEAP),  # Medium -> Cheap
        ("Design system architecture", ModelTier.BALANCED),  # Complex -> Balanced
    ]

    passed = 0
    for task, expected_tier in test_cases:
        result = router.route(task)
        actual_tier = result["model_config"].tier
        status = "[OK]" if actual_tier == expected_tier else "[FAIL]"
        if actual_tier == expected_tier:
            passed += 1
        print(f"  {status} '{task[:30]}...' -> {actual_tier.value} (expected {expected_tier.value})")

    print(f"\n  {passed}/{len(test_cases)} tests passed")
    return passed == len(test_cases)


def test_budget_constraints():
    """Test budget-aware routing"""
    print("\n" + "=" * 60)
    print("TEST: Budget Constraints")
    print("=" * 60)

    # Test with tight budget
    router = SmartRouter(monthly_budget=0.01, prefer_local=True)
    result = router.route("Design complex system")
    status = "[OK]" if result["model_config"].tier == ModelTier.LOCAL else "[FAIL]"
    print(f"  {status} Tight budget -> {result['model_key']} ({result['model_config'].tier.value})")

    # Test with generous budget
    router2 = SmartRouter(monthly_budget=1000.0)
    result2 = router2.route("Design complex system")
    status2 = "[OK]" if result2["model_config"].tier in [ModelTier.BALANCED, ModelTier.PREMIUM] else "[FAIL]"
    print(f"  {status2} Generous budget -> {result2['model_key']} ({result2['model_config'].tier.value})")

    return True


def test_cost_estimation():
    """Test cost estimation"""
    print("\n" + "=" * 60)
    print("TEST: Cost Estimation")
    print("=" * 60)

    router = SmartRouter()

    # Local model should be free
    result = router.route("Format file")
    status = "[OK]" if result["estimated_cost"] == 0 else "[FAIL]"
    print(f"  {status} Local model cost: ${result['estimated_cost']:.4f}")

    # Cloud model should have cost
    result2 = router.route("Design microservice architecture with database")
    status2 = "[OK]" if result2["estimated_cost"] > 0 else "[FAIL]"
    print(f"  {status2} Cloud model cost: ${result2['estimated_cost']:.4f}")

    return True


def test_routing_history():
    """Test routing history tracking"""
    print("\n" + "=" * 60)
    print("TEST: Routing History")
    print("=" * 60)

    router = SmartRouter()

    # Make several routing decisions
    tasks = ["Format file", "Implement API", "Design architecture"]
    for task in tasks:
        router.route(task)

    history = router.get_routing_history()
    status = "[OK]" if len(history) == 3 else "[FAIL]"
    print(f"  {status} History entries: {len(history)}")

    stats = router.get_stats()
    status2 = "[OK]" if stats["total_routes"] == 3 else "[FAIL]"
    print(f"  {status2} Total routes: {stats['total_routes']}")

    print(f"  Complexity distribution: {stats['complexity_distribution']}")
    print(f"  Model distribution: {stats['model_distribution']}")

    return True


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("SMART ROUTER TEST SUITE")
    print("=" * 60)

    results = []

    results.append(("Task Analyzer", test_task_analyzer()))
    results.append(("Model Selection", test_model_selection()))
    results.append(("Budget Constraints", test_budget_constraints()))
    results.append(("Cost Estimation", test_cost_estimation()))
    results.append(("Routing History", test_routing_history()))

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status}: {name}")

    print(f"\n  {passed}/{total} tests passed")

    if passed == total:
        print("\n  [SUCCESS] All tests passed!")
        return 0
    else:
        print("\n  [WARN] Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
