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

    idx = A.write_chapters(con, bid, chapters)
    con.commit()
print(f"ingested book id={bid}, owner={OWNER}, paragraphs={idx}, cover={cover_url}")
