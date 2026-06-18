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

### 📖 Reading & writing

- **EPUB → readable post** — `ebooklib` splits a book into chapters and paragraphs; the cover is extracted, embedded images are localized and resized to WebP with Pillow, and all HTML is run through a single `bleach` allow-list before it's ever stored or shown.
- **Write your own** — post in **Markdown** (or `.md`/`.txt` upload): the first heading becomes the caption, headings split chapters, and the first image becomes the cover.
- **In-app reader** — paragraph-by-paragraph rendering in a serif reading view, a **chapter table of contents**, and **reading progress** that's saved as you scroll.
- **Continue reading** — a shelf on your home feed that picks up every book exactly where you left off, with a progress bar per cover.
- **Highlights & notes** — mark any passage, and attach **private** notes to individual paragraphs, scoped per book.
- **Lossless editing** — your original Markdown source is preserved, so re-editing a post never degrades its formatting.

### 💬 Social

- **A real feed** — books from people you follow (plus your own), newest first; a separate **Explore** tab surfaces everything public.
- **React & discuss** — **like**, **save/bookmark**, and **comment** with threaded replies, `@mentions`, and `#hashtags`.
- **Reposts & quotes** — reshare a book to your followers, optionally with a quote of your own.
- **Follows & profiles** — every profile is a **bookshelf grid** with stats: posts, followers, following, paragraphs read, and a **reading streak**.
- **Book clubs** — create a shared space around any book and chat with members in real time (join / leave / delete).
- **Direct messages** — 1:1 conversations with read receipts, **block-aware**, with unread badges.
- **Notifications** — an activity inbox for likes, comments, replies, and mentions, with unread indicators in the top bar.

### 🔎 Discovery

- **Full-text search** — SQLite **FTS5** searches *inside* the books themselves and returns highlighted snippets, alongside matching captions and people.
- **Discover** — when the search box is empty: popular books, people to follow, and a **`#tag` cloud**.
- **Hashtags** — `#tags` written in captions are indexed automatically and get their own tag pages.

### 🔒 Privacy & control

- **Private accounts** — followers-only visibility, enforced across feeds, search, reposts, DMs, and clubs.
- **Blocks** — block someone and they vanish from your feeds and search and can't message or interact with you.
- **Settings** — edit display name, bio, and avatar, and toggle a private account.

### 🛠️ Built for self-hosting

- **Generated covers** — books without artwork get a deterministic gradient-and-title cover, and any missing image degrades gracefully instead of showing a broken icon.
- **Proxy auth** — trusts `Remote-User` / `Remote-Email` identity headers, so it drops cleanly behind a reverse-proxy SSO; a `DEV_MODE` shortcut picks the user from `?as=` locally.
- **Small & single-process** — Flask + SQLite (WAL, foreign keys, FTS5), an HTMX, mobile-first UI with native-feeling bottom sheets, and a 64 MB upload cap.

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
