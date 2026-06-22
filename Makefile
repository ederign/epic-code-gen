.PHONY: install test test-unit test-integration clean

install:
	uv sync

test: test-unit test-integration

test-unit:
	uv run pytest tests/ -m "not integration" -v

test-integration:
	uv run pytest tests/ -m "integration" -v

clean:
	rm -rf tmp/ .target-repo/ .context/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
