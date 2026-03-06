# Use the official Apify Python base image
FROM apify/actor-python:3.12

# Install system dependencies if any
# RUN apk add --no-cache ...

# Install Python requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy the entire source code
COPY . ./

# Ensure the core library is accessible
# Structural note: src/main.py will `from dagpipe.generator...`
# We copier src/dagpipe/ into actors/dagpipe-generator-mcp/src/dagpipe/
# so the structure in the container should be:
# /usr/src/app/src/main.py
# /usr/src/app/src/dagpipe/
# So we need to set PYTHONPATH or ensure we run from src/

ENV PYTHONPATH="${PYTHONPATH}:/usr/src/app/src"

# Run the actor
CMD ["python3", "-m", "src.main"]
