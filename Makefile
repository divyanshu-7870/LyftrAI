.PHONY: up down build test clean

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

test:
	./venv/bin/pytest backend/tests/test_api.py -v

clean:
	docker compose down -v
