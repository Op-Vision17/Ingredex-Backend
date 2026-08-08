# Ingredex Backend Makefile

.PHONY: help dev migrate install check test run

help:
	@echo Ingredex Backend Commands:
	@echo   make dev       - Start FastAPI development server (poetry run dev)
	@echo   make run       - Run uvicorn server via run.py
	@echo   make migrate   - Run Alembic database migrations
	@echo   make install   - Install Python dependencies via Poetry
	@echo   make check     - Check Python code syntax
	@echo   make test      - Run Pytest test suite

dev:
	poetry run dev

run:
	python run.py

migrate:
	poetry run migrate

install:
	poetry install

check:
	python -m py_compile app/main.py app/routers/analyze.py app/services/web_search_service.py app/ai/crew.py app/ai/preprocessor.py

test:
	poetry run pytest
