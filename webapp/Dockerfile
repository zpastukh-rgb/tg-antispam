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
# URL API может быть только в рантайме: serve-static.mjs отдаёт /guard-api-config.js из process.env.
RUN npm run build

FROM node:20-alpine AS run
WORKDIR /app
COPY --from=build /app/dist ./dist
COPY serve-static.mjs ./serve-static.mjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=15s --start-period=40s --retries=5 \
  CMD node -e "require('http').get('http://127.0.0.1:'+(process.env.PORT||3000)+'/',(r)=>{r.resume();r.on('end',()=>process.exit(r.statusCode>=200&&r.statusCode<500?0:1))}).on('error',()=>process.exit(1))"
CMD ["node", "serve-static.mjs"]
