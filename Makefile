.PHONY: run install shell test lint format migrate revision upgrade downgrade reset-db seed-demo

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

seed:
	poetry run python -m app.run_seeds

revision:
	poetry run alembic revision --autogenerate -m "$(msg)"

upgrade:
	poetry run alembic upgrade head

downgrade:
	poetry run alembic downgrade -1

reset-db:
	poetry run python app/scripts/reset_db.py

seed-demo:
	poetry run python -m app.scripts.seed_demo_data $(tenant)
