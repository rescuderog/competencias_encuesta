FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directory for database
RUN mkdir -p /app/instance

# Expose port (Railway will set PORT env variable)
ENV PORT=5000
EXPOSE $PORT

# Run with gunicorn
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --timeout 120 app:app
