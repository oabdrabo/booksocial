from pathlib import Path
import app as A

DB_PATH = Path(__file__).parent / "books.db"
if DB_PATH.exists(): DB_PATH.unlink()
A.init_db()
con = A.sqlite3.connect(A.DB); con.row_factory = A.sqlite3.Row
con.execute("PRAGMA foreign_keys=ON")

for u, dn, bio in [("demo","Demo","Just exploring."),
                   ("alice","Alice Aurora","Reading and writing in equal measure."),
                   ("bob","Bob Bay","Translator of strange texts.")]:
    con.execute("INSERT INTO users(username,email,display_name,bio) VALUES(?,?,?,?)",
                (u, f"{u}@example.com", dn, bio))
con.commit()
uid = lambda n: con.execute("SELECT id FROM users WHERE username=?", (n,)).fetchone()["id"]

for a, b in [("demo","alice"),("demo","bob"),("alice","bob")]:
    con.execute("INSERT INTO follows(follower_id,followee_id) VALUES(?,?)", (uid(a), uid(b)))

POSTS = [
    ("alice", "a small book about leaves and waiting.",
     "# The Quiet Garden\n\nIt was the kind of morning where every leaf held a drop of light.\n\n"
     "The bees worked the lavender. A cat watched her from beneath the rose bush.\n\n"
     "## Threshold\n\nInside, the kettle was already whistling. \"Drink first,\" her grandmother said.\n\nMara drank.\n"),
    ("bob", "fragments and rumors.",
     "# Notes Toward a Map of the Unfindable\n\nEvery city has one door no one notices.\n\n"
     "The door is not locked. The door is not open. It is simply waiting.\n"),
]
for user, caption, body in POSTS:
    bid = con.execute("INSERT INTO books(owner_id,caption,status,visibility) VALUES(?,?,?,?)",
                      (uid(user), caption, "published", "public")).lastrowid
    chapters = A.parse_markdown(body)
    idx = 0
    for ci, (title, paras) in enumerate(chapters):
        cid = con.execute("INSERT INTO chapters(book_id,idx,title) VALUES(?,?,?)",
                          (bid, ci, title)).lastrowid if (title or len(chapters) > 1) else None
        for p in paras:
            con.execute("INSERT INTO paragraphs(book_id,chapter_id,idx,html,plain) VALUES(?,?,?,?,?)",
                        (bid, cid, idx, p["html"], p["plain"]))
            idx += 1

ab = con.execute("SELECT id FROM books WHERE owner_id=?", (uid("alice"),)).fetchone()["id"]
bb = con.execute("SELECT id FROM books WHERE owner_id=?", (uid("bob"),)).fetchone()["id"]
for u, b in [("demo", ab), ("bob", ab)]:
    con.execute("INSERT INTO likes(user_id,book_id) VALUES(?,?)", (uid(u), b))
con.execute("INSERT INTO saves(user_id,book_id) VALUES(?,?)", (uid("demo"), bb))
for u, msg in [("demo", "lovely opening."), ("bob", "such a calm pace.")]:
    con.execute("INSERT INTO comments(user_id,book_id,body) VALUES(?,?,?)", (uid(u), ab, msg))
con.commit(); con.close()
print("seeded.")
