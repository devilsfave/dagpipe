FROM apify/actor-node:22 AS builder

# Copy package.json to speed up the build using Docker layer cache
COPY --chown=myuser:myuser package*.json ./
RUN npm install --include=dev --audit=false

# Copy all files including JS/TS source code and local Python dependencies into the image
COPY --chown=myuser:myuser . ./
RUN npm run build

FROM apify/actor-node:22

USER root
# Install python and pip to run the backend generator engine
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*
USER myuser

COPY --chown=myuser:myuser package*.json ./
RUN npm --quiet set progress=false \
    && npm install --omit=dev --omit=optional \
    && rm -r ~/.npm

# Create a virtual environment and install python dependencies needed by dagpipe
RUN python3 -m venv /home/myuser/venv
ENV PATH="/home/myuser/venv/bin:$PATH"
RUN pip install groq pyyaml pydantic

# Copy the built TS files from the builder stage
COPY --from=builder --chown=myuser:myuser /usr/src/app/dist ./dist

# Copy the remaining project files (including src/wrapper.py and src/dagpipe_lib)
COPY --chown=myuser:myuser . ./

CMD ["node", "dist/main.js"]
