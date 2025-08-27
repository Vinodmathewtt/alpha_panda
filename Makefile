# Alpha Panda Makefile
.PHONY: help install dev up down bootstrap seed run test test-setup test-unit test-integration test-e2e test-performance test-chaos test-all test-status test-report test-clean clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install:  ## Install dependencies with constraints
	pip install -r requirements.txt -c constraints.txt

dev:  ## Set up development environment
	@echo "🐼 Setting up Alpha Panda development environment..."
	cp .env.example .env
	@echo "✓ Created .env file"
	pip install -r requirements.txt -c constraints.txt
	@echo "✓ Installed dependencies"

up:  ## Start infrastructure (docker-compose up)
	docker-compose up -d
	@echo "✓ Infrastructure started"
	@echo "Waiting for services to be ready..."
	sleep 10

down:  ## Stop infrastructure
	docker-compose down
	@echo "✓ Infrastructure stopped"

bootstrap:  ## Bootstrap Redpanda topics
	python cli.py bootstrap

seed:  ## Seed test data
	python cli.py seed

run:  ## Run Alpha Panda application
	python cli.py run

test:  ## Run unit tests
	@echo "🧪 Running unit tests..."
	@./scripts/test-infrastructure.sh unit

test-setup:  ## Set up test environment with health checks
	@echo "🚀 Setting up test environment..."
	docker compose -f docker-compose.test.yml up -d
	docker compose -f docker-compose.test.yml wait
	@echo "✓ Test infrastructure ready and healthy"

test-unit:  ## Run unit tests only
	@echo "🧪 Running unit tests..."
	@./scripts/test-infrastructure.sh unit

test-integration:  ## Run integration tests
	@echo "🔗 Running integration tests..."
	@./scripts/test-infrastructure.sh integration

test-e2e:  ## Run end-to-end tests
	@echo "🌍 Running end-to-end tests..."
	@./scripts/test-infrastructure.sh e2e

test-performance:  ## Run performance tests
	@echo "⚡ Running performance tests..."
	@./scripts/test-infrastructure.sh performance

test-chaos:  ## Run chaos engineering tests
	@echo "🌪️  Running chaos engineering tests..."
	@./scripts/test-infrastructure.sh chaos

test-all:  ## Run complete test suite
	@echo "🎯 Running complete test suite..."
	@./scripts/test-infrastructure.sh all

test-status:  ## Show test environment status
	@echo "📊 Checking test environment status..."
	@./scripts/test-infrastructure.sh status

test-report:  ## Generate test reports
	@echo "📋 Generating test reports..."
	@./scripts/test-infrastructure.sh report

test-clean:  ## Clean test infrastructure
	@echo "🧹 Cleaning test infrastructure..."
	docker compose -f docker-compose.test.yml down -v
	docker system prune -f

clean:  ## Clean up containers and volumes
	docker-compose down -v
	docker system prune -f

test-with-env:  ## Run integration/e2e tests with test environment
	@echo "🧪 Running tests with test environment..."
	@export $$(grep -v '^#' .env.test | xargs) && \
	 python -m pytest tests/integration/ tests/e2e/ -v --tb=short

test-performance-with-env:  ## Run performance tests with test environment
	@echo "⚡ Running performance tests with test environment..."
	@export $$(grep -v '^#' .env.test | xargs) && \
	 python -m pytest tests/performance/ -v -m "not slow"

test-all-infra:  ## Run all infrastructure tests
	@echo "🎯 Running complete infrastructure test suite..."
	make test-setup
	@export $$(grep -v '^#' .env.test | xargs) && \
	 python -m pytest tests/integration/ tests/e2e/ tests/performance/ -v

setup: dev up bootstrap seed  ## Complete setup for first run
	@echo "🎉 Alpha Panda is ready to go!"
	@echo "Run 'make run' to start the application"