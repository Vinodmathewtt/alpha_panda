# AlphaPT Makefile

.PHONY: help install install-dev test test-cov lint format clean build docker-build docker-run docker-stop setup-dev run

# Default target
help:
	@echo "AlphaPT Development Commands"
	@echo "============================"
	@echo "install          Install production dependencies"
	@echo "install-dev      Install development dependencies"
	@echo "test             Run tests"
	@echo "test-cov         Run tests with coverage"
	@echo "lint             Run linting (flake8, mypy)"
	@echo "format           Format code (black, isort)"
	@echo "clean            Clean build artifacts"
	@echo "build            Build package"
	@echo "docker-build     Build Docker image"
	@echo "docker-run       Run application with Docker Compose"
	@echo "docker-stop      Stop Docker Compose services"
	@echo "setup-dev        Setup development environment"
	@echo "run              Run application locally"

# Installation
install:
	pip install -e .

install-dev:
	pip install -e ".[dev,test]"

# Testing
test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=core --cov-report=html --cov-report=term

# Code quality
lint:
	flake8 core/ tests/
	mypy core/

format:
	black core/ tests/
	isort core/ tests/

# Build and clean
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete

build:
	python -m build

# Docker
docker-build:
	docker build -t alphapt:latest .

docker-run:
	docker-compose up -d

docker-stop:
	docker-compose down

# Development setup
setup-dev: install-dev
	cp .env.example .env
	@echo "Development environment setup complete!"
	@echo "Please edit .env file with your configuration"

# Run application
run:
	python -m main

# Database migrations (when implemented)
migrate:
	alembic upgrade head

# Start services for development
start-services:
	docker-compose up -d postgres clickhouse redis nats prometheus grafana

# Stop services
stop-services:
	docker-compose down