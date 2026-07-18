.PHONY: run install shell test lint format migrate revision upgrade downgrade reset-db seed-demo docker-build docker-run docker-dev

APP=app.main:app
IMAGE_NAME=petshop-backend

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

docker-build:
	docker build -t $(IMAGE_NAME) .

docker-run:
	docker run --env-file .env -p 8000:8080 $(IMAGE_NAME)

docker-dev:
	docker run --env-file .env -p 8000:8080 -v "$(CURDIR):/app" $(IMAGE_NAME) poetry run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

db-restore-backup:
	@echo "Restaurando banco de dados a partir do arquivo de backup..."
	@echo "PS: O arquivo SQL gerado com --clean ja deleta (DROP) as tabelas automaticamente antes de recria-las!"
	docker run --rm -i postgres:17 psql "$(url)" < "$(file)"
