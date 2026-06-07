"""Test 6: Project analyzer"""
import sys
sys.path.insert(0, r'D:\codex-local')

from tools.project_analyzer import ProjectAnalyzer
import tempfile
import os

def test_project_analyzer():
    # Create a small test project
    tmp = tempfile.mkdtemp()

    # Write some Python files
    with open(os.path.join(tmp, "main.py"), "w") as f:
        f.write("""def greet(name):
    return f"Hello, {name}"

class Calculator:
    def add(self, a, b):
        return a + b
""")

    with open(os.path.join(tmp, "utils.py"), "w") as f:
        f.write("""def helper():
    pass
""")

    analyzer = ProjectAnalyzer(tmp)
    graph = analyzer.analyze(max_files=50)

    assert len(graph.modules) >= 2, f"modules={list(graph.modules.keys())}"
    assert any("Calculator" in c for c in graph.classes), f"classes={list(graph.classes.keys())}"
    assert "greet" in graph.functions, f"functions={list(graph.functions.keys())}"

    # Cleanup
    import shutil
    shutil.rmtree(tmp)
    print("PASS: project analyzer")

if __name__ == "__main__":
    test_project_analyzer()