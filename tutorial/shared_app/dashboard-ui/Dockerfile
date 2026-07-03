# Stage 1: Build the React application (native arch — esbuild crashes under QEMU)
FROM --platform=$BUILDPLATFORM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve with nginx (target arch — runs on OpenShift)
FROM nginx:1.25-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

# Fix permissions for OpenShift (arbitrary UID / non-root)
RUN chown -R 1001:0 /var/cache/nginx /var/run /usr/share/nginx/html && \
    chmod -R g=u /var/cache/nginx /var/run /usr/share/nginx/html && \
    touch /var/run/nginx.pid && \
    chown 1001:0 /var/run/nginx.pid && \
    chmod g=u /var/run/nginx.pid

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

USER 1001

CMD ["nginx", "-g", "daemon off;"]
