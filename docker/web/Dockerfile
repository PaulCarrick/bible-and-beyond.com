# The web container: nginx serving the public site (the built pages, with /api/ passed to the Python
# service) on port 80 and the Drupal admin (PHP-FPM) on port 8081, on Debian 13 like the server
# (PHP 8.4, Python 3.13). Build from the repository root: see docker/compose.yml and docker/README.md.
# No key, password or data file is put in the image (.dockerignore); they come in when it starts, and the
# first start installs Drupal (entrypoint.sh).

# 1. The public site's pages, built the way deploy.sh builds them on the server.
FROM node:24-trixie-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN VITE_ML_SERVICE_URL=/api npm run build

# 2. Drupal's PHP packages (core, drush), from the committed composer.lock.
FROM composer:2 AS drupal
WORKDIR /build/drupal
COPY drupal/ ./
RUN composer install --no-dev --no-interaction --no-progress --optimize-autoloader --ignore-platform-reqs

# 3. The running container.
FROM debian:trixie-slim
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    nginx supervisor ca-certificates curl gzip \
    php8.4-fpm php8.4-cli php8.4-mysql php8.4-gd php8.4-intl php8.4-mbstring php8.4-xml php8.4-curl \
    php8.4-zip php8.4-apcu php8.4-opcache \
    python3 python3-venv \
    postgresql-client-17 mariadb-client \
  && rm -rf /var/lib/apt/lists/* \
  && rm -f /etc/nginx/sites-enabled/default /etc/php/8.4/fpm/pool.d/www.conf \
  && useradd --uid 1000 --create-home --shell /bin/bash site

WORKDIR /app

# The Python service and its packages (requirements.txt first, so a code change does not reinstall them).
COPY ml-service/requirements.txt ml-service/requirements.txt
RUN python3 -m venv ml-service/.venv \
  && ml-service/.venv/bin/pip install --no-cache-dir --quiet -r ml-service/requirements.txt
COPY ml-service/ ml-service/

COPY --from=drupal /build/drupal drupal/
COPY --from=frontend /build/frontend/dist frontend/dist/

COPY docker/web/nginx.conf /etc/nginx/conf.d/stack.conf
COPY docker/web/php-fpm.conf /etc/php/8.4/fpm/pool.d/stack.conf
COPY docker/web/supervisord.conf /etc/supervisor/stack.conf
COPY docker/web/settings.local.php drupal/web/sites/default/settings.local.php
COPY docker/web/entrypoint.sh /usr/local/bin/stack-web-entrypoint.sh
COPY docker/web/setup/ /app/docker-setup/

# The code is readable by everyone (PHP-FPM and the Python service run as "site"), whatever the
# permissions of the copy it was built from; none of it is secret (the keys come in when it starts).
RUN chmod -R a+rX /app/drupal /app/ml-service /app/frontend /app/docker-setup

# Places that change while the site runs (volumes in compose.yml), owned by the user the site runs as.
RUN mkdir -p drupal/web/sites/default/files /app/drupal-private /app/drupal-config ml-service/data /run/php \
  && chown -R site:site drupal/web/sites/default/files /app/drupal-private /app/drupal-config ml-service/data

EXPOSE 80 8081
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS http://127.0.0.1/api/health > /dev/null && curl -fsS -o /dev/null http://127.0.0.1:8081/user/login
ENTRYPOINT ["/usr/local/bin/stack-web-entrypoint.sh"]
