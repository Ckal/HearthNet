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

print(f"Total test files: {len(test_files)}\n")

# Run pytest on all collected files
result = subprocess.run(
    ['python', '-m', 'pytest'] + [str(f) for f in test_files] + ['--collect-only', '-q'],
    capture_output=True,
    text=True
)

# Print last lines with count
lines = result.stdout.split('\n')
for line in lines[-10:]:
    if line.strip():
        print(line)
