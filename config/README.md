# Configuration Files

## Overview

The config directory contains external configuration files for Alpha Panda infrastructure components and third-party services. These are deployment-specific configurations separate from the application configuration managed in `core/config/`.

## Components

### `redpanda-console.yml`
Configuration for Redpanda Console (Kafka UI):

- **Kafka Brokers**: Development cluster connection settings
- **Console Settings**: Web UI enablement and access control
- **Client Identification**: Console client configuration for monitoring

## Configuration Structure

```yaml
kafka:
  brokers: ["redpanda:29092"]  # Redpanda cluster endpoints
  clientId: "alpha-panda-console"  # Client identification

console:
  enabled: true  # Enable web console interface
```

## Usage

### Development Environment
The configuration is automatically loaded by Docker Compose services:

```yaml
# docker-compose.yml
redpanda-console:
  image: redpandadata/console:latest
  volumes:
    - ./config/redpanda-console.yml:/tmp/config.yml
```

### Production Deployment
For production, override configuration values:

```bash
# Environment-specific configuration
KAFKA_BROKERS=prod-redpanda-1:9092,prod-redpanda-2:9092
CONSOLE_ENABLED=true
```

## Configuration Categories

- **Infrastructure Config**: External service configurations (Redpanda Console)
- **Application Config**: See `core/config/` for application settings
- **Environment Config**: `.env` files for environment-specific values
- **Database Config**: Connection strings and migration settings

## Architecture Integration

- **Separation of Concerns**: Infrastructure configs separate from application logic
- **Environment Agnostic**: Base configurations with environment overrides
- **Service Discovery**: Configuration supports dynamic service discovery
- **Monitoring Integration**: Console configuration enables infrastructure monitoring

## Configuration Management

### File Hierarchy
1. **Base Configuration**: Default settings in config files
2. **Environment Overrides**: Environment variables take precedence
3. **Runtime Configuration**: Dynamic configuration from database/Redis
4. **Feature Flags**: Runtime feature toggles via application config

### Security Considerations
- **No Secrets**: Configuration files contain no sensitive data
- **Environment Variables**: Secrets injected via environment variables
- **Access Control**: File-level access control for sensitive configurations
- **Audit Trail**: Configuration changes tracked in version control

## Dependencies

- **Docker Compose**: Configuration mounting and service orchestration
- **Redpanda Console**: Kafka cluster monitoring and management
- **Environment Files**: Integration with `.env` configuration system