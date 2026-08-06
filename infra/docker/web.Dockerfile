# AtlasKB web image (Next.js 14).
# Build context is apps/web (see docker-compose.yml).
# Runs the Next.js dev server — appropriate for this scaffold phase.
FROM node:20-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json ./
RUN npm install

# Copy the application source.
COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
