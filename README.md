# Bible and Beyond

Bible and Beyond is an open source, self-hosted Bible study website. Read and search public-domain Bibles, see the Hebrew and Greek behind the English, follow cross references, and read classic commentaries and devotionals, all from one verse. An AI-answered FAQ, notes and daily devotional emails are built in, and you choose where to host your site.

[See the live site](https://bible-and-beyond.com) · [Follow the installation guide](INSTALLATION.md) · [Report an issue](https://github.com/PaulCarrick/bible-and-beyond.com/issues)

## What you can do

Use Bible and Beyond to give a church, a study group, or your own readers a free place to read and study the Bible. Once the server is running, you manage it from the admin interface.

- Read a chapter at a time in the ASV, BSB, KJV, WEB and YLT, scrolling on from book to book.
- Search the Bible for words, phrases or a Strong's number, and search the NIV, NASB and The Message through API.Bible.
- Open any verse in context, in other translations, with its cross references and its original Hebrew or Greek words.
- Read and search six classic commentaries and four devotional books, and have a devotional emailed each day.
- Keep private notes on verses, commentaries and readings with a free account.
- Ask the FAQ: answers to 30 common questions, written by an AI from a Bible-centred point of view.

## Why use Bible and Beyond?

### 🚀 Free and open source

Use, inspect, and modify the software under the Apache License 2.0. The software is free. Hosting and domain registration costs depend on what you choose.

### 📖 Texts from trusted sources

The Bibles, commentaries and devotionals are public-domain works, and the original-language data and cross references come from STEP Bible and OpenBible.info with credit. Each source is credited on the site, and the sources that ask not to be redistributed are downloaded from their owners when your site first starts.

### 🔓 Choose where you host

Run Bible and Beyond on infrastructure you control. Two Docker containers hold the whole site, so you can move it to a new host with its database.

### 💰 Start with affordable hosting

You can run the site on a small cloud server. The live site runs on Amazon Lightsail with 2 GB of memory.

## Get started

Follow the [installation guide](INSTALLATION.md) to run Bible and Beyond with Docker. Once it's running, log in to the admin interface, check the site settings, and add the keys for the optional services (the AI answers, the licensed Bibles and the contact form's spam check).

## Live example

[Bible and Beyond](https://bible-and-beyond.com) runs this code. Browse it to see how reading, searching, commentaries and devotionals work together on a published site.

## For developers

Bible and Beyond uses React and TypeScript for the website, Python with FastAPI for the search and AI service, PostgreSQL with pgvector for the Bible data, and Drupal with MariaDB for the admin interface. Docker configurations are included for the web server and the database.

- [`frontend/`](frontend/) contains the website (React, TypeScript, Vite).
- [`ml-service/`](ml-service/) contains the API, the importers and the pytest test suite.
- [`drupal/`](drupal/) contains the admin interface, with its custom module in `web/modules/custom/bible_admin`.
- [`docker/`](docker/) contains the containers and their [full guide](docker/README.md).
- [`deploy/`](deploy/) contains the configuration of the live server.

## The texts and their licences

The Apache License covers this project's code. The texts and data it shows have their own terms, which the site states and credits:

- The Bibles (ASV, BSB, KJV, WEB, YLT), the six commentaries and the devotionals are in the public domain.
- The Hebrew and Greek words and lexicons are from [STEP Bible](https://www.stepbible.org) (CC BY 4.0), and the cross references from [OpenBible.info](https://www.openbible.info/labs/cross-references/) (CC BY 4.0).
- The NIV, NASB and The Message are fetched from [API.Bible](https://api.bible) for display only, under its terms, and are never stored.
- Drupal keeps its own licence, the GNU GPL (see [`drupal/LICENSE.txt`](drupal/LICENSE.txt)).

## Help and contributions

If you find a bug or have a feature idea, [open a GitHub issue](https://github.com/PaulCarrick/bible-and-beyond.com/issues). For a bug report, include how you installed it and the steps to reproduce the problem.

Pull requests are welcome. For a larger change, start with an issue so we can discuss the approach.

## License

Bible and Beyond is available under the [Apache License 2.0](LICENSE).
