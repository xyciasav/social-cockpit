FROM node:22-alpine AS build
ARG APP_VERSION=0.4.0
ENV APP_VERSION=$APP_VERSION
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY . .
RUN npm run build

FROM node:22-alpine AS runtime
ARG APP_VERSION=0.4.0
WORKDIR /app
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000 APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.title="Social Cockpit" \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.source="https://github.com/xyciasav/social-cockpit"
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/drizzle ./drizzle
RUN mkdir -p /app/.wrangler && chown -R node:node /app
EXPOSE 3000
USER node
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
