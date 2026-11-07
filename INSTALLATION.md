# Installing Bible and Beyond

Bible and Beyond runs in two Docker containers: one for the web server and one for the databases. This page is the short version; the [full guide](docker/README.md) covers HTTPS, the keys, backups and updates.

## What you need

- A server or computer with Docker and the Docker Compose plugin.
- About 3 GB of disk and 2 GB of memory.
- An internet connection on the first start, to download the texts whose owners ask not to be redistributed.

## Install

```bash
git clone https://github.com/PaulCarrick/bible-and-beyond.com.git
cd bible-and-beyond.com
cp docker/.env.example docker/.env
```

Edit `docker/.env`. At least set the two database passwords, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `SITE_URL`. Every setting is explained in the file.

```bash
docker compose -f docker/compose.yml up -d
docker compose -f docker/compose.yml logs -f web
```

The first start loads the Bible data, sets up the admin, and then downloads the original-language data and the devotionals from their owners. It takes a few minutes.

## Open the site

- The website is on port 80 of your server (`SITE_PORT`).
- The admin interface is on port 8081 (`ADMIN_PORT`). Log in with `ADMIN_USERNAME` and `ADMIN_PASSWORD`.

On a public server, put a proxy that handles HTTPS in front of both. The [full guide](docker/README.md#https-and-host-names) shows how with Caddy.

## Optional services

Each needs its own account. Add its keys to `docker/.env` or on the admin's **Site settings** screen:

- **Google Gemini** writes the FAQ answers.
- **API.Bible** lets visitors search the NIV, NASB and The Message.
- **Google reCAPTCHA** protects the contact form.
- **An email server** sends contact messages, account emails and the daily devotionals.

The site works without them. Each part that needs one says it is not available.
