.PHONY: format lint lint-fix
format:
black .
ruff check --select I --fix .
lint:
ruff check .
black --check .
lint-fix: format
