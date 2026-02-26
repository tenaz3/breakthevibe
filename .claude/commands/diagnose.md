---
description: Debug-first approach — add diagnostic logging before attempting fixes
argument-hint: [description of the bug or failing test]
---

# Diagnostic Debugging

Follow a data-driven debugging approach. Do NOT attempt fixes before understanding root cause.

## Steps

1. **Reproduce**: Run the failing test or trigger the bug. Capture the exact error output.

2. **Read the code path**: Trace the execution path from entry point to the error. Read all relevant files.

3. **Add diagnostics**: Add `structlog.get_logger(__name__).debug()` calls at key points in the code path to confirm:
   - Which branch/condition is being taken
   - What values variables actually hold
   - Whether the function is even being called

4. **Run again**: Execute with diagnostics in place. Analyze the output.

5. **Form hypothesis**: Based on diagnostic data, identify the root cause. Explain it clearly before proposing a fix.

6. **Fix**: Apply the minimal fix for the identified root cause.

7. **Verify**: Run the full test suite (`uv run pytest tests/ -x -q`) to confirm the fix works and doesn't break anything else.

8. **Clean up**: Remove diagnostic logging that was added temporarily.

## Rules
- NEVER attempt more than one fix without gathering diagnostic data first
- If the first fix doesn't work, add MORE logging, don't try a different approach blindly
- Always run the full test suite after fixing, not just the specific failing test
