.PHONY: up down build test clean

SHELL := /bin/bash

# Ensure docker commands execute with docker group permissions
DOCKER_CMD := $(shell groups | grep -q '\bdocker\b' && echo "docker" || echo "sg docker -c \"docker")
COMPOSE_CMD := $(shell groups | grep -q '\bdocker\b' && echo "docker compose" || echo "sg docker -c \"docker compose")

up:
	sg docker -c "docker compose up --build -d" || docker compose up --build -d

down:
	sg docker -c "docker compose down" || docker compose down

build:
	sg docker -c "docker compose build" || docker compose build

test:
	./venv/bin/pytest backend/tests/test_api.py -v

clean:
	sg docker -c "docker compose down -v" || docker compose down -v
