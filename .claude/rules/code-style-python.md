---
paths:
  - "**/*.py"
---

# Python Rules

- Follow PEP 8. `ruff` enforces it. The configuration is in [controller/pyproject.toml](../../controller/pyproject.toml).
- After you change a `.py` file, run `ruff format` and `ruff check --fix` on it. Run them before you consider the change done.
- Indent with four spaces. Keep lines to 88 characters or fewer (the `ruff` default).
- Casing:

  | Type                | Case       |
  | ------------------- | ---------- |
  | class               | PascalCase |
  | function / variable | snake_case |
  | constant            | SHOUT_CASE |
  | module / file       | snake_case |

- Add type hints to every public function and method. Use built-in generics, for example `list[str]`, not `List[str]`.
- Use `pathlib.Path` for file paths. Do not join paths with string operations.
- Do not catch a bare `Exception` unless you log it and re-raise it, or unless the code is a top-level loop that must not stop.
- Use the `logging` module. Do not use `print` in library code.
- Keep hardware access behind the input and player abstractions. Code outside those modules must run on a laptop with no GPIO and no DRM device.
- Every new behaviour gets a `pytest` test. Tests must not need a Pi, a display or network access.
- Write real documentation in `docs/<feature>/`. Keep code comments short. Use a comment to explain why, not what.
