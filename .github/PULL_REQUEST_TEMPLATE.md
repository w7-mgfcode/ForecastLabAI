## Summary

<!-- Brief description of changes (1-3 sentences) -->

## Type of Change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would cause existing functionality to change)
- [ ] Refactoring (no functional changes)
- [ ] Documentation update
- [ ] CI/CD changes

## Checklist

### Code Quality
- [ ] My code follows the project's coding standards (see CLAUDE.md)
- [ ] I have run `uv run ruff check . --fix && uv run ruff format .`
- [ ] I have run `uv run mypy app/ && uv run pyright app/`
- [ ] All type annotations are complete (no `Any` without justification)

### Testing
- [ ] I have added tests that prove my fix/feature works
- [ ] All existing tests pass (`uv run pytest -v`)
- [ ] New tests follow existing patterns in `app/*/tests/`

### Database
- [ ] No database changes required
- [ ] Migration added and tested (`uv run alembic upgrade head` on fresh DB)
- [ ] Migration is backward compatible

### Documentation
- [ ] No documentation changes needed
- [ ] I have updated relevant documentation
- [ ] Docstrings follow Google style

### Security
- [ ] No hardcoded secrets, credentials, or API keys
- [ ] Input validation is in place for user-provided data
- [ ] No SQL injection vulnerabilities (using SQLAlchemy ORM)

## Testing Instructions

<!-- How can reviewers test these changes? -->

## Related Issues

<!-- Link to related issues: Fixes #123, Relates to #456 -->
