# Use the official Python image with GPU support
FROM nvidia/cuda:11.3.1-cudnn8-runtime-ubuntu20.04

# Install Python and other dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Expose the port
EXPOSE 5000

# Set the entry point
CMD ["python3", "app.py"]
