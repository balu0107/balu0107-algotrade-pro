# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Copy dependency list and install requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the bot source code
COPY . .

# Command to run your bot script
CMD ["python", "bot.py"]