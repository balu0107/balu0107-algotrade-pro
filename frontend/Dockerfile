# Use official Node.js image as base
FROM node:20-alpine AS builder
WORKDIR /app

# Copy dependency definitions
COPY package*.json ./
RUN npm install

# Copy source code and build the Next.js application
COPY . .
RUN npm run build

# Production image, copy all the files and run next
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]

