#!/bin/bash

# AlphaPT Production Deployment Script
# This script handles the complete production deployment process

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DEPLOYMENT_ENV=${DEPLOYMENT_ENV:-production}
BACKUP_DIR="/backups/alphapt"
LOG_FILE="/var/log/alphapt/deployment.log"
HEALTH_CHECK_TIMEOUT=300
ROLLBACK_TIMEOUT=60

# Functions
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

cleanup_on_exit() {
    log "Cleaning up deployment artifacts..."
    # Add cleanup commands here
}

# Trap to ensure cleanup on exit
trap cleanup_on_exit EXIT

# Pre-deployment checks
pre_deployment_checks() {
    log "🔍 Running pre-deployment checks..."
    
    # Check required environment variables
    required_vars=(
        "DATABASE_PASSWORD"
        "JWT_SECRET_KEY"
        "ZERODHA_API_KEY"
        "ZERODHA_API_SECRET"
        "ENCRYPTION_KEY"
        "GRAFANA_PASSWORD"
    )
    
    for var in "${required_vars[@]}"; do
        if [[ -z "${!var}" ]]; then
            error "Required environment variable $var is not set"
            exit 1
        fi
    done
    
    # Check Docker and Docker Compose
    if ! command -v docker &> /dev/null; then
        error "Docker is not installed"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check available disk space (require at least 10GB)
    available_space=$(df / | tail -1 | awk '{print $4}')
    required_space=10485760  # 10GB in KB
    
    if [[ $available_space -lt $required_space ]]; then
        error "Insufficient disk space. Required: 10GB, Available: $(($available_space/1024/1024))GB"
        exit 1
    fi
    
    # Check if ports are available
    ports_to_check=(80 443 5432 6379 8123 4222 9090 9091 9093 3000)
    for port in "${ports_to_check[@]}"; do
        if netstat -tuln | grep ":$port " > /dev/null; then
            warning "Port $port is already in use"
        fi
    done
    
    success "Pre-deployment checks completed"
}

# Backup current deployment
backup_current_deployment() {
    log "💾 Creating backup of current deployment..."
    
    timestamp=$(date +%Y%m%d_%H%M%S)
    backup_path="$BACKUP_DIR/backup_$timestamp"
    
    mkdir -p "$backup_path"
    
    # Backup databases
    if docker ps | grep alphapt-postgres > /dev/null; then
        log "Backing up PostgreSQL database..."
        docker exec alphapt-postgres pg_dump -U alphapt_user alphapt_db > "$backup_path/postgres_backup.sql"
    fi
    
    if docker ps | grep alphapt-redis > /dev/null; then
        log "Backing up Redis data..."
        docker exec alphapt-redis redis-cli BGSAVE
        docker cp alphapt-redis:/data/dump.rdb "$backup_path/redis_backup.rdb"
    fi
    
    # Backup configuration and logs
    if [[ -d "./logs" ]]; then
        cp -r ./logs "$backup_path/"
    fi
    
    if [[ -d "./config" ]]; then
        cp -r ./config "$backup_path/"
    fi
    
    # Create backup metadata
    cat > "$backup_path/metadata.json" << EOF
{
    "timestamp": "$timestamp",
    "deployment_env": "$DEPLOYMENT_ENV",
    "git_commit": "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')",
    "git_branch": "$(git branch --show-current 2>/dev/null || echo 'unknown')",
    "docker_images": $(docker images --format "table {{.Repository}}:{{.Tag}}\t{{.ID}}" | grep alphapt | jq -R . | jq -s .)
}
EOF
    
    success "Backup created at $backup_path"
    echo "$backup_path" > /tmp/alphapt_backup_path
}

# Build and deploy
build_and_deploy() {
    log "🏗️ Building and deploying AlphaPT..."
    
    # Pull latest images
    log "Pulling latest base images..."
    docker-compose -f docker-compose.production.yml pull postgres redis clickhouse nats prometheus alertmanager grafana nginx
    
    # Build AlphaPT application
    log "Building AlphaPT application..."
    docker-compose -f docker-compose.production.yml build alphapt-app
    
    # Stop existing services gracefully
    if docker ps | grep alphapt > /dev/null; then
        log "Stopping existing services..."
        docker-compose -f docker-compose.production.yml down --timeout 30
    fi
    
    # Start services in order
    log "Starting infrastructure services..."
    docker-compose -f docker-compose.production.yml up -d postgres redis clickhouse nats
    
    # Wait for infrastructure to be ready
    log "Waiting for infrastructure services to be ready..."
    sleep 30
    
    # Check database connectivity
    max_attempts=30
    attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        if docker exec alphapt-postgres pg_isready -U alphapt_user -d alphapt_db > /dev/null 2>&1; then
            success "PostgreSQL is ready"
            break
        fi
        log "Waiting for PostgreSQL... (attempt $attempt/$max_attempts)"
        sleep 5
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        error "PostgreSQL failed to start within timeout"
        exit 1
    fi
    
    # Start monitoring services
    log "Starting monitoring services..."
    docker-compose -f docker-compose.production.yml up -d prometheus alertmanager grafana
    
    # Start main application
    log "Starting AlphaPT application..."
    docker-compose -f docker-compose.production.yml up -d alphapt-app alphapt-api
    
    # Start load balancer
    log "Starting Nginx load balancer..."
    docker-compose -f docker-compose.production.yml up -d nginx
    
    success "Deployment completed"
}

# Health checks
run_health_checks() {
    log "🏥 Running health checks..."
    
    # Wait for services to start
    sleep 30
    
    # Check AlphaPT application health
    check_service_health() {
        local service_name=$1
        local health_url=$2
        local max_attempts=60
        local attempt=1
        
        log "Checking $service_name health..."
        
        while [[ $attempt -le $max_attempts ]]; do
            if curl -f -s "$health_url" > /dev/null 2>&1; then
                success "$service_name is healthy"
                return 0
            fi
            log "Waiting for $service_name... (attempt $attempt/$max_attempts)"
            sleep 5
            ((attempt++))
        done
        
        error "$service_name failed health check"
        return 1
    }
    
    # Health check endpoints
    check_service_health "AlphaPT API" "http://localhost:8000/api/health"
    check_service_health "Prometheus" "http://localhost:9091/-/healthy"
    check_service_health "Grafana" "http://localhost:3000/api/health"
    
    # Check database connections
    if ! docker exec alphapt-postgres pg_isready -U alphapt_user -d alphapt_db > /dev/null 2>&1; then
        error "PostgreSQL health check failed"
        return 1
    fi
    
    if ! docker exec alphapt-redis redis-cli ping > /dev/null 2>&1; then
        error "Redis health check failed"
        return 1
    fi
    
    # Check if services are processing data
    log "Checking data processing..."
    sleep 60  # Wait for some data to be processed
    
    # Verify metrics are being collected
    if ! curl -s "http://localhost:9090/api/v1/query?query=up" | grep -q "success"; then
        warning "Prometheus metrics collection may have issues"
    fi
    
    success "All health checks passed"
}

# Performance verification
verify_performance() {
    log "⚡ Verifying performance..."
    
    # Run performance test
    if [[ -f "tests/load_testing/performance_load_test.py" ]]; then
        log "Running performance tests..."
        
        # Activate virtual environment and run tests
        if [[ -f "venv/bin/activate" ]]; then
            source venv/bin/activate
            TESTING=true python -m pytest tests/load_testing/performance_load_test.py --tb=short -v
            
            if [[ $? -eq 0 ]]; then
                success "Performance tests passed"
            else
                warning "Performance tests failed - monitoring required"
            fi
        else
            warning "Virtual environment not found - skipping performance tests"
        fi
    else
        warning "Performance tests not found - skipping"
    fi
    
    # Check resource usage
    log "Checking resource usage..."
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" | grep alphapt
}

# Post-deployment tasks
post_deployment_tasks() {
    log "📋 Running post-deployment tasks..."
    
    # Generate SSL certificates if they don't exist
    if [[ ! -f "nginx/ssl/alphapt.crt" ]]; then
        log "Generating self-signed SSL certificates..."
        mkdir -p nginx/ssl
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/alphapt.key \
            -out nginx/ssl/alphapt.crt \
            -subj "/C=IN/ST=Karnataka/L=Bangalore/O=AlphaPT/CN=alphapt.trading.local"
    fi
    
    # Set up log rotation
    log "Setting up log rotation..."
    cat > /etc/logrotate.d/alphapt << EOF
/var/log/alphapt/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF
    
    # Create monitoring cron job
    log "Setting up monitoring cron job..."
    cat > /tmp/alphapt_monitor.sh << 'EOF'
#!/bin/bash
# AlphaPT monitoring script
curl -f http://localhost:8000/api/health > /dev/null 2>&1 || echo "AlphaPT health check failed at $(date)" >> /var/log/alphapt/health_failures.log
EOF
    
    chmod +x /tmp/alphapt_monitor.sh
    echo "*/5 * * * * /tmp/alphapt_monitor.sh" | crontab -
    
    # Send deployment notification
    if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
        log "Sending deployment notification..."
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"✅ AlphaPT production deployment completed successfully at $(date)\"}" \
            "$SLACK_WEBHOOK_URL" > /dev/null 2>&1 || warning "Failed to send Slack notification"
    fi
    
    success "Post-deployment tasks completed"
}

# Rollback function
rollback() {
    error "Deployment failed - initiating rollback..."
    
    if [[ -f "/tmp/alphapt_backup_path" ]]; then
        backup_path=$(cat /tmp/alphapt_backup_path)
        log "Rolling back to backup: $backup_path"
        
        # Stop current services
        docker-compose -f docker-compose.production.yml down --timeout 30
        
        # Restore databases
        if [[ -f "$backup_path/postgres_backup.sql" ]]; then
            log "Restoring PostgreSQL database..."
            # Start only postgres for restore
            docker-compose -f docker-compose.production.yml up -d postgres
            sleep 30
            docker exec -i alphapt-postgres psql -U alphapt_user -d alphapt_db < "$backup_path/postgres_backup.sql"
        fi
        
        if [[ -f "$backup_path/redis_backup.rdb" ]]; then
            log "Restoring Redis data..."
            docker-compose -f docker-compose.production.yml up -d redis
            sleep 10
            docker cp "$backup_path/redis_backup.rdb" alphapt-redis:/data/dump.rdb
            docker restart alphapt-redis
        fi
        
        success "Rollback completed"
    else
        error "No backup found for rollback"
    fi
    
    exit 1
}

# Main deployment flow
main() {
    log "🚀 Starting AlphaPT production deployment..."
    
    # Set error handler for rollback
    trap rollback ERR
    
    pre_deployment_checks
    backup_current_deployment
    build_and_deploy
    run_health_checks
    verify_performance
    post_deployment_tasks
    
    success "🎉 AlphaPT production deployment completed successfully!"
    
    log "📊 Deployment Summary:"
    log "- Environment: $DEPLOYMENT_ENV"
    log "- Timestamp: $(date)"
    log "- Git commit: $(git rev-parse HEAD 2>/dev/null || echo 'unknown')"
    log "- Services: $(docker ps --filter "name=alphapt" --format "{{.Names}}" | wc -l) containers running"
    log "- Health status: All services healthy"
    log ""
    log "🌐 Access URLs:"
    log "- API: https://localhost/api/"
    log "- WebSocket: wss://localhost/ws/"
    log "- Grafana: http://localhost:3000/"
    log "- Prometheus: http://localhost:9091/"
    log ""
    log "📈 Next steps:"
    log "1. Configure DNS to point to this server"
    log "2. Update SSL certificates with proper domain"
    log "3. Set up external backup schedule"
    log "4. Configure external monitoring alerts"
    log "5. Run integration tests with live market data"
}

# Handle command line arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "rollback")
        rollback
        ;;
    "health-check")
        run_health_checks
        ;;
    "backup")
        backup_current_deployment
        ;;
    *)
        echo "Usage: $0 {deploy|rollback|health-check|backup}"
        exit 1
        ;;
esac