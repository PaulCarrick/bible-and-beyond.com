# Bible and Beyond in two containers

Run your own copy of Bible and Beyond, a free, non-commercial Bible study site: public-domain Bibles,
the Hebrew and Greek behind the English (Strong's numbers and a lexicon), cross references, six classic
commentaries, four devotional books with daily emails, eleven other classic books, notes for visitors with accounts, and an
AI-answered FAQ.

- **web**: nginx serving the public site (port 80 in the container) and the Drupal admin (port 8081),
  with the Python service behind the site's `/api/` and the daily devotional emails.
- **database**: PostgreSQL 17 with pgvector (the Bible data and the visitors' accounts and notes) and
  MariaDB (Drupal's database). It is on an internal network that only the web container shares: it
  opens no port, nothing else can reach it, and it has no route to the internet.

**Where the data comes from.** Built into the database image, as loaded in the database: the
public-domain Bibles (ASV, BSB, KJV, WEB, YLT), the public-domain commentaries, the cross references
(OpenBible.info, CC BY 4.0, credited on the site) and the Berean Bible's word links (public domain).
**Fetched from their owners on the first start**, because they ask that their files not be redistributed:
the Hebrew and Greek words and the lexicons (STEPBible, CC BY 4.0, from its GitHub repository) and the
four devotionals (two from the Christian Classics Ethereal Library, two from Project Gutenberg) and the
eleven other books (Project Gutenberg). No source
data file is in the images, and no visitor data from the original site is included.

## Install on a server

You need Docker with the Compose plugin, about 3 GB of disk and 2 GB of memory.

```bash
git clone https://github.com/PaulCarrick/bible-and-beyond.com.git
cd bible-and-beyond.com
cp docker/.env.example docker/.env
```

Edit `docker/.env` (it is commented): at least the two database passwords, `ADMIN_EMAIL`,
`ADMIN_PASSWORD` and `SITE_URL`. Then:

```bash
docker compose -f docker/compose.yml up -d
docker compose -f docker/compose.yml logs -f web     # watch the first start; Ctrl+C to stop watching
```

The first start loads the built-in data (about a minute), sets up the admin, and then, while the site
is already running, downloads and loads the STEPBible data, the devotionals and the other books (a few minutes, about
130 MB; the server needs to reach github.com, ccel.org and gutenberg.org). Until they are loaded the
devotionals and other books do not appear and the Original Words windows say there is nothing to show. If a download
fails, the next start tries again (`docker compose -f docker/compose.yml restart web`). Then:

- the public site is on `http://your-server/` (`SITE_PORT`, 80);
- the admin is on `http://your-server:8081/` (`ADMIN_PORT`). Log in with `ADMIN_USERNAME` and
  `ADMIN_PASSWORD`. If you left the password empty, a random one was made and shown once in the log of
  the first start.

`docker compose pull` downloads the published images; `up -d --build` builds them from this repository
instead (building the database image needs `docker/public-data/bible-data.sql.gz`, which only the
maintainer can make, with `docker/make-public-data.sh`).

## HTTPS and host names

The containers speak plain HTTP. On a public server put a proxy that handles HTTPS in front of them,
for example Caddy (it gets certificates by itself):

```
bible.example.org {
  reverse_proxy localhost:80
}
admin.bible.example.org {
  reverse_proxy localhost:8081
}
```

Then set `SITE_URL=https://bible.example.org` and `DRUPAL_TRUSTED_HOSTS=^admin\.bible\.example\.org$` in
`docker/.env`, and `docker compose -f docker/compose.yml up -d` again. With a proxy in front, you can set
`SITE_PORT` and `ADMIN_PORT` to ports the proxy reaches but the internet does not (or close them in the
firewall). The site's rate limits see each visitor's own address through a proxy on the same machine or
a private network.

## Secrets and keys

`docker/.env` holds every password and key: keep it private (`chmod 600 docker/.env`), never commit it.

- **Database passwords** (`POSTGRES_PASSWORD`, `DRUPAL_DATABASE_PASSWORD`): set on the first start.
  To change them later, change them inside the databases too.
- **The administrator** (`ADMIN_*`): used only on the first start. Change the password later in the
  admin (My account, Edit).
- **Email** (`SMTP_*`, `MAIL_FROM`, `CONTACT_EMAIL_TO`): for the contact form, the account emails
  (confirming an address, resetting a password) and the daily devotionals. Saved on the first start;
  later on the admin's **Site settings** screen. Without them no email is sent.
- **Outside services**, each optional and each with its own account and terms:
  - `GEMINI_API_KEY`: Google Gemini writes the FAQ answers (https://aistudio.google.com/apikey).
    Without it the FAQ lists its questions but says the answers are not available.
  - `API_BIBLE_KEY`: API.Bible, for searching the NIV, NASB and The Message
    (https://scripture.api.bible; the free plan is for non-commercial use, 5,000 requests a month).
    Without it those three Bibles cannot be searched.
  - `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY`: Google reCAPTCHA v3 for the contact form
    (https://www.google.com/recaptcha/admin; add your host name to the key). Without them the contact
    form says it is unavailable.

  They can also be typed on the admin's **Site settings** screen (in password fields that never show a
  saved key). Once that screen is saved, its values are used instead of `docker/.env`.

## Running it

```bash
docker compose -f docker/compose.yml ps                 # are both running and healthy?
docker compose -f docker/compose.yml logs web           # the site, the admin and the emails
docker compose -f docker/compose.yml stop               # keeps all data
docker compose -f docker/compose.yml start
docker compose -f docker/compose.yml pull && docker compose -f docker/compose.yml up -d    # update
docker compose -f docker/compose.yml down -v            # removes everything, data included
```

**People who run the website** do not need all of Drupal. In the admin, go to People, Add user, and give them
the **Website administrator** role: they see only the website's pages (Bibles, Commentaries, Devotionals, Other books, Site settings,
Site users).
Keep the first administrator for Drupal itself.

A one-time admin login link, if the password is lost:

```bash
docker compose -f docker/compose.yml exec -u site web /app/drupal/vendor/bin/drush user:login --uri=http://your-server:8081
```

All data lives in Docker volumes (`postgres_data` holds the visitors' accounts and notes). Back it up
with, for example:

```bash
docker compose -f docker/compose.yml exec database pg_dump -U bibleandbeyond bibleandbeyond | gzip > bible-and-beyond.sql.gz
docker compose -f docker/compose.yml exec database mariadb-dump --socket=/run/mysqld/mysqld.sock bibleandbeyond_drupal | gzip > drupal.sql.gz
```

## For the maintainer: publishing the images

`docker/make-public-data.sh` makes `docker/public-data/bible-data.sql.gz` from the live database, on
the server, without the rows of any visitor table (it checks), and `docker/publish.sh` builds both images
for amd64 and arm64 servers and pushes them to the registry in `IMAGE_REGISTRY` (log in first:
`docker login ghcr.io`). The images are public once pushed.
