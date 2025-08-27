#!/bin/bash
# Test the recommended infrastructure setup approach

set -e

echo "🚀 Testing recommended infrastructure setup..."

# 1. Update dependencies with constraints
echo "📦 Installing dependencies with constraints..."
source venv/bin/activate
pip install -r requirements.txt -c constraints.txt

# 2. Start test infrastructure with health checks
echo "🐳 Starting test infrastructure..."
docker compose -f docker-compose.test.yml up -d

# 3. Wait for services to be healthy
echo "🏥 Waiting for services to be healthy..."
docker compose -f docker-compose.test.yml wait

# 4. Verify services are running
echo "✅ Verifying services..."
docker compose -f docker-compose.test.yml ps

# 5. Test service connectivity
echo "🔗 Testing connectivity..."

# Test Redpanda
echo "Testing Redpanda..."
timeout 30 docker compose -f docker-compose.test.yml exec -T redpanda-test rpk cluster info

# Test PostgreSQL
echo "Testing PostgreSQL..."
timeout 30 docker compose -f docker-compose.test.yml exec -T postgres-test pg_isready -U alpha_panda_test

# Test Redis
echo "Testing Redis..."
timeout 30 docker compose -f docker-compose.test.yml exec -T redis-test redis-cli ping

# 6. Run a quick test with test environment
echo "🧪 Running quick test with test environment..."
export $(grep -v '^#' .env.test | xargs)
python -c "
import os
print('✅ DATABASE_URL:', os.getenv('DATABASE_URL'))
print('✅ REDIS_URL:', os.getenv('REDIS_URL'))
print('✅ REDPANDA_BOOTSTRAP_SERVERS:', os.getenv('REDPANDA_BOOTSTRAP_SERVERS'))
"

# 7. Run unit tests to verify everything works
echo "🧪 Running unit tests to verify setup..."
python -m pytest tests/unit/test_broker_segregation.py -v -q

echo "🎉 Infrastructure setup test completed successfully!"
echo ""
echo "✨ Ready to run infrastructure tests:"
echo "   make test-setup                    # Start test infrastructure"
echo "   make test-with-env                 # Run integration/e2e tests"
echo "   make test-performance-with-env     # Run performance tests"
echo "   make test-all-infra                # Run complete test suite"
echo ""
echo "🧹 Cleanup when done:"
echo "   make test-clean                    # Stop and clean test infrastructure"