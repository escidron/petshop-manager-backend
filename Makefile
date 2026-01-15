.PHONY: run install shell test lint format migrate revision upgrade downgrade

APP=app.main:app

install:
	poetry install

run:
	poetry run uvicorn $(APP) --reload

shell:
	poetry shell

test:
	poetry run pytest

lint:
	poetry run ruff check .

format:
	poetry run ruff format .

revision:
	poetry run alembic revision --autogenerate -m "$(MSG)"

upgrade:
	poetry run alembic upgrade head

downgrade:
	poetry run alembic downgrade -1
