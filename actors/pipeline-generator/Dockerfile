# ── Stage 1: Builder (TypeScript compilation) ────────────────────────────────
FROM apify/actor-node:22 AS builder

COPY --chown=myuser:myuser package*.json ./
RUN npm install --include=dev --audit=false

COPY --chown=myuser:myuser . ./
RUN npm run build

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# IMPORTANT: Stay as the default user (myuser) the ENTIRE time.
# Never switch to root after npm install — it corrupts npm's rename locks.
FROM apify/actor-node:22

# Install production npm packages FIRST (as myuser, which is the image default).
COPY --chown=myuser:myuser package*.json ./
RUN npm --quiet set progress=false \
    && npm install --omit=dev --omit=optional \
    && echo "Node.js: $(node --version) | npm: $(npm --version)" \
    && rm -rf ~/.npm

# Now switch to root ONLY to install system packages, AFTER npm is done.
USER root
RUN apk add --no-cache python3 py3-pip
# Install Python packages globally so myuser can run them
RUN pip install --no-cache-dir --break-system-packages groq pyyaml pydantic
USER myuser

# Copy compiled TS from builder
COPY --from=builder --chown=myuser:myuser /usr/src/app/dist ./dist

# Copy all source files (wrapper.py, src/dagpipe_lib, etc.)
COPY --chown=myuser:myuser . ./

CMD ["node", "dist/main.js"]
