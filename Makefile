.PHONY: test validate clean

test:
	python -m pytest tests/

validate:
	@if [ -z "$(SKILL)" ]; then \
		echo "Usage: make validate SKILL=path/to/skill"; \
		exit 1; \
	fi
	python scripts/validate_all.py "$(SKILL)"

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
