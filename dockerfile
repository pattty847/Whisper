# Use the official Python image with GPU support (adjust if needed)
FROM python:3.11-slim

# Set environment variables to avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive

# Install Python and other dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Install ngrok
RUN curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && \
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | tee /etc/apt/sources.list.d/ngrok.list && \
    apt-get update && apt-get install -y ngrok

# Copy the rest of the application code
COPY . .

# Make the start.sh file executable
RUN chmod +x start.sh

# Expose port 5000 for Flask
EXPOSE 5000

# Start both Flask and ngrok
CMD ["./start.sh"]
