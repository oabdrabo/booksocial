<div align="center">

# 📚 booksocial

### Instagram, shaped for reading.

Upload an EPUB and it becomes a post: a cover, a caption, and the book itself — parsed into chapters and paragraphs you can read right in the feed. Then the social layer kicks in: follow people, like and save, highlight passages, leave notes, start book clubs, and DM. A small, self-hosted Flask app.

![Flask](https://img.shields.io/badge/Flask-000?logo=flask&logoColor=fff)
![Python](https://img.shields.io/badge/Python-3776AB?logo=python&logoColor=fff)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=fff)
![EPUB](https://img.shields.io/badge/EPUB-e11d6b)

</div>

---

## The idea

Reading apps are libraries; social apps are feeds. booksocial puts them together — your bookshelf *is* your profile, and reading is something you do with people. Drop in an EPUB; it's ingested into clean, sanitized HTML paragraphs (cover extracted, images localized), and posted to your feed for others to read, react to, and discuss.

## Features

- **EPUB → readable post** — `ebooklib` parses chapters and paragraphs; HTML is sanitized with `bleach`, covers and images are extracted and resized with Pillow.
- **A real feed** — books from people you follow, with captions, covers, likes, saves, and comments.
- **In-app reader** — chapter table of contents, paragraph-level rendering, reading progress.
- **Highlights & notes** — mark passages and keep private notes, scoped per book.
- **Social graph** — follows, profiles, reposts, quotes.
- **Book clubs** — shared spaces around a read.
- **DMs & notifications** — direct messages and an activity inbox.

## How it works

```
upload .epub ─▶ ebooklib parse ─▶ sanitize (bleach) + extract cover/images (Pillow)
            ─▶ chapters + paragraphs in SQLite ─▶ rendered in the feed & reader
```

Auth is delegated to a reverse proxy: the app trusts `Remote-User` / `Remote-Email` headers (so it sits cleanly behind a homelab SSO), with a `DEV_MODE` fallback for local work.

## Stack

| Layer | Choice |
|---|---|
| Server | Flask |
| Database | SQLite (WAL, foreign keys) |
| EPUB | ebooklib + BeautifulSoup |
| Sanitizing | bleach |
| Images | Pillow |

## Run it

```sh
pip install -r requirements.txt
python seed.py            # initialize the schema (+ demo data)
DEV_MODE=1 flask --app app run
# open http://localhost:5000/?as=demo   (DEV_MODE picks the user from ?as=)
```

In production, put it behind a proxy that sets `Remote-User`, and point `DB_PATH` / `UPLOADS_DIR` at persistent storage.

## 💖 Support

Free and open-source. If it's useful, you can support development — pay what you like, once or monthly:

[![Donate once](https://img.shields.io/badge/☕%20Donate%20once-pay%20what%20you%20like-635bff?logo=stripe&logoColor=white)](https://donate.stripe.com/3cI6oI7Gh1PG0eV8MJ5kk00)
[![Sponsor monthly](https://img.shields.io/badge/💜%20Sponsor%20monthly-recurring-56c4e6?logo=stripe&logoColor=white)](https://buy.stripe.com/00wbJ2f8J51S9Pv1kh5kk01)

<div align="center"><sub>Built by <a href="https://github.com/oabdrabo">@oabdrabo</a></sub></div>
