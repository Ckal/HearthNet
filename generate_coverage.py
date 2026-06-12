from pathlib import Path
import subprocess

test_files = (
    sorted(Path('tests').glob('test_m*.py')) +
    sorted(Path('tests').glob('test_x*.py')) +
    sorted(Path('tests').glob('test_c*.py')) +
    sorted(Path('tests').glob('test_g*.py')) +
    sorted(Path('tests').glob('test_h*.py')) +
    sorted(Path('tests').glob('test_o*.py')) +
    sorted(Path('tests').glob('test_i*.py')) +
    sorted(Path('tests').glob('test_p*.py')) +
    sorted(Path('tests').glob('test_r*.py'))
)

print(f"Running coverage analysis on {len(test_files)} test files with {sum(1 for f in test_files)} tests...\n")

# Run pytest with coverage
result = subprocess.run(
    ['python', '-m', 'pytest'] + [str(f) for f in test_files] + 
    ['--cov=hearthnet', '--cov-report=term-missing', '--cov-report=html', '-q'],
    capture_output=True,
    text=True,
    timeout=300
)

# Print output
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Show summary
print("\nCoverage report generated in htmlcov/index.html")
