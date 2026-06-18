<div align="center">

<picture>
  <source media="(prefers-color-scheme: light)" srcset="assets/banner-light.png" />
  <img src="assets/banner-dark.png" alt="booksocial — Instagram, shaped for reading" width="880" />
</picture>

Upload an EPUB and it becomes a post: a cover, a caption, and the book itself — parsed into chapters and paragraphs you can read right in the feed. Then the social layer kicks in: follow people, like and save, highlight passages, leave notes, start book clubs, and DM. A small, self-hosted Flask app.

![License: MIT](https://img.shields.io/badge/License-MIT-3da639.svg?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-000?logo=flask&logoColor=fff&style=flat-square)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff&style=flat-square)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=fff&style=flat-square)

[Overview](#overview) · [Screenshots](#screenshots) · [Features](#features) · [Architecture](#architecture) · [Stack](#tech-stack) · [Install](#installation) · [Usage](#usage) · [Config](#configuration) · [Develop](#development) · [Contributing](#contributing) · [License](#license) · [Support](#support)

</div>

---

## Screenshots

<table>
<tr>
<td width="33%"><img src="assets/screens/feed.webp" alt="Feed with continue-reading and book posts" /></td>
<td width="33%"><img src="assets/screens/reader.webp" alt="In-app reader with chapters and inline images" /></td>
<td width="33%"><img src="assets/screens/profile.webp" alt="Profile bookshelf with stats" /></td>
</tr>
<tr>
<td align="center"><b>Feed</b><br/>continue-reading, covers, likes, reposts</td>
<td align="center"><b>Reader</b><br/>chapters, progress, inline images</td>
<td align="center"><b>Profile</b><br/>your bookshelf, with generated covers</td>
</tr>
<tr>
<td><img src="assets/screens/search.webp" alt="Discover — people, popular books, tags" /></td>
<td><img src="assets/screens/search-results.webp" alt="Full-text search across book paragraphs" /></td>
<td><img src="assets/screens/club.webp" alt="Book club group chat" /></td>
</tr>
<tr>
<td align="center"><b>Discover</b><br/>people, popular, #tags</td>
<td align="center"><b>Full-text search</b><br/>matches inside the books</td>
<td align="center"><b>Book clubs</b><br/>group chat around a read</td>
</tr>
<tr>
<td><img src="assets/screens/dm.webp" alt="Direct message conversation" /></td>
<td><img src="assets/screens/notifications.webp" alt="Activity inbox" /></td>
<td><img src="assets/screens/settings.webp" alt="Profile and privacy settings" /></td>
</tr>
<tr>
<td align="center"><b>Direct messages</b><br/>block-aware DMs</td>
<td align="center"><b>Notifications</b><br/>likes, comments, replies, mentions</td>
<td align="center"><b>Settings</b><br/>profile, bio, private account</td>
</tr>
</table>

## Overview

Reading apps are libraries; social apps are feeds. booksocial puts them together — your bookshelf *is* your profile, and reading is something you do with people. Drop in an EPUB; it's ingested into clean, sanitized HTML paragraphs (cover extracted, images localized) and posted to your feed for others to read, react to, and discuss.

## Features

- **EPUB → readable post** — `ebooklib` parses chapters and paragraphs; HTML is sanitized with `bleach`, covers and images extracted, localized, and resized with Pillow. Markdown and plain text work too.
- **A real feed** — books from people you follow, with captions, covers, likes, saves, comments, reposts, and quotes.
- **In-app reader** — chapter table of contents, paragraph-level rendering, and reading progress that powers a *continue reading* shelf.
- **Highlights & notes** — mark passages and keep private notes, scoped per book.
- **Full-text search & discover** — SQLite FTS5 searches *inside* the books (highlighted snippets), alongside people, popular books, and `#hashtags`.
- **Generated covers** — books without artwork get a deterministic gradient-and-title cover; missing images degrade gracefully instead of breaking.
- **Social graph & privacy** — follows, profiles, reposts/quotes, private accounts (followers-only), and blocks honored across feeds, search, DMs, and clubs.
- **Book clubs** — shared discussion spaces around a read, scoped to who can see the book.
- **DMs & notifications** — direct messages (block-aware) and an activity inbox for likes, comments, replies, and mentions.
- **Lossless editing** — your original Markdown is preserved, so editing a post never degrades its formatting.

## Architecture

```
upload .epub ─▶ ebooklib parse ─▶ sanitize (bleach) + extract cover/images (Pillow)
            ─▶ chapters + paragraphs in SQLite ─▶ rendered in the feed & reader
```

Data model centers on `users`, `books` (with `chapters` and `paragraphs`), and the social tables (`follows`, `likes`, `saves`, `comments`, `highlights`, `notes`, `reading_progress`). Auth is delegated to a reverse proxy: the app trusts `Remote-User` / `Remote-Email` headers, so it sits cleanly behind a homelab SSO.

## Tech stack

| Layer | Choice |
|---|---|
| Server | Flask |
| Database | SQLite (WAL, foreign keys) |
| EPUB | ebooklib + BeautifulSoup |
| Sanitizing | bleach |
| Images | Pillow |

## Installation

```sh
pip install -r requirements.txt
python seed.py        # initialize the schema (+ demo data)
```

## Usage

```sh
DEV_MODE=1 flask --app app run
# open http://localhost:5000/?as=demo   (DEV_MODE picks the user from ?as=)
```

Upload an EPUB to create a post, then browse the feed, open the reader, highlight passages, follow other readers, and join clubs.

## Configuration

| Var | Default | Purpose |
|---|---|---|
| `DB_PATH` | `./books.db` | SQLite database file |
| `UPLOADS_DIR` | `./uploads` | Stored covers + extracted images |
| `DEV_MODE` | `1` | Local auth shortcut — picks the user from `?as=` / cookie |
| `Remote-User` / `Remote-Email` | – | Identity headers set by your reverse proxy in production |

## Development

In production, put booksocial behind a proxy that sets `Remote-User` and point `DB_PATH` / `UPLOADS_DIR` at persistent storage. Max upload size is 64 MB; uploaded HTML is always sanitized through the single `bleach` allow-list.

## FAQ

**What can I upload?**
EPUB files — `ebooklib` parses them into chapters and paragraphs, extracts the cover, and localizes images.

**How does login work?**
Identity comes from reverse-proxy headers (`Remote-User` / `Remote-Email`); locally, `DEV_MODE` picks the user from `?as=`.

**Is uploaded content sanitized?**
Yes — all HTML passes through a single `bleach` allow-list before it's stored or rendered.

## Contributing

Contributions are welcome — please read the [AI Contribution Policy](https://github.com/oabdrabo/.github/blob/main/AI_POLICY.md) first. Keep pull requests focused on a single concern, follow the existing conventions, and tests are very welcome.

## License

[MIT](LICENSE) © 2026 Omar Abdrabo

## Support

Free and open-source. If it's useful, you can support development — pay what you like, once or monthly:

[![Donate once](https://img.shields.io/badge/☕%20Donate%20once-pay%20what%20you%20like-635bff?logo=stripe&logoColor=white&style=flat-square)](https://donate.stripe.com/3cI6oI7Gh1PG0eV8MJ5kk00)
[![Sponsor monthly](https://img.shields.io/badge/💜%20Sponsor%20monthly-recurring-56c4e6?logo=stripe&logoColor=white&style=flat-square)](https://buy.stripe.com/00wbJ2f8J51S9Pv1kh5kk01)
