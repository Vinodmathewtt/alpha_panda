"""Production build configuration and utilities for AlphaPT.

This module handles production-specific build configurations,
including exclusion of development-only components like mock market feed.
"""

import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any
import json

logger = logging.getLogger(__name__)


class ProductionBuilder:
    """Handle production build configuration and component exclusion."""
    
    def __init__(self, project_root: Path = None):
        """Initialize production builder.
        
        Args:
            project_root: Root directory of the project
        """
        self.project_root = project_root or Path(__file__).parent
        self.build_dir = self.project_root / "dist" / "production"
        
        # Components to exclude in production
        self.excluded_components = [
            "mock_market_feed",
            "examples",
            "tests",
            "venv",
            ".git",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            "*.pyd",
            ".pytest_cache",
            ".coverage",
            "htmlcov"
        ]
        
        # Development-only files to exclude
        self.excluded_files = [
            "test_*.py",
            "*_test.py",
            "demo_*.py",
            ".env.example",
            "docker-compose.yml",  # Will be replaced with production version
            "Makefile",
            ".pre-commit-config.yaml",
            "pytest.ini"
        ]
    
    def validate_production_environment(self) -> bool:
        """Validate that environment is ready for production build.
        
        Returns:
            bool: True if environment is valid for production
        """
        try:
            # Check required environment variables
            required_env_vars = [
                "ENVIRONMENT",
                "POSTGRES_HOST",
                "CLICKHOUSE_HOST", 
                "REDIS_URL",
                "NATS_URL"
            ]
            
            missing_vars = []
            for var in required_env_vars:
                if not os.getenv(var):
                    missing_vars.append(var)
            
            if missing_vars:
                logger.error(f"Missing required environment variables: {missing_vars}")
                return False
            
            # Validate ENVIRONMENT is set to production
            if os.getenv("ENVIRONMENT") != "production":
                logger.error("ENVIRONMENT must be set to 'production' for production build")
                return False
            
            # Ensure MOCK_MARKET_FEED is disabled
            if os.getenv("MOCK_MARKET_FEED", "").lower() == "true":
                logger.error("MOCK_MARKET_FEED must be disabled (false) for production build")
                return False
            
            logger.info("Production environment validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Production environment validation failed: {e}")
            return False
    
    def create_production_pyproject_toml(self) -> None:
        """Create production-optimized pyproject.toml without dev dependencies."""
        try:
            import toml
            
            # Read original pyproject.toml
            original_path = self.project_root / "pyproject.toml"
            if not original_path.exists():
                raise FileNotFoundError("pyproject.toml not found")
            
            with open(original_path, 'r') as f:
                config = toml.load(f)
            
            # Remove development dependencies
            if 'project' in config and 'optional-dependencies' in config['project']:
                # Keep only production dependencies
                optional_deps = config['project']['optional-dependencies']
                production_deps = {}
                
                # Include only test dependencies for production testing
                if 'test' in optional_deps:
                    production_deps['test'] = optional_deps['test']
                
                config['project']['optional-dependencies'] = production_deps
            
            # Remove development-specific configurations
            dev_configs_to_remove = ['tool.black', 'tool.isort', 'tool.mypy']
            for config_key in dev_configs_to_remove:
                keys = config_key.split('.')
                current = config
                for key in keys[:-1]:
                    if key in current:
                        current = current[key]
                    else:
                        break
                else:
                    if keys[-1] in current:
                        del current[keys[-1]]
            
            # Write production pyproject.toml
            production_path = self.build_dir / "pyproject.toml"
            production_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(production_path, 'w') as f:
                toml.dump(config, f)
            
            logger.info("Created production pyproject.toml")
            
        except Exception as e:
            logger.error(f"Failed to create production pyproject.toml: {e}")
            raise
    
    def create_production_docker_config(self) -> None:
        """Create production-optimized Docker configuration."""
        try:
            # Production Docker Compose
            production_compose = {
                'version': '3.8',
                'services': {
                    'postgres': {
                        'image': 'postgres:15-alpine',
                        'environment': {
                            'POSTGRES_DB': '${POSTGRES_DB}',
                            'POSTGRES_USER': '${POSTGRES_USER}',
                            'POSTGRES_PASSWORD': '${POSTGRES_PASSWORD}'
                        },
                        'ports': ['5432:5432'],
                        'volumes': [
                            'postgres_data:/var/lib/postgresql/data',
                            './database/init_postgresql.sql:/docker-entrypoint-initdb.d/init.sql'
                        ],
                        'healthcheck': {
                            'test': ['CMD-SHELL', 'pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}'],
                            'interval': '10s',
                            'timeout': '5s',
                            'retries': 5
                        },
                        'networks': ['alphapt-network']
                    },
                    'clickhouse': {
                        'image': 'clickhouse/clickhouse-server:23.8-alpine',
                        'environment': {
                            'CLICKHOUSE_DB': '${CLICKHOUSE_DB}',
                            'CLICKHOUSE_USER': '${CLICKHOUSE_USER}',
                            'CLICKHOUSE_PASSWORD': '${CLICKHOUSE_PASSWORD}'
                        },
                        'ports': ['9000:9000', '8123:8123'],
                        'volumes': [
                            'clickhouse_data:/var/lib/clickhouse',
                            'clickhouse_logs:/var/log/clickhouse-server'
                        ],
                        'networks': ['alphapt-network']
                    },
                    'redis': {
                        'image': 'redis:7-alpine',
                        'ports': ['6379:6379'],
                        'volumes': ['redis_data:/data'],
                        'command': 'redis-server --appendonly yes --maxmemory 1gb --maxmemory-policy allkeys-lru',
                        'networks': ['alphapt-network']
                    },
                    'nats': {
                        'image': 'nats:2.10-alpine',
                        'ports': ['4222:4222', '8222:8222'],
                        'command': '--jetstream --store_dir=/data --http_port=8222',
                        'volumes': ['nats_data:/data'],
                        'networks': ['alphapt-network']
                    },
                    'alphapt': {
                        'build': '.',
                        'ports': ['8000:8000'],
                        'environment': [
                            'ENVIRONMENT=production',
                            'MOCK_MARKET_FEED=false',
                            'POSTGRES_HOST=postgres',
                            'CLICKHOUSE_HOST=clickhouse',
                            'REDIS_URL=redis://redis:6379',
                            'NATS_URL=nats://nats:4222'
                        ],
                        'depends_on': {
                            'postgres': {'condition': 'service_healthy'},
                            'clickhouse': {'condition': 'service_healthy'},
                            'redis': {'condition': 'service_healthy'},
                            'nats': {'condition': 'service_healthy'}
                        },
                        'networks': ['alphapt-network'],
                        'restart': 'unless-stopped'
                    }
                },
                'volumes': {
                    'postgres_data': {'driver': 'local'},
                    'clickhouse_data': {'driver': 'local'},
                    'clickhouse_logs': {'driver': 'local'},
                    'redis_data': {'driver': 'local'},
                    'nats_data': {'driver': 'local'}
                },
                'networks': {
                    'alphapt-network': {
                        'driver': 'bridge'
                    }
                }
            }
            
            # Write production docker-compose
            import yaml
            production_compose_path = self.build_dir / "docker-compose.production.yml"
            with open(production_compose_path, 'w') as f:
                yaml.dump(production_compose, f, default_flow_style=False)
            
            # Production Dockerfile
            dockerfile_content = '''FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml ./
RUN pip install -e .

# Copy application code (excluding development components)
COPY alphaPT/ ./alphaPT/
COPY data/ ./data/
COPY risk_manager/ ./risk_manager/
COPY paper_trade/ ./paper_trade/
COPY zerodha_trade/ ./zerodha_trade/
COPY zerodha_market_feed/ ./zerodha_market_feed/
COPY strategy_manager/ ./strategy_manager/
COPY api/ ./api/
COPY database/ ./database/
COPY monitoring/ ./monitoring/

# Create non-root user
RUN useradd -m -u 1000 alphapt && chown -R alphapt:alphapt /app
USER alphapt

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "alphaPT.main"]
'''
            
            dockerfile_path = self.build_dir / "Dockerfile"
            with open(dockerfile_path, 'w') as f:
                f.write(dockerfile_content)
            
            logger.info("Created production Docker configuration")
            
        except Exception as e:
            logger.error(f"Failed to create production Docker config: {e}")
            raise
    
    def copy_production_code(self) -> None:
        """Copy application code excluding development components."""
        try:
            # Create build directory
            self.build_dir.mkdir(parents=True, exist_ok=True)
            
            # Define production components to include
            production_components = [
                "alphaPT",
                "data", 
                "risk_manager",
                "paper_trade",
                "zerodha_trade",
                "zerodha_market_feed",
                "strategy_manager",
                "api",
                "database",
                "monitoring"
            ]
            
            # Copy production components
            for component in production_components:
                src_path = self.project_root / component
                if src_path.exists():
                    dst_path = self.build_dir / component
                    if src_path.is_dir():
                        shutil.copytree(src_path, dst_path, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
                    else:
                        shutil.copy2(src_path, dst_path)
                    logger.info(f"Copied {component} to production build")
            
            # Copy essential configuration files
            essential_files = [
                "README.md",
                "LICENSE",
                ".env.production.example"
            ]
            
            for file_name in essential_files:
                src_file = self.project_root / file_name
                if src_file.exists():
                    shutil.copy2(src_file, self.build_dir / file_name)
            
            logger.info("Production code copy completed")
            
        except Exception as e:
            logger.error(f"Failed to copy production code: {e}")
            raise
    
    def create_production_config(self) -> None:
        """Create production-specific configuration files."""
        try:
            # Production environment template
            env_template = '''# AlphaPT Production Configuration
ENVIRONMENT=production
DEBUG=false

# CRITICAL: Mock market feed MUST be disabled in production
MOCK_MARKET_FEED=false

# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=alphapt_prod
POSTGRES_USER=alphapt_prod
POSTGRES_PASSWORD=your_secure_password

# ClickHouse Configuration  
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_DB=alphapt_prod
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=your_secure_password

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# NATS Configuration
NATS_URL=nats://localhost:4222

# Zerodha Configuration (Required for production)
ZERODHA_API_KEY=your_api_key
ZERODHA_API_SECRET=your_api_secret
ZERODHA_REQUEST_TOKEN=your_request_token

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_CORS_ORIGINS=["http://localhost:3000"]

# Monitoring Configuration
PROMETHEUS_PORT=8001
GRAFANA_ADMIN_PASSWORD=your_secure_password

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
'''
            
            env_file = self.build_dir / ".env.production.example"
            with open(env_file, 'w') as f:
                f.write(env_template)
            
            # Production startup script
            startup_script = '''#!/bin/bash

# AlphaPT Production Startup Script

set -e

echo "🚀 Starting AlphaPT Production Deployment..."

# Validate environment
if [ "$ENVIRONMENT" != "production" ]; then
    echo "❌ ENVIRONMENT must be set to 'production'"
    exit 1
fi

if [ "$MOCK_MARKET_FEED" = "true" ]; then
    echo "❌ MOCK_MARKET_FEED must be disabled (false) for production"
    exit 1
fi

# Check required environment variables
required_vars=("POSTGRES_HOST" "CLICKHOUSE_HOST" "REDIS_URL" "NATS_URL" "ZERODHA_API_KEY")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Required environment variable $var is not set"
        exit 1
    fi
done

echo "✅ Environment validation passed"

# Start services
echo "🔄 Starting AlphaPT services..."
docker-compose -f docker-compose.production.yml up -d

echo "✅ AlphaPT production deployment completed"
echo "🌐 API available at: http://localhost:8000"
echo "📊 Monitoring available at: http://localhost:3000"
'''
            
            startup_file = self.build_dir / "start_production.sh"
            with open(startup_file, 'w') as f:
                f.write(startup_script)
            startup_file.chmod(0o755)
            
            logger.info("Created production configuration files")
            
        except Exception as e:
            logger.error(f"Failed to create production config: {e}")
            raise
    
    def verify_production_build(self) -> bool:
        """Verify that production build is correct and complete.
        
        Returns:
            bool: True if build verification passes
        """
        try:
            # Check that mock components are excluded
            mock_dirs = [
                self.build_dir / "mock_market_feed",
                self.build_dir / "examples",
                self.build_dir / "tests"
            ]
            
            for mock_dir in mock_dirs:
                if mock_dir.exists():
                    logger.error(f"Production build contains excluded component: {mock_dir}")
                    return False
            
            # Check that essential components are present
            required_components = [
                "alphaPT",
                "zerodha_trade", 
                "zerodha_market_feed",
                "risk_manager",
                "paper_trade",
                "strategy_manager"
            ]
            
            for component in required_components:
                component_path = self.build_dir / component
                if not component_path.exists():
                    logger.error(f"Required component missing from production build: {component}")
                    return False
            
            # Check configuration files
            required_files = [
                "pyproject.toml",
                "docker-compose.production.yml",
                "Dockerfile",
                ".env.production.example",
                "start_production.sh"
            ]
            
            for file_name in required_files:
                file_path = self.build_dir / file_name
                if not file_path.exists():
                    logger.error(f"Required file missing from production build: {file_name}")
                    return False
            
            logger.info("✅ Production build verification passed")
            return True
            
        except Exception as e:
            logger.error(f"Production build verification failed: {e}")
            return False
    
    def build_production(self) -> bool:
        """Execute complete production build process.
        
        Returns:
            bool: True if production build succeeds
        """
        try:
            logger.info("🚀 Starting AlphaPT production build...")
            
            # Validate environment
            if not self.validate_production_environment():
                return False
            
            # Clean previous build
            if self.build_dir.exists():
                shutil.rmtree(self.build_dir)
            
            # Copy production code
            self.copy_production_code()
            
            # Create production configurations
            self.create_production_pyproject_toml()
            self.create_production_docker_config()
            self.create_production_config()
            
            # Verify build
            if not self.verify_production_build():
                return False
            
            logger.info("✅ AlphaPT production build completed successfully")
            logger.info(f"📁 Production build available at: {self.build_dir}")
            logger.info("🚀 To deploy: cd dist/production && ./start_production.sh")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Production build failed: {e}")
            return False


def main():
    """Main entry point for production build."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    builder = ProductionBuilder()
    success = builder.build_production()
    
    if not success:
        exit(1)
    
    print("\n🎉 Production build completed successfully!")
    print(f"📁 Build location: {builder.build_dir}")
    print("📋 Next steps:")
    print("   1. Copy .env.production.example to .env and configure")
    print("   2. Run: cd dist/production && ./start_production.sh")


if __name__ == "__main__":
    main()