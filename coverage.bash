#!/bin/bash
set -e

# find the coverage.py script to use
for cov in "python3-coverage" "coverage3" "coverage"; do
    if hash "${cov}" 2>/dev/null; then
	COVERAGE="${cov}"
	break
    fi
done

"${COVERAGE}" run test.py
"${COVERAGE}" report -m *.py
"${COVERAGE}" html *.py
