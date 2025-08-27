# AlphaPT Docker Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV APP_DIR=/app

# Create app directory
WORKDIR $APP_DIR

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml LICENSE README.md ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy application code
COPY core/ ./core/
COPY app/ ./app/
COPY api/ ./api/
COPY storage/ ./storage/
COPY mock_market_feed/ ./mock_market_feed/
COPY zerodha_market_feed/ ./zerodha_market_feed/
COPY zerodha_trade/ ./zerodha_trade/
COPY paper_trade/ ./paper_trade/
COPY risk_manager/ ./risk_manager/
COPY strategy_manager/ ./strategy_manager/
COPY instrument_data/ ./instrument_data/
COPY main.py ./
COPY .env.example ./.env

# Create logs directory
RUN mkdir -p logs

# Create non-root user
RUN useradd -m -u 1000 alphapt && chown -R alphapt:alphapt $APP_DIR
USER alphapt

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import asyncio; from app.application import AlphaPTApplication; app = AlphaPTApplication(); print(asyncio.run(app.health_check()))"

# Expose ports
EXPOSE 8000 8001

# Command to run the application
CMD ["python", "-m", "main"]