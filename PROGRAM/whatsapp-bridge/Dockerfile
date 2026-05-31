FROM node:20-slim

# Chromium для whatsapp-web.js
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 \
    libgcc-s1 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 \
    libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 lsb-release \
    wget xdg-utils \
    && rm -rf /var/lib/apt/lists/*

ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app
COPY package*.json ./
RUN npm install --omit=dev

COPY server.js ./

EXPOSE 3001

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
HEALTHCHECK --interval=15s --timeout=3s --start-period=15s --retries=5 \
    CMD curl -fsS http://localhost:3001/health || exit 1

# Запускаем под non-root user — даже с --no-sandbox у Chromium не должен быть полный root.
# Каталог .wa-sessions создаём заранее и chown'им, чтобы entrypoint мог писать в смонтированный volume.
RUN groupadd --system --gid 1001 wabridge \
    && useradd  --system --uid 1001 --gid wabridge --home-dir /app --shell /usr/sbin/nologin wabridge \
    && mkdir -p /app/.wa-sessions \
    && chown -R wabridge:wabridge /app

USER wabridge

CMD ["node", "server.js"]
