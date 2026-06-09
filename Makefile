PYTHON := python3
PIP    := $(PYTHON) -m pip

.PHONY: install run debug clean lint lint-strict help

help:
	@echo "******************************************************************"
	@echo "*Fly-in -- available targets:								  *"
	@echo "*  make install        Install project dependencies           *"
	@echo "*  make run            Launch the interactive map menu          *"
	@echo "*  make debug          Launch the menu under pdb	      	  *"
	@echo "*  make clean          Remove caches and bytecode	          *"
	@echo "*  make lint           flake8 + mypy with mandatory flags	  *"
	@echo "*  make lint-strict    flake8 + mypy --strict (optional)          *"
	@echo "******************************************************************"

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

run:
	$(PYTHON) main.py

debug:
	$(PYTHON) -m pdb main.py

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
