# Validation

Run with the paired SDK source checkout selected explicitly:

```bash
PYTHONPATH=/path/to/aoa-sdk/src python -m pytest -q mechanics/governed-execution/parts/programmatic-tool-execution/tests
PYTHONPATH=/path/to/aoa-sdk/src python -m py_compile mechanics/governed-execution/parts/programmatic-tool-execution/programmatic_tool_execution.py
python scripts/validate_stack.py
python scripts/validate_nested_agents.py
python scripts/validate_decision_records.py
```

The focused suite proves disabled-by-default dispatch, explicit admission,
independent Codex and local adapter seams, observation-sink ordering,
distinct adapter and sink failures, normalized provider errors, and
fail-closed invalid observations with post-execution or indeterminate status,
including unknown completion after invocation exceptions.
It does not prove live provider execution, runtime deployment, paired baseline
admission, eval quality, promotion, economy comparison, or owner acceptance.
