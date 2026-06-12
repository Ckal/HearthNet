#!/bin/bash
# Pre-commit hook: run tests before allowing commit
# Usage: cp pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit

echo "🧪 Running tests before commit..."
python -m pytest tests/ -q --tb=short

if [ $? -ne 0 ]; then
    echo "❌ Tests failed! Commit aborted."
    echo "Fix failures and try again: python -m pytest tests/ -v"
    exit 1
fi

echo "✅ All tests passed! Proceeding with commit..."
exit 0
