PYTHON ?= python3
VENV = .venv
BIN = $(VENV)/bin

.PHONY: install test demo serve clean

install:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

test:
	$(BIN)/python -m pytest -q

demo:
	$(BIN)/python -m trevad generate
	$(BIN)/python -m trevad decide

serve:
	$(BIN)/python -m trevad serve

clean:
	rm -rf out .pytest_cache
