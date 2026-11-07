# The database container: PostgreSQL 17 with pgvector (the Bible database the public site uses) and
# MariaDB 11.8 (Drupal's database), the same versions as the server (Debian 13).
#
# The Bible data is built in (docker/public-data/bible-data.sql.gz, made by docker/make-public-data.sh:
# the Bibles, commentaries, devotionals, cross references, original words and lexicon, with no visitor
# data) and loaded into the volume on the first start. MariaDB starts empty; the web container installs
# Drupal into it.
FROM pgvector/pgvector:pg17-trixie

RUN apt-get update \
  && apt-get install -y --no-install-recommends mariadb-server gzip \
  && rm -rf /var/lib/apt/lists/* \
  && rm -rf /var/lib/mysql/* \
  && mkdir -p /run/mysqld \
  && chown mysql:mysql /run/mysqld /var/lib/mysql

COPY docker/public-data/bible-data.sql.gz /bible-data/bible-data.sql.gz
COPY docker/database/entrypoint.sh /usr/local/bin/stack-database-entrypoint.sh
COPY docker/database/load-bible-data.sh /docker-entrypoint-initdb.d/10-load-bible-data.sh

# Both databases are ready when both answer. PostgreSQL is asked over TCP: while the first start loads
# the data it listens only on its socket, so the web container waits until the loading is done.
HEALTHCHECK --interval=10s --timeout=5s --start-period=900s --retries=6 \
  CMD pg_isready -h 127.0.0.1 -U "${POSTGRES_USER:-bibleandbeyond}" -d "${POSTGRES_DB:-bibleandbeyond}" -q \
    && mariadb-admin --socket=/run/mysqld/mysqld.sock ping --silent

EXPOSE 5432 3306
ENTRYPOINT ["/usr/local/bin/stack-database-entrypoint.sh"]
CMD ["postgres"]
