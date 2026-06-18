import sys, urllib.request
from pathlib import Path
import app as A
from ebooklib import epub, ITEM_COVER, ITEM_IMAGE

URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.gutenberg.org/ebooks/11.epub.images"
OWNER = sys.argv[2] if len(sys.argv) > 2 else "alice"
CAPTION = sys.argv[3] if len(sys.argv) > 3 else "Alice's Adventures in Wonderland — Lewis Carroll."
EPUB_PATH = Path("/tmp/_ingest.epub")

print(f"downloading {URL} …")
urllib.request.urlretrieve(URL, EPUB_PATH)
print(f"  {EPUB_PATH.stat().st_size} bytes")

con = A.sqlite3.connect(A.DB); con.row_factory = A.sqlite3.Row
con.execute("PRAGMA foreign_keys=ON")
row = con.execute("SELECT id FROM users WHERE username=?", (OWNER,)).fetchone()
if row is None: sys.exit(f"no such user: {OWNER!r} (run seed.py first)")
uid = row["id"]

with A.app.test_request_context():
    bid = con.execute("INSERT INTO books(owner_id,caption,status,visibility) VALUES(?,?,?,?)",
                      (uid, CAPTION, "published", "public")).lastrowid
    with open(EPUB_PATH, "rb") as f:
        chapters, _, _ = A.parse_epub(f, bid)

    book = epub.read_epub(str(EPUB_PATH))
    cover_url = None
    for it in book.get_items_of_type(ITEM_COVER):
        cover_url = A.save_pic(it.get_content(), "covers", 1200, f"b{bid}")
        if cover_url: break
    if not cover_url:
        for it in book.get_items_of_type(ITEM_IMAGE):
            if "cover" in (it.file_name or "").lower():
                cover_url = A.save_pic(it.get_content(), "covers", 1200, f"b{bid}")
                if cover_url: break
    if cover_url:
        con.execute("UPDATE books SET cover=? WHERE id=?", (cover_url, bid))

    idx = 0
    for ci, (title, paras) in enumerate(chapters):
        cid = con.execute("INSERT INTO chapters(book_id,idx,title) VALUES(?,?,?)",
                          (bid, ci, title)).lastrowid if (title or len(chapters) > 1) else None
        for p in paras:
            con.execute("INSERT INTO paragraphs(book_id,chapter_id,idx,html,plain) VALUES(?,?,?,?,?)",
                        (bid, cid, idx, p["html"], p["plain"]))
            idx += 1
    con.commit()
print(f"ingested book id={bid}, owner={OWNER}, paragraphs={idx}, cover={cover_url}")
