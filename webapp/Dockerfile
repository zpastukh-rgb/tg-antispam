# Контекст сборки — папка webapp (в Railway: Root Directory = webapp).
# RAILWAY_DOCKERFILE_PATH для ЭТОГО сервиса: только "Dockerfile" или удали переменную (см. webapp/railway.json).
# Неверно: webapp/Dockerfile.bot, Dockerfile.bot — это образ бота из корня репо, здесь их нет.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
RUN npm install -g serve@14
COPY --from=build /app/dist ./dist
EXPOSE 3000
CMD ["sh", "-c", "exec serve -s dist -l ${PORT:-3000}"]
