FIX: 01 - Detect GitHub Actions run steps

## Problem
Factory detection misses inline GitHub Actions steps written as `- run: command`, so initialization can omit an existing CI test command. Existing mapping-style `run:` and Bitbucket `script:` hints must remain available without treating block markers or step metadata as commands.

## Change
CI detection now recognizes YAML block headers with comments and indentation indicators, including indicators combined with chomp modifiers. Committed as `aa1e208`.

## Verified
- `python3 -m unittest discover -s tests` (.): exit 0, 107 passed, 0 failed
- review-2: PASS
