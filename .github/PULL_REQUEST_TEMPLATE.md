## Summary

<!-- What does this PR do? One paragraph is fine. -->

## Changes

<!-- Bullet list of the main changes made. -->

- 
- 

## Type of change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor / code quality
- [ ] Tests
- [ ] Documentation
- [ ] CI/CD / infrastructure

## Testing

- [ ] All existing tests pass (`pytest tests/ -q`)
- [ ] New tests added for new code paths
- [ ] Coverage stays at 100% (`--cov-fail-under=90` enforced)
- [ ] Linting passes (`black --check . && flake8 .`)
- [ ] Type checking run (`mypy shared/ orchestrator/ agents/ integrations/ --ignore-missing-imports`)

On Windows, run everything at once:

```powershell
.\scripts\test_local.ps1
```

## Related issues

<!-- Closes # -->
