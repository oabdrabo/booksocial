import app as A

for p in (A.DB, A.Path(f"{A.DB}-wal"), A.Path(f"{A.DB}-shm")):
    if p.exists(): p.unlink()
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
    A.write_chapters(con, bid, A.parse_markdown(body))

ab = con.execute("SELECT id FROM books WHERE owner_id=?", (uid("alice"),)).fetchone()["id"]
bb = con.execute("SELECT id FROM books WHERE owner_id=?", (uid("bob"),)).fetchone()["id"]
for u, b in [("demo", ab), ("bob", ab)]:
    con.execute("INSERT INTO likes(user_id,book_id) VALUES(?,?)", (uid(u), b))
con.execute("INSERT INTO saves(user_id,book_id) VALUES(?,?)", (uid("demo"), bb))
for u, msg in [("demo", "lovely opening."), ("bob", "such a calm pace.")]:
    con.execute("INSERT INTO comments(user_id,book_id,body) VALUES(?,?,?)", (uid(u), ab, msg))
con.commit(); con.close()
print("seeded.")
