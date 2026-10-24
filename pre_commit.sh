#!/bin/bash
set -e

echo "Running checks..."
ruff check veraxi_ymmp/ tests/ scripts/
mypy veraxi_ymmp
python scripts/check_no_local_paths.py --all

echo "Running test_architectural_fitness.py..."
pytest tests/test_architectural_fitness.py

echo "All passed!"
