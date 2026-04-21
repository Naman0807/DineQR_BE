# Docker Setup Documentation

This document outlines the Docker configuration for the DineQR backend application.

## Overview

The backend uses a multi-stage Docker build to create an optimized production image. The build process consists of three stages:

1. **Base Stage** - Sets up Python runtime with required system dependencies
2. **Builder Stage** - Copies application source code
3. **Production Stage** - Creates the final production image with non-root user

## Docker Files

### `.dockerignore`

Excludes files and directories that should not be included in the Docker image:

- Python cache and compilation artifacts
- Virtual environments
- IDE configuration files
- Git metadata
- Test coverage reports
- Environment files containing secrets
- Database files
- Log files
- OS-specific files

### `Dockerfile`

A three-stage multi-stage build:

| Stage | Purpose |
|-------|---------|
| `base` | Python 3.11-slim with libpq-dev, build-essential, and pkg-config |
| `builder` | Copies application code (app/, alembic/) |
| `production` | Final image running as non-root user `appuser` |

## Build Configuration

- **Base Image**: `python:3.11-slim`
- **Python Version**: 3.11
- **Port**: 8000
- **Non-root User**: `appuser`
- **Health Check**: HTTP GET to `/health` endpoint

## Environment Variables

| Variable | Value | Description |
|----------|-------|-------------|
| `PYTHONDONTWRITEBYTECODE` | 1 | Disable .pyc files |
| `PYTHONUNBUFFERED` | 1 | Unbuffered stdout/stderr |
| `PYTHONFAULTHANDLER` | 1 | Enable fault handler |
| `PYTHONPATH` | /app | Python module path |

## Building the Image

```bash
docker build -t dineqr-backend:latest .
```

## Running the Container

```bash
docker run -d \
  --name dineqr-backend \
  -p 8000:8000 \
  -e DATABASE_URL=<database_url> \
  dineqr-backend:latest
```

## Production Considerations

1. **Secrets Management**: Use Docker secrets or environment variables for sensitive data
2. **Database**: Ensure PostgreSQL is accessible via `DATABASE_URL`
3. **Health Check**: Requires `/health` endpoint to be implemented in the application
4. **Non-root User**: Application runs as `appuser` for security
5. **Layer Caching**: Requirements.txt should be copied before source code for better cache utilization