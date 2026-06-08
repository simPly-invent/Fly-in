PYTHON := python3
PIP    := $(PYTHON) -m pip
MAP    := maps/easy/01_linear_path.txt

.PHONY: install run debug clean lint lint-strict help

help:
	@echo "Fly-in -- available targets:"
	@echo "  make install        Install project dependencies"
	@echo "  make run MAP=...    Run the simulation on a map file (terminal)"
	@echo "  make debug MAP=...  Run the simulation under pdb"
	@echo "  make clean          Remove caches and bytecode"
	@echo "  make lint           flake8 + mypy with mandatory flags"
	@echo "  make lint-strict    flake8 + mypy --strict (optional)"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) main.py $(MAP)

debug:
	$(PYTHON) -m pdb main.py $(MAP)

clean:
	rm -rf __pycache__ */__pycache__ */*/__pycache__
	rm -rf .mypy_cache .pytest_cache .ruff_cache
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true

lint:
	flake8 .
	$(PYTHON) -m mypy . --warn-return-any --warn-unused-ignores --ignore-missing-imports \
	       --disallow-untyped-defs --check-untyped-defs

lint-strict:
	flake8 .
	$(PYTHON) -m mypy . --strict
