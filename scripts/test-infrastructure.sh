#!/bin/bash
# Alpha Panda Test Infrastructure Management Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Test environment management (uses standard docker-compose.yml)
setup_test_environment() {
    log_info "Setting up Alpha Panda test environment..."
    
    # Ensure we're in the project root
    cd "$PROJECT_ROOT"
    
    # Start test infrastructure with health checks
    log_info "Starting infrastructure..."
    docker compose -f docker-compose.yml up -d
    
    # Wait for all services to be healthy
    log_info "Waiting for services to be healthy..."
    docker compose -f docker-compose.yml wait || true
    
    # Wait for services to be healthy
    log_info "Waiting for services to be ready..."
    
    # Wait for Redpanda
    log_info "Waiting for Redpanda..."
    timeout 60 bash -c '
        until docker compose -f docker-compose.yml exec -T redpanda rpk cluster info >/dev/null 2>&1; do
            echo "Waiting for Redpanda..."
            sleep 2
        done
    ' || {
        log_error "Redpanda failed to start"
        docker compose -f docker-compose.yml logs redpanda || true
        exit 1
    }
    
    # Wait for PostgreSQL
    log_info "Waiting for PostgreSQL..."
    timeout 30 bash -c '
        until docker compose -f docker-compose.yml exec -T postgres pg_isready -U alpha_panda >/dev/null 2>&1; do
            echo "Waiting for PostgreSQL..."
            sleep 2
        done
    ' || {
        log_error "PostgreSQL failed to start"
        docker compose -f docker-compose.yml logs postgres || true
        exit 1
    }
    
    # Wait for Redis
    log_info "Waiting for Redis..."
    timeout 30 bash -c '
        until docker compose -f docker-compose.yml exec -T redis redis-cli ping >/dev/null 2>&1; do
            echo "Waiting for Redis..."
            sleep 2
        done
    ' || {
        log_error "Redis failed to start"
        docker compose -f docker-compose.yml logs redis || true
        exit 1
    }
    
    # Bootstrap topics
    log_info "Bootstrapping Kafka topics..."
    python scripts/bootstrap_topics.py || {
        log_warning "Topic bootstrap script not found, creating basic topics..."
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create market.ticks --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create paper.signals.raw --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create paper.signals.validated --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create paper.orders.filled --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create zerodha.signals.raw --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create zerodha.signals.validated --partitions 3 --replicas 1 || true
        docker compose -f docker-compose.yml exec -T redpanda rpk topic create zerodha.orders.filled --partitions 3 --replicas 1 || true
    }
    
    # Seed test data
    log_info "Seeding test database..."
    python scripts/seed_test_data.py || {
        log_warning "Test data seeding script not found, using SQL initialization..."
    }
    
    log_success "Test environment ready!"
}

run_unit_tests() {
    log_info "Running unit tests..."
    
    # Ensure virtual environment is activated
    if [[ -z "$VIRTUAL_ENV" ]]; then
        log_warning "Virtual environment not detected, attempting to activate..."
        if [[ -f "venv/bin/activate" ]]; then
            source venv/bin/activate
        else
            log_error "Virtual environment not found. Please run 'make setup' first."
            exit 1
        fi
    fi
    
    # Test dependencies are included in requirements.txt
    
    # Run unit tests with coverage
    python -m pytest tests/unit/ -v \
        --cov=core --cov=services --cov=strategies \
        --cov-report=html --cov-report=xml --cov-report=term-missing \
        --tb=short
}

run_integration_tests() {
    log_info "Running integration tests..."
    
    # Ensure test environment is running
    if ! docker compose -f docker-compose.yml ps | grep -q "Up"; then
        log_warning "Test environment not running, setting up..."
        setup_test_environment
    fi
    
    # Run integration tests
    python -m pytest tests/integration/ -v --tb=short \
        --disable-warnings
}

run_e2e_tests() {
    log_info "Running end-to-end tests..."
    
    # Ensure test environment is running
    if ! docker compose -f docker-compose.yml ps | grep -q "Up"; then
        log_warning "Test environment not running, setting up..."
        setup_test_environment
    fi
    
    # Run E2E tests
    python -m pytest tests/e2e/ -v --tb=short \
        --disable-warnings
}

run_performance_tests() {
    log_info "Running performance tests..."
    
    # Run performance tests (excluding slow tests by default)
    python -m pytest tests/performance/ -v -m "not slow" \
        --tb=short --disable-warnings
    
    log_info "To run slow performance tests, use: pytest tests/performance/ -v -m 'slow'"
}

run_chaos_tests() {
    log_info "Running chaos engineering tests..."
    
    # Run chaos tests
    python -m pytest tests/unit/test_enhanced_error_handling.py::TestChaosEngineering -v \
        --tb=short --disable-warnings
}

run_all_tests() {
    log_info "Running complete test suite..."
    
    # Ensure test environment is set up
    setup_test_environment
    
    # Run tests in order
    log_info "Phase 1: Unit Tests"
    run_unit_tests
    
    log_info "Phase 2: Integration Tests"
    run_integration_tests
    
    log_info "Phase 3: End-to-End Tests"
    run_e2e_tests
    
    log_info "Phase 4: Performance Tests"
    run_performance_tests
    
    log_success "All tests completed!"
    
    # Generate test report
    generate_test_report
}

generate_test_report() {
    log_info "Generating test report..."
    
    REPORT_DIR="$PROJECT_ROOT/test-reports"
    mkdir -p "$REPORT_DIR"
    
    # Generate HTML coverage report
    if [[ -f "htmlcov/index.html" ]]; then
        cp -r htmlcov "$REPORT_DIR/"
        log_success "Coverage report available at: $REPORT_DIR/htmlcov/index.html"
    fi
    
    # Generate performance report if exists
    if [[ -f "performance_report.html" ]]; then
        mv performance_report.html "$REPORT_DIR/"
        log_success "Performance report available at: $REPORT_DIR/performance_report.html"
    fi
    
    # Generate summary report
    cat > "$REPORT_DIR/test_summary.md" << EOF
# Alpha Panda Test Report

Generated on: $(date)

## Test Coverage

See [Coverage Report](htmlcov/index.html) for detailed coverage information.

## Performance Metrics

See [Performance Report](performance_report.html) for detailed performance metrics.

## Test Environment

- **Redpanda**: $(docker compose -f docker-compose.yml exec -T redpanda rpk version | head -1 || echo "Not available")
- **PostgreSQL**: $(docker compose -f docker-compose.yml exec -T postgres psql --version || echo "Not available")
- **Redis**: $(docker compose -f docker-compose.yml exec -T redis redis-server --version || echo "Not available")

## Infrastructure Status

\`\`\`
$(docker compose -f docker-compose.yml ps)
\`\`\`
EOF
    
    log_success "Test summary available at: $REPORT_DIR/test_summary.md"
}

cleanup_test_environment() {
    log_info "Cleaning up test environment..."
    
    # Stop and remove test containers
    docker compose -f docker-compose.yml down -v
    
    # Clean up Docker resources
    docker system prune -f
    
    # Clean up test artifacts
    rm -rf .pytest_cache
    rm -rf htmlcov
    rm -rf .coverage
    rm -f coverage.xml
    
    log_success "Cleanup completed!"
}

show_test_status() {
    log_info "Test Environment Status"
    echo "========================="
    
    if docker compose -f docker-compose.yml ps | grep -q "Up"; then
        log_success "Test environment is running"
        docker compose -f docker-compose.yml ps
        
        # Show topic list
        echo ""
        log_info "Kafka Topics:"
        docker compose -f docker-compose.yml exec -T redpanda rpk topic list || log_warning "Could not list topics"
        
        # Show database status
        echo ""
        log_info "Database Tables:"
        docker compose -f docker-compose.yml exec -T postgres psql -U alpha_panda -d alpha_panda -c "\\dt" || log_warning "Could not list tables"
        
    else
        log_warning "Test environment is not running"
        echo "Use '$0 setup' to start the test environment"
    fi
}

# Command line interface
case "${1:-}" in
    "setup")
        setup_test_environment
        ;;
    "unit")
        run_unit_tests
        ;;
    "integration") 
        run_integration_tests
        ;;
    "e2e")
        run_e2e_tests
        ;;
    "performance")
        run_performance_tests
        ;;
    "chaos")
        run_chaos_tests
        ;;
    "all")
        run_all_tests
        ;;
    "report")
        generate_test_report
        ;;
    "cleanup")
        cleanup_test_environment
        ;;
    "status")
        show_test_status
        ;;
    *)
        echo "Alpha Panda Test Infrastructure Management"
        echo "Usage: $0 {setup|unit|integration|e2e|performance|chaos|all|report|cleanup|status}"
        echo ""
        echo "Commands:"
        echo "  setup       - Set up test infrastructure"
        echo "  unit        - Run unit tests with coverage"
        echo "  integration - Run integration tests"
        echo "  e2e         - Run end-to-end tests"
        echo "  performance - Run performance tests"
        echo "  chaos       - Run chaos engineering tests"
        echo "  all         - Run complete test suite"
        echo "  report      - Generate test reports"
        echo "  cleanup     - Clean up test environment"
        echo "  status      - Show test environment status"
        echo ""
        echo "Examples:"
        echo "  $0 setup     # Initial test environment setup"
        echo "  $0 unit      # Run unit tests only"
        echo "  $0 all       # Run complete test suite"
        exit 1
        ;;
esac
