import io, os, re, secrets, sqlite3, tempfile
from pathlib import Path

import bleach
import markdown as md
from bs4 import BeautifulSoup
from PIL import Image
from ebooklib import epub, ITEM_DOCUMENT, ITEM_IMAGE, ITEM_COVER
from flask import Flask, abort, g, redirect, render_template, request, send_from_directory, url_for

BASE = Path(__file__).parent.resolve()
DB = Path(os.environ.get("DB_PATH") or (BASE / "books.db"))
UPROOT = Path(os.environ.get("UPLOADS_DIR") or (BASE / "uploads"))
UP = {"covers": UPROOT / "covers", "images": UPROOT / "images"}
DEV = os.environ.get("DEV_MODE", "1") == "1"
TAGS = "p br strong em b i u blockquote pre code h1 h2 h3 h4 h5 h6 ul ol li a img hr span".split()
ATTRS = {"a": ["href", "title", "rel"], "img": ["src", "alt", "title", "loading"]}
BLOCKS = {"p","h1","h2","h3","h4","h5","h6","blockquote","pre","ul","ol","figure"}
PALETTE = [("#1e293b","#475569"),("#3f3f46","#6b7280"),("#44403c","#78716c"),("#365314","#4d7c0f"),
           ("#7c2d12","#9a3412"),("#581c87","#7e22ce"),("#0c4a6e","#0369a1"),("#831843","#be185d"),
           ("#713f12","#a16207"),("#134e4a","#0f766e")]
FEED = "b.*, u.username AS owner_username, u.display_name AS owner_display, u.avatar AS owner_avatar, (SELECT COUNT(*) FROM paragraphs WHERE book_id=b.id) AS para_count"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def _close(_):
    c = g.pop("db", None)
    if c: c.close()

def _migrate():
    if not DB.exists(): return
    c = sqlite3.connect(DB)
    if "source_md" not in {r[1] for r in c.execute("PRAGMA table_info(books)")}:
        c.execute("ALTER TABLE books ADD COLUMN source_md TEXT"); c.commit()
    c.close()

def init_db():
    for p in UP.values(): p.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB); c.executescript((BASE / "schema.sql").read_text())
    c.commit(); c.close()

_migrate()

@app.before_request
def _load_user():
    h = request.headers
    name = h.get("Remote-User")
    if not name and DEV:
        name = request.args.get("as") or request.cookies.get("dev_as") or "demo"
    g.user = None
    if not name: return
    row = db().execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
    if row is None:
        cur = db().execute("INSERT INTO users(username,email,display_name) VALUES(?,?,?)",
                           (name, h.get("Remote-Email") or f"{name}@example.com", h.get("Remote-Name") or name))
        db().commit()
        row = db().execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    g.user = row

@app.after_request
def _persist_dev(resp):
    if DEV and (q := request.args.get("as")):
        resp.set_cookie("dev_as", q, max_age=86400, samesite="Lax")
    return resp

def need():
    if not g.user: abort(401)
    return g.user

@app.template_filter("min")
def min_filter(v, m): return min(v, m)

@app.template_filter("title_part")
def title_part(caption):
    if not caption: return ""
    s = str(caption).strip().rstrip(".")
    for sep in (" — ", " – ", " - "):
        if sep in s: return s.split(sep, 1)[0].strip()
    return s

@app.template_filter("author_part")
def author_part(caption):
    if not caption: return ""
    s = str(caption).strip().rstrip(".")
    for sep in (" — ", " – ", " - "):
        if sep in s: return s.split(sep, 1)[1].strip()
    return ""

@app.template_filter("ago")
def ago_filter(ts):
    if not ts: return ""
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(str(ts).replace("Z","")).replace(tzinfo=timezone.utc)
        s = int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception: return ""
    if s < 60: return "now"
    if s < 3600: return f"{s//60}m"
    if s < 86400: return f"{s//3600}h"
    if s < 604800: return f"{s//86400}d"
    if s < 2592000: return f"{s//604800}w"
    return f"{s//2592000}mo"

@app.template_filter("mentions")
def mentions_filter(text):
    from markupsafe import Markup, escape
    out = []
    last = 0
    for m in re.finditer(r"(@|#)([a-zA-Z0-9_]+)", text or ""):
        out.append(escape(text[last:m.start()]))
        sigil, name = m.group(1), m.group(2)
        if sigil == "@":
            out.append(Markup(f'<a href="/u/{name}">@{name}</a>'))
        else:
            out.append(Markup(f'<a href="/tag/{name.lower()}">#{name}</a>'))
        last = m.end()
    out.append(escape(text[last:]))
    return Markup("".join(str(x) for x in out))

@app.delete("/comments/<int:cid>")
def delete_comment(cid):
    u = need()
    c = db().execute("SELECT * FROM comments WHERE id=?", (cid,)).fetchone()
    if not c or c["user_id"] != u["id"]: abort(403)
    db().execute("DELETE FROM comments WHERE id=?", (cid,)); db().commit()
    return "", 200

@app.context_processor
def _ctx():
    def cover_palette(b):
        a, c = PALETTE[(b["id"] or 0) % len(PALETTE)]
        return {"from": a, "to": c}
    def read_time(para_count):
        m = max(1, round((para_count or 0) * 40 / 200))
        return f"{m} min"
    unread = unread_dm = 0
    if g.get("user"):
        try:
            unread = db().execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (g.user["id"],)).fetchone()[0]
            unread_dm = db().execute("SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE (c.user_a=? OR c.user_b=?) AND m.sender_id!=? AND m.read_at IS NULL", (g.user["id"], g.user["id"], g.user["id"])).fetchone()[0]
        except Exception: pass
    return {"cover_palette": cover_palette, "read_time": read_time, "unread_count": unread, "unread_dm": unread_dm,
            "layout": "_blank.html" if request.headers.get("HX-Request") else "base.html"}


def sanitize(html):
    return re.sub(r"<img ", '<img loading="lazy" ', bleach.clean(html, tags=TAGS, attributes=ATTRS, strip=True))

def _para(el):
    txt = el.get_text(" ", strip=True) if hasattr(el, "get_text") else ""
    is_img = el.name == "img"
    if not txt and not is_img and not (hasattr(el, "find") and el.find("img")): return None
    h = sanitize(str(el)) if (el.name in BLOCKS or is_img or el.name == "hr") else f"<p>{sanitize(str(el))}</p>"
    return {"html": h, "plain": txt}

def html_paragraphs(html):
    soup = BeautifulSoup(html, "html.parser")
    container = soup.body or soup
    out, seen = [], set()
    for el in container.find_all(["p","h1","h2","h3","h4","h5","h6","blockquote","pre","figure","img","hr"]):
        if any(id(a) in seen for a in el.parents): continue
        seen.add(id(el))
        if (p := _para(el)): out.append(p)
    return out

def _split_soup(soup):
    chapters, title, paras = [], None, []
    for el in list(soup.children):
        n = getattr(el, "name", None)
        if not n: continue
        if n in ("h1","h2"):
            if paras or title: chapters.append((title, paras))
            title, paras = el.get_text(" ", strip=True), []
        elif (p := _para(el)): paras.append(p)
    if paras or title: chapters.append((title, paras))
    return chapters

def parse_markdown(text):
    return _split_soup(BeautifulSoup(md.markdown(text, extensions=["extra","sane_lists"]), "html.parser")) or [(None, [])]

def parse_epub(fs, bid):
    from urllib.parse import unquote
    with tempfile.NamedTemporaryFile(suffix=".epub") as t:
        t.write(fs.read()); t.flush(); book = epub.read_epub(t.name)
    title = book.get_metadata("DC", "title")
    author = book.get_metadata("DC", "creator")
    epub_caption = None
    if title and title[0] and title[0][0]:
        ti = title[0][0].strip()
        a = author[0][0].strip() if author and author[0] and author[0][0] else ""
        epub_caption = f"{ti} — {a}" if a else ti
    cover_bytes = None
    for it in book.get_items_of_type(ITEM_COVER):
        if (data := it.get_content()): cover_bytes = data; break
    if not cover_bytes:
        meta = book.get_metadata("OPF", "cover")
        cid = meta[0][1].get("content") if meta and meta[0] and meta[0][1] else None
        if cid and (it := book.get_item_with_id(cid)):
            cover_bytes = it.get_content()
    if not cover_bytes:
        for it in book.get_items_of_type(ITEM_IMAGE):
            if "cover" in (it.file_name or "").lower():
                cover_bytes = it.get_content(); break
    images = {}
    for it in book.get_items_of_type(ITEM_IMAGE):
        if (url := save_pic(it.get_content(), "images", 1600, f"b{bid}")):
            full = it.file_name or ""
            for k in {full, Path(full).name, unquote(full), unquote(Path(full).name), full.lower(), Path(full).name.lower()}:
                if k: images[k] = url
    chapters = []
    for it in book.get_items_of_type(ITEM_DOCUMENT):
        if "nav" in (getattr(it, "properties", []) or []): continue
        if (it.file_name or "").lower().endswith(("nav.xhtml","toc.xhtml")): continue
        try: content = it.get_content().decode("utf-8", errors="ignore")
        except Exception: continue
        doc_dir = Path(it.file_name or "").parent
        soup = BeautifulSoup(content, "html.parser")
        for img in soup.find_all("img"):
            src = str(img.get("src", ""))
            tgt = None
            if src:
                candidates = [src, unquote(src), Path(src).name, unquote(Path(src).name)]
                if doc_dir != Path("."):
                    try: resolved = str((doc_dir / src).as_posix()).lstrip("./")
                    except Exception: resolved = None
                    if resolved: candidates.extend([resolved, unquote(resolved)])
                for c in candidates:
                    if c in images: tgt = images[c]; break
                    if c.lower() in images: tgt = images[c.lower()]; break
            if tgt: img["src"] = tgt
            else: img.decompose()
        h = soup.find(["h1","h2","h3"])
        title = (h.get_text(" ", strip=True)[:200] or None) if h else None
        if h: h.decompose()
        paras = html_paragraphs(str(soup))
        if paras or title: chapters.append((title, paras))
    return chapters or [(None, [])], epub_caption, cover_bytes

def save_pic(src, kind, max_w, prefix):
    try:
        img = Image.open(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src)
        if img.mode != "RGB": img = img.convert("RGB")
        if img.width > max_w: img = img.resize((max_w, int(img.height * max_w / img.width)))
        name = f"{prefix}_{secrets.token_hex(6)}.webp"
        img.save(UP[kind] / name, "WEBP", quality=85)
        return url_for("uploaded", kind=kind, name=name)
    except Exception: return None

def write_chapters(c, bid, chapters):
    c.execute("DELETE FROM chapters WHERE book_id=?", (bid,))
    c.execute("DELETE FROM paragraphs WHERE book_id=?", (bid,))
    idx = 0
    for ci, (title, paras) in enumerate(chapters):
        cid = c.execute("INSERT INTO chapters(book_id,idx,title) VALUES(?,?,?)",
                        (bid, ci, title)).lastrowid if (title or len(chapters) > 1) else None
        for p in paras:
            c.execute("INSERT INTO paragraphs(book_id,chapter_id,idx,html,plain) VALUES(?,?,?,?,?)",
                      (bid, cid, idx, p["html"], p["plain"])); idx += 1
    return idx

def save_chapters(bid, chapters):
    c = db(); write_chapters(c, bid, chapters)
    c.execute("UPDATE books SET updated_at=datetime('now') WHERE id=?", (bid,)); c.commit()

def save_tags(bid):
    c = db()
    row = c.execute("SELECT caption FROM books WHERE id=?", (bid,)).fetchone()
    c.execute("DELETE FROM tags WHERE book_id=?", (bid,))
    for t in {m.lower() for m in re.findall(r"#([a-zA-Z0-9_]+)", (row and row["caption"]) or "")}:
        c.execute("INSERT OR IGNORE INTO tags(book_id, tag) VALUES(?,?)", (bid, t))

def _vis_ctx(user, owner_ids):
    c = db(); uid = user["id"] if user else None
    owner_ids = list(owner_ids)
    private = {r[0] for r in c.execute(f"SELECT id FROM users WHERE private=1 AND id IN ({','.join('?'*len(owner_ids))})", owner_ids)} if owner_ids else set()
    following = {r[0] for r in c.execute("SELECT followee_id FROM follows WHERE follower_id=?", (uid,))} if uid else set()
    blocked = {r[0] for r in c.execute("SELECT blocked_id FROM blocks WHERE blocker_id=? UNION SELECT blocker_id FROM blocks WHERE blocked_id=?", (uid, uid))} if uid else set()
    return {"uid": uid, "private": private, "following": following, "blocked": blocked}

def _visible(b, ctx):
    if not b: return False
    if ctx["uid"] and b["owner_id"] == ctx["uid"]: return True
    if b["status"] != "published" or b["visibility"] != "public": return False
    if b["owner_id"] in ctx["private"] and b["owner_id"] not in ctx["following"]: return False
    return b["owner_id"] not in ctx["blocked"]

def can_view(u, b):
    return _visible(b, _vis_ctx(u, {b["owner_id"]})) if b else False

def post_state(bid, user):
    c = db(); o = lambda q, a: c.execute(q, a).fetchone()
    liked = saved = False; progress_idx = 0
    if user:
        liked = o("SELECT 1 FROM likes WHERE user_id=? AND book_id=?", (user["id"], bid)) is not None
        saved = o("SELECT 1 FROM saves WHERE user_id=? AND book_id=?", (user["id"], bid)) is not None
        pr = o("SELECT paragraph_idx FROM reading_progress WHERE user_id=? AND book_id=?", (user["id"], bid))
        progress_idx = pr["paragraph_idx"] if pr else 0
    return {"liked": liked, "saved": saved,
            "like_count": o("SELECT COUNT(*) FROM likes WHERE book_id=?", (bid,))[0],
            "comment_count": o("SELECT COUNT(*) FROM comments WHERE book_id=?", (bid,))[0],
            "progress_idx": progress_idx}

def hydrate(rows, user):
    if not rows: return []
    src_ids = {r["repost_of"] for r in rows if r["repost_of"]}
    originals = {}
    if src_ids:
        c = db()
        originals = {o["id"]: o for o in c.execute(f"SELECT * FROM books WHERE id IN ({','.join('?'*len(src_ids))})", list(src_ids))}
    ctx = _vis_ctx(user, {r["owner_id"] for r in rows} | {o["owner_id"] for o in originals.values()})
    def ok(r):
        if not _visible(r, ctx): return False
        return _visible(originals.get(r["repost_of"]), ctx) if r["repost_of"] else True
    visible = [r for r in rows if ok(r)]
    if not visible: return []
    c = db(); ids = [r["id"] for r in visible]; ph = ",".join("?" * len(ids))
    likes = dict(c.execute(f"SELECT book_id, COUNT(*) FROM likes WHERE book_id IN ({ph}) GROUP BY book_id", ids).fetchall())
    comments = dict(c.execute(f"SELECT book_id, COUNT(*) FROM comments WHERE book_id IN ({ph}) GROUP BY book_id", ids).fetchall())
    liked = saved = set(); progress = {}
    if user:
        a = [user["id"], *ids]
        liked = {r[0] for r in c.execute(f"SELECT book_id FROM likes WHERE user_id=? AND book_id IN ({ph})", a)}
        saved = {r[0] for r in c.execute(f"SELECT book_id FROM saves WHERE user_id=? AND book_id IN ({ph})", a)}
        progress = {r[0]: r[1] for r in c.execute(f"SELECT book_id, paragraph_idx FROM reading_progress WHERE user_id=? AND book_id IN ({ph})", a)}
    return [{**dict(r), "liked": r["id"] in liked, "saved": r["id"] in saved,
             "like_count": likes.get(r["id"], 0), "comment_count": comments.get(r["id"], 0),
             "progress_idx": progress.get(r["id"], 0)} for r in visible]

def htmx(): return request.headers.get("HX-Request") == "true"

def feed(title, empty, sql, args=()):
    return render_template("feed.html", title=title, empty=empty,
                           books=hydrate(db().execute(sql, args).fetchall(), g.user))


@app.route("/")
def home():
    if not g.user: return redirect(url_for("explore"))
    continuing = hydrate(db().execute(
        f"SELECT {FEED} FROM books b JOIN users u ON u.id=b.owner_id JOIN reading_progress rp ON rp.book_id=b.id WHERE rp.user_id=? AND rp.paragraph_idx > 0 ORDER BY b.updated_at DESC LIMIT 6",
        (g.user["id"],)).fetchall(), g.user)
    books = hydrate(db().execute(
        f"SELECT {FEED} FROM books b JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' AND (b.owner_id=:u OR b.owner_id IN (SELECT followee_id FROM follows WHERE follower_id=:u)) ORDER BY b.updated_at DESC LIMIT 50",
        {"u": g.user["id"]}).fetchall(), g.user)
    return render_template("feed.html", title="Home", empty="Follow someone to fill your feed.", books=books, continuing=continuing)

@app.route("/explore")
def explore():
    return feed("Explore", "No public posts yet.",
        f"SELECT {FEED} FROM books b JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' ORDER BY b.updated_at DESC LIMIT 50")

@app.route("/reels")
def reels():
    rows = db().execute(
        "SELECT p.book_id, p.idx, p.plain, b.caption, b.cover, b.owner_id, u.username AS owner_username FROM paragraphs p JOIN books b ON b.id=p.book_id JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' AND b.repost_of IS NULL AND length(p.plain) BETWEEN 180 AND 700 ORDER BY RANDOM() LIMIT 120"
    ).fetchall()
    ctx = _vis_ctx(g.user, {r["owner_id"] for r in rows})
    seen, items = set(), []
    for r in rows:
        if r["book_id"] in seen or r["owner_id"] in ctx["blocked"]: continue
        if r["owner_id"] in ctx["private"] and r["owner_id"] not in ctx["following"]: continue
        seen.add(r["book_id"]); items.append(r)
        if len(items) >= 24: break
    state = {}
    if items:
        c = db(); ids = [r["book_id"] for r in items]; ph = ",".join("?" * len(ids))
        likes = dict(c.execute(f"SELECT book_id, COUNT(*) FROM likes WHERE book_id IN ({ph}) GROUP BY book_id", ids).fetchall())
        comments = dict(c.execute(f"SELECT book_id, COUNT(*) FROM comments WHERE book_id IN ({ph}) GROUP BY book_id", ids).fetchall())
        liked = saved = set()
        if g.user:
            a = [g.user["id"], *ids]
            liked = {x[0] for x in c.execute(f"SELECT book_id FROM likes WHERE user_id=? AND book_id IN ({ph})", a)}
            saved = {x[0] for x in c.execute(f"SELECT book_id FROM saves WHERE user_id=? AND book_id IN ({ph})", a)}
        state = {b: {"liked": b in liked, "saved": b in saved, "like_count": likes.get(b, 0), "comment_count": comments.get(b, 0)} for b in ids}
    return render_template("reels.html", reels=items, state=state)

@app.route("/saved")
def saved():
    return feed("Saved", "Nothing saved.",
        f"SELECT {FEED.replace('u.', 'usr.')} FROM saves s JOIN books b ON b.id=s.book_id JOIN users usr ON usr.id=b.owner_id WHERE s.user_id=? ORDER BY s.book_id DESC", (need()["id"],))

@app.route("/settings", methods=["GET","POST"])
def settings():
    u = need()
    if request.method == "POST":
        dn = (request.form.get("display_name") or "").strip() or None
        bio = (request.form.get("bio") or "").strip() or None
        private = 1 if request.form.get("private") else 0
        c = db()
        c.execute("UPDATE users SET display_name=?, bio=?, private=? WHERE id=?", (dn, bio, private, u["id"]))
        av = request.files.get("avatar")
        if av and av.filename and (url := save_pic(av.stream, "covers", 400, f"a{u['id']}")):
            c.execute("UPDATE users SET avatar=? WHERE id=?", (url, u["id"]))
        c.commit()
        return redirect(url_for("profile", username=u["username"]))
    return render_template("settings.html")

@app.route("/u/<username>")
def profile(username):
    target = db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not target: abort(404)
    own = g.user and g.user["id"] == target["id"]
    where = "owner_id=? AND repost_of IS NULL" if own else "owner_id=? AND status='published' AND repost_of IS NULL"
    rows = db().execute(f"SELECT * FROM books WHERE {where} ORDER BY updated_at DESC", (target["id"],)).fetchall()
    books = hydrate(rows, g.user)
    o = lambda q: db().execute(q, (target["id"],)).fetchone()[0]
    paragraphs_read = db().execute("SELECT COALESCE(SUM(paragraph_idx),0) FROM reading_progress WHERE user_id=?", (target["id"],)).fetchone()[0]
    days = [r[0] for r in db().execute("SELECT DISTINCT date(updated_at) FROM books WHERE owner_id=? UNION SELECT DISTINCT date(updated_at) FROM books WHERE id IN (SELECT book_id FROM reading_progress WHERE user_id=?) ORDER BY 1 DESC LIMIT 60", (target["id"], target["id"])).fetchall()]
    streak = 0
    from datetime import date
    today = date.today()
    for i, d in enumerate(days):
        try:
            from datetime import datetime as dt
            ds = dt.strptime(d, "%Y-%m-%d").date()
            if (today - ds).days == i: streak += 1
            else: break
        except Exception: break
    stats = {"books": len(books),
             "followers": o("SELECT COUNT(*) FROM follows WHERE followee_id=?"),
             "following": o("SELECT COUNT(*) FROM follows WHERE follower_id=?"),
             "paras_read": paragraphs_read, "streak": streak}
    is_following = bool(g.user and not own and db().execute(
        "SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?", (g.user["id"], target["id"])).fetchone())
    is_blocked = bool(g.user and not own and db().execute(
        "SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?", (g.user["id"], target["id"])).fetchone())
    return render_template("profile.html", target=target, books=books, stats=stats, is_following=is_following, is_blocked=is_blocked)

@app.post("/follow/<int:uid>")
def follow(uid):
    u = need()
    if uid == u["id"]: abort(400)
    c = db()
    existing = c.execute("SELECT 1 FROM follows WHERE follower_id=? AND followee_id=?", (u["id"], uid)).fetchone()
    sql = "DELETE FROM follows WHERE follower_id=? AND followee_id=?" if existing else "INSERT INTO follows(follower_id,followee_id) VALUES(?,?)"
    c.execute(sql, (u["id"], uid)); c.commit()
    target = c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if htmx(): return render_template("partials/follow_btn.html", target=target, is_following=not existing)
    return redirect(url_for("profile", username=target["username"]))


@app.route("/new", methods=["GET","POST"])
def new_book():
    u = need()
    if request.method == "GET": return render_template("new.html")
    body_md = (request.form.get("body_md") or "").strip()
    upload = request.files.get("file")
    fn = (upload.filename or "").lower() if upload else ""
    if fn.endswith((".md", ".txt")):
        body_md = upload.read().decode("utf-8", errors="ignore").strip()
    if not fn.endswith(".epub") and not body_md: abort(400)
    bid = db().execute("INSERT INTO books(owner_id) VALUES(?)", (u["id"],)).lastrowid
    if fn.endswith(".epub"):
        try:
            chapters, epub_caption, cover_bytes = parse_epub(upload, bid)
            cap = epub_caption or (chapters[0][0] if chapters and chapters[0][0] else None)
            if cap: db().execute("UPDATE books SET caption=? WHERE id=?", (cap[:200], bid))
            if cover_bytes and (url := save_pic(cover_bytes, "covers", 1080, f"c{bid}")):
                db().execute("UPDATE books SET cover=? WHERE id=?", (url, bid))
            save_chapters(bid, chapters); save_tags(bid); db().commit()
        except Exception:
            db().execute("DELETE FROM books WHERE id=?", (bid,)); db().commit(); abort(400)
        return redirect(url_for("home"))
    soup = BeautifulSoup(md.markdown(body_md, extensions=["extra","sane_lists"]), "html.parser")
    img = soup.find("img")
    if img and (src := str(img.get("src", ""))).startswith("data:"):
        import base64
        try: data = base64.b64decode(src.split(",", 1)[1])
        except Exception: data = None
        if data and (url := save_pic(data, "covers", 1080, f"c{bid}")):
            db().execute("UPDATE books SET cover=? WHERE id=?", (url, bid)); img.decompose()
    if (h := soup.find(["h1","h2"])):
        db().execute("UPDATE books SET caption=? WHERE id=?", (h.get_text(" ", strip=True)[:200], bid))
    db().execute("UPDATE books SET source_md=? WHERE id=?", (body_md, bid))
    chapters = _split_soup(soup)
    if chapters: save_chapters(bid, chapters)
    save_tags(bid); db().commit()
    return redirect(url_for("home"))


@app.route("/books/<int:bid>/edit", methods=["GET","POST"])
def book_edit(bid):
    u = need()
    book = db().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    if not book or book["owner_id"] != u["id"]: abort(403)
    if request.method == "GET":
        body = book["source_md"]
        if not body:
            rows = db().execute("SELECT p.html FROM paragraphs p WHERE p.book_id=? ORDER BY p.idx", (bid,)).fetchall()
            body = "\n\n".join(re.sub(r"<[^>]+>", "", r["html"]) for r in rows)
        return render_template("edit_post.html", book=book, body=body)
    body_md = (request.form.get("body_md") or "").strip()
    if not body_md: abort(400)
    soup = BeautifulSoup(md.markdown(body_md, extensions=["extra","sane_lists"]), "html.parser")
    if (h := soup.find(["h1","h2"])):
        db().execute("UPDATE books SET caption=? WHERE id=?", (h.get_text(" ", strip=True)[:200], bid))
    db().execute("UPDATE books SET source_md=? WHERE id=?", (body_md, bid))
    save_tags(bid); save_chapters(bid, _split_soup(soup))
    return redirect(url_for("book_read", bid=bid))

@app.post("/books/<int:bid>/delete")
def book_delete(bid):
    u = need()
    book = db().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    if not book or book["owner_id"] != u["id"]: abort(403)
    db().execute("DELETE FROM books WHERE id=?", (bid,)); db().commit()
    if htmx(): return "", 200
    return redirect(url_for("home"))

@app.post("/books/<int:bid>/repost")
def book_repost(bid):
    u = need()
    quote = (request.form.get("quote") or "").strip() or None
    src = db().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    if not src or not can_view(u, src): abort(404)
    db().execute("INSERT INTO books(owner_id, caption, cover, repost_of, quote) VALUES(?,?,?,?,?)",
                 (u["id"], src["caption"], src["cover"], bid, quote)); db().commit()
    return redirect(url_for("home"))

@app.get("/u/<username>/followers")
def followers(username):
    t = db().execute("SELECT id, username, display_name FROM users WHERE username=?", (username,)).fetchone()
    if not t: abort(404)
    users = db().execute("SELECT usr.username, usr.display_name, usr.avatar FROM follows f JOIN users usr ON usr.id=f.follower_id WHERE f.followee_id=? ORDER BY usr.username", (t["id"],)).fetchall()
    return render_template("user_list.html", title=f"{t['display_name'] or t['username']} · followers", users=users, empty="No followers yet.")

@app.get("/u/<username>/following")
def following(username):
    t = db().execute("SELECT id, username, display_name FROM users WHERE username=?", (username,)).fetchone()
    if not t: abort(404)
    users = db().execute("SELECT usr.username, usr.display_name, usr.avatar FROM follows f JOIN users usr ON usr.id=f.followee_id WHERE f.follower_id=? ORDER BY usr.username", (t["id"],)).fetchall()
    return render_template("user_list.html", title=f"{t['display_name'] or t['username']} · following", users=users, empty="Not following anyone yet.")

@app.post("/logout")
def logout():
    resp = redirect(url_for("home"))
    resp.delete_cookie("dev_as")
    return resp

@app.post("/clubs/<int:cid>/leave")
def club_leave(cid):
    u = need()
    db().execute("DELETE FROM club_members WHERE club_id=? AND user_id=?", (cid, u["id"])); db().commit()
    return redirect(url_for("clubs"))

@app.post("/clubs/<int:cid>/delete")
def club_delete(cid):
    u = need()
    info = db().execute("SELECT owner_id FROM clubs WHERE id=?", (cid,)).fetchone()
    if not info or info["owner_id"] != u["id"]: abort(403)
    db().execute("DELETE FROM clubs WHERE id=?", (cid,)); db().commit()
    return redirect(url_for("clubs"))

@app.delete("/dms/<username>")
def dm_delete(username):
    u = need()
    other = db().execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if not other: abort(404)
    pa, pb = _conv_pair(u["id"], other["id"])
    db().execute("DELETE FROM conversations WHERE user_a=? AND user_b=?", (pa, pb)); db().commit()
    if htmx(): return "", 200
    return redirect(url_for("dms"))

@app.post("/notifications/read_all")
def notifications_read_all():
    u = need()
    db().execute("UPDATE notifications SET read_at=datetime('now') WHERE user_id=? AND read_at IS NULL", (u["id"],)); db().commit()
    return redirect(url_for("notifications"))

@app.get("/tag/<tag>")
def tag_page(tag):
    tag = tag.lower().strip("#")
    rows = db().execute(f"SELECT DISTINCT {FEED} FROM books b JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' AND b.repost_of IS NULL AND (b.caption LIKE ? OR EXISTS (SELECT 1 FROM tags t WHERE t.book_id=b.id AND t.tag=?)) ORDER BY b.updated_at DESC LIMIT 50",
                       (f"%#{tag}%", tag)).fetchall()
    books = hydrate(rows, g.user)
    return render_template("feed.html", title=f"#{tag}", empty=f"No posts tagged #{tag}.", books=books, continuing=[])

@app.post("/block/<int:uid>")
def block(uid):
    u = need()
    if uid == u["id"]: abort(400)
    c = db()
    existing = c.execute("SELECT 1 FROM blocks WHERE blocker_id=? AND blocked_id=?", (u["id"], uid)).fetchone()
    if existing: c.execute("DELETE FROM blocks WHERE blocker_id=? AND blocked_id=?", (u["id"], uid))
    else: c.execute("INSERT INTO blocks(blocker_id, blocked_id) VALUES(?,?)", (u["id"], uid))
    c.commit()
    return redirect(request.referrer or url_for("home"))

@app.route("/clubs", methods=["GET","POST"])
def clubs():
    u = need()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        bid = request.form.get("book_id", type=int)
        if not name or not bid: abort(400)
        _viewable(bid)
        cid = db().execute("INSERT INTO clubs(book_id, name, owner_id) VALUES(?,?,?)", (bid, name, u["id"])).lastrowid
        db().execute("INSERT INTO club_members(club_id, user_id) VALUES(?,?)", (cid, u["id"])); db().commit()
        return redirect(url_for("club", cid=cid))
    rows = db().execute("SELECT c.*, b.cover, b.caption AS book_caption, (SELECT COUNT(*) FROM club_members WHERE club_id=c.id) AS members FROM clubs c JOIN books b ON b.id=c.book_id WHERE EXISTS (SELECT 1 FROM club_members WHERE club_id=c.id AND user_id=?) OR c.owner_id=? ORDER BY c.created_at DESC", (u["id"], u["id"])).fetchall()
    raw = db().execute("SELECT c.*, b.cover, b.caption AS book_caption, b.owner_id AS book_owner, b.status AS book_status, b.visibility AS book_visibility, (SELECT COUNT(*) FROM club_members WHERE club_id=c.id) AS members FROM clubs c JOIN books b ON b.id=c.book_id WHERE NOT EXISTS (SELECT 1 FROM club_members WHERE club_id=c.id AND user_id=?) AND c.owner_id != ? ORDER BY c.created_at DESC LIMIT 40", (u["id"], u["id"])).fetchall()
    ctx = _vis_ctx(u, {r["book_owner"] for r in raw})
    public_clubs = [r for r in raw if _visible({"owner_id": r["book_owner"], "status": r["book_status"], "visibility": r["book_visibility"]}, ctx)][:10]
    return render_template("clubs.html", clubs=rows, public_clubs=public_clubs)

@app.route("/clubs/<int:cid>", methods=["GET","POST"])
def club(cid):
    u = need()
    info = db().execute("SELECT c.*, b.cover, b.caption AS book_caption FROM clubs c JOIN books b ON b.id=c.book_id WHERE c.id=?", (cid,)).fetchone()
    if not info: abort(404)
    if not can_view(u, db().execute("SELECT * FROM books WHERE id=?", (info["book_id"],)).fetchone()): abort(404)
    is_member = db().execute("SELECT 1 FROM club_members WHERE club_id=? AND user_id=?", (cid, u["id"])).fetchone()
    if not is_member and request.args.get("join"):
        db().execute("INSERT OR IGNORE INTO club_members(club_id, user_id) VALUES(?,?)", (cid, u["id"])); db().commit()
        is_member = True
    if request.method == "POST" and is_member:
        body = (request.form.get("body") or "").strip()
        if body:
            mid = db().execute("INSERT INTO club_messages(club_id, user_id, body) VALUES(?,?,?)", (cid, u["id"], body)).lastrowid
            db().commit()
            if htmx():
                m = db().execute("SELECT m.*, usr.username FROM club_messages m JOIN users usr ON usr.id=m.user_id WHERE m.id=?", (mid,)).fetchone()
                return render_template("partials/club_msg.html", m=m, me_id=u["id"])
        return redirect(url_for("club", cid=cid))
    msgs = db().execute("SELECT m.*, usr.username FROM club_messages m JOIN users usr ON usr.id=m.user_id WHERE m.club_id=? ORDER BY m.id LIMIT 200", (cid,)).fetchall()
    members = db().execute("SELECT usr.* FROM club_members cm JOIN users usr ON usr.id=cm.user_id WHERE cm.club_id=?", (cid,)).fetchall()
    return render_template("club.html", info=info, msgs=msgs, members=members, is_member=is_member, cid=cid)

@app.route("/books/<int:bid>")
def book_read(bid):
    book = db().execute(f"SELECT {FEED} FROM books b JOIN users u ON u.id=b.owner_id WHERE b.id=?", (bid,)).fetchone()
    if book and book["repost_of"]:
        return redirect(url_for("book_read", bid=book["repost_of"]))
    if not book or not can_view(g.user, book): abort(404 if not book else 403)
    rows = db().execute("SELECT p.idx, p.html, c.title AS ctitle, c.idx AS cidx FROM paragraphs p LEFT JOIN chapters c ON c.id=p.chapter_id WHERE p.book_id=? ORDER BY p.idx", (bid,)).fetchall()
    paragraphs, last = [], object()
    for r in rows:
        paragraphs.append({"idx": r["idx"], "html": r["html"], "chapter_title": r["ctitle"] if r["cidx"] != last else None})
        last = r["cidx"]
    progress = db().execute("SELECT * FROM reading_progress WHERE user_id=? AND book_id=?", (g.user["id"], bid)).fetchone() if g.user else None
    highlights = {r["paragraph_idx"] for r in db().execute("SELECT paragraph_idx FROM highlights WHERE user_id=? AND book_id=?", (g.user["id"], bid)).fetchall()} if g.user else set()
    notes = {r["paragraph_idx"]: r["body"] for r in db().execute("SELECT paragraph_idx, body FROM notes WHERE user_id=? AND book_id=?", (g.user["id"], bid)).fetchall()} if g.user else {}
    return render_template("reader.html", book=book, paragraphs=paragraphs, progress=progress, highlights=highlights, notes=notes, **post_state(bid, g.user))

@app.post("/books/<int:bid>/progress")
def save_progress(bid):
    u = need()
    db().execute("INSERT INTO reading_progress(user_id,book_id,paragraph_idx) VALUES(?,?,?) ON CONFLICT(user_id,book_id) DO UPDATE SET paragraph_idx=excluded.paragraph_idx",
        (u["id"], bid, request.form.get("idx", type=int) or 0))
    db().commit(); return "", 200

@app.delete("/books/<int:bid>/progress")
def clear_progress(bid):
    u = need()
    db().execute("DELETE FROM reading_progress WHERE user_id=? AND book_id=?", (u["id"], bid)); db().commit()
    return "", 200

@app.post("/books/<int:bid>/highlight/<int:idx>")
def highlight(bid, idx):
    u = need(); c = db()
    if c.execute("SELECT 1 FROM highlights WHERE user_id=? AND book_id=? AND paragraph_idx=?", (u["id"], bid, idx)).fetchone():
        c.execute("DELETE FROM highlights WHERE user_id=? AND book_id=? AND paragraph_idx=?", (u["id"], bid, idx))
    else:
        c.execute("INSERT INTO highlights(user_id,book_id,paragraph_idx) VALUES(?,?,?)", (u["id"], bid, idx))
    c.commit(); return "", 200

@app.route("/books/<int:bid>/note/<int:idx>", methods=["POST","DELETE"])
def note(bid, idx):
    u = need(); c = db()
    if request.method == "DELETE":
        c.execute("DELETE FROM notes WHERE user_id=? AND book_id=? AND paragraph_idx=?", (u["id"], bid, idx))
    else:
        body = (request.form.get("body") or "").strip()
        if body:
            c.execute("DELETE FROM notes WHERE user_id=? AND book_id=? AND paragraph_idx=?", (u["id"], bid, idx))
            c.execute("INSERT INTO notes(user_id,book_id,paragraph_idx,body) VALUES(?,?,?,?)", (u["id"], bid, idx, body))
    c.commit(); return "", 200

@app.get("/books/<int:bid>/toc")
def book_toc(bid):
    need()
    chapters = db().execute("SELECT c.title, MIN(p.idx) AS first_idx FROM chapters c JOIN paragraphs p ON p.chapter_id=c.id WHERE c.book_id=? GROUP BY c.id ORDER BY c.idx", (bid,)).fetchall()
    return render_template("toc.html", bid=bid, chapters=chapters)

@app.get("/books/<int:bid>/notes")
def book_notes(bid):
    u = need()
    rows = db().execute("SELECT n.*, p.plain FROM notes n LEFT JOIN paragraphs p ON p.book_id=n.book_id AND p.idx=n.paragraph_idx WHERE n.user_id=? AND n.book_id=? ORDER BY n.paragraph_idx", (u["id"], bid)).fetchall()
    return render_template("notes.html", bid=bid, notes=rows)


def notify(actor_id, kind, **extra):
    c = db()
    target_user = extra.get("user_id")
    if not target_user or target_user == actor_id: return
    c.execute("INSERT INTO notifications(user_id,actor_id,kind,book_id,comment_id) VALUES(?,?,?,?,?)",
              (target_user, actor_id, kind, extra.get("book_id"), extra.get("comment_id"))); c.commit()

def parse_mentions(text):
    return set(re.findall(r"@([a-zA-Z0-9_]+)", text or ""))

def _viewable(bid):
    b = db().execute("SELECT * FROM books WHERE id=?", (bid,)).fetchone()
    if not can_view(g.user, b): abort(404)
    return b

def _toggle(table, bid):
    u = need(); c = db()
    exists = c.execute(f"SELECT 1 FROM {table} WHERE user_id=? AND book_id=?", (u["id"], bid)).fetchone()
    q = f"DELETE FROM {table} WHERE user_id=? AND book_id=?" if exists else f"INSERT INTO {table}(user_id,book_id) VALUES(?,?)"
    c.execute(q, (u["id"], bid)); c.commit()
    return not exists

def _btn(name, bid):
    if htmx(): return render_template(f"partials/{name}_btn.html", bid=bid, **post_state(bid, g.user))
    return redirect(url_for("book_read", bid=bid))

@app.post("/books/<int:bid>/like")
def like(bid):
    book = _viewable(bid)
    if _toggle("likes", bid):
        notify(g.user["id"], "like", user_id=book["owner_id"], book_id=bid)
    return _btn("like", bid)

@app.post("/books/<int:bid>/save")
def save(bid): _viewable(bid); _toggle("saves", bid); return _btn("save", bid)

@app.post("/books/<int:bid>/comments")
def add_comment(bid):
    u = need()
    book = _viewable(bid)
    body = (request.form.get("body") or "").strip()
    parent_id = request.form.get("parent_id", type=int)
    if not body: abort(400)
    cur = db().execute("INSERT INTO comments(user_id,book_id,parent_id,body) VALUES(?,?,?,?)", (u["id"], bid, parent_id, body))
    db().commit()
    cid = cur.lastrowid
    notify(u["id"], "comment", user_id=book["owner_id"], book_id=bid, comment_id=cid)
    if parent_id:
        parent = db().execute("SELECT user_id FROM comments WHERE id=?", (parent_id,)).fetchone()
        if parent: notify(u["id"], "reply", user_id=parent["user_id"], book_id=bid, comment_id=cid)
    for name in parse_mentions(body):
        m = db().execute("SELECT id FROM users WHERE username=?", (name,)).fetchone()
        if m: notify(u["id"], "mention", user_id=m["id"], book_id=bid, comment_id=cid)
    c = db().execute("SELECT c.*, u.username FROM comments c JOIN users u ON u.id=c.user_id WHERE c.id=?", (cid,)).fetchone()
    if htmx(): return render_template("partials/comment.html", c=c)
    return redirect(url_for("book_read", bid=bid))

@app.get("/books/<int:bid>/comments")
def book_comments(bid):
    _viewable(bid)
    rows = db().execute("SELECT c.*, u.username FROM comments c JOIN users u ON u.id=c.user_id WHERE c.book_id=? ORDER BY COALESCE(c.parent_id, c.id), c.created_at", (bid,)).fetchall()
    return render_template("comments.html", comments=rows, bid=bid)

@app.get("/notifications")
def notifications():
    u = need()
    rows = db().execute("SELECT n.*, a.username AS actor_name, a.avatar AS actor_avatar, b.caption AS book_caption FROM notifications n JOIN users a ON a.id=n.actor_id LEFT JOIN books b ON b.id=n.book_id WHERE n.user_id=? ORDER BY n.created_at DESC LIMIT 60", (u["id"],)).fetchall()
    db().execute("UPDATE notifications SET read_at=datetime('now') WHERE user_id=? AND read_at IS NULL", (u["id"],)); db().commit()
    return render_template("notifications.html", items=rows)

@app.get("/notifications/count")
def notifications_count():
    u = need()
    n = db().execute("SELECT COUNT(*) FROM notifications WHERE user_id=? AND read_at IS NULL", (u["id"],)).fetchone()[0]
    return str(n)


def _conv_pair(a, b): return (a, b) if a < b else (b, a)

def _get_or_create_conv(a, b):
    pa, pb = _conv_pair(a, b)
    c = db()
    row = c.execute("SELECT id FROM conversations WHERE user_a=? AND user_b=?", (pa, pb)).fetchone()
    if row: return row["id"]
    return c.execute("INSERT INTO conversations(user_a,user_b) VALUES(?,?)", (pa, pb)).lastrowid

@app.get("/dms/new")
def dms_new():
    u = need()
    q = (request.args.get("q") or "").strip()
    users = []
    if q:
        users = db().execute("SELECT username, display_name, avatar FROM users WHERE id != ? AND (username LIKE ? OR display_name LIKE ?) LIMIT 20", (u["id"], f"%{q}%", f"%{q}%")).fetchall()
    else:
        users = db().execute("SELECT DISTINCT usr.username, usr.display_name, usr.avatar FROM users usr JOIN follows f ON (f.followee_id=usr.id AND f.follower_id=?) WHERE usr.id != ? LIMIT 20", (u["id"], u["id"])).fetchall()
    return render_template("dms_new.html", q=q, users=users)

@app.get("/dms")
def dms():
    u = need()
    rows = db().execute("""
      SELECT c.id, c.updated_at,
        CASE WHEN c.user_a=:u THEN c.user_b ELSE c.user_a END AS other_id,
        (SELECT body FROM messages WHERE conversation_id=c.id ORDER BY id DESC LIMIT 1) AS last_body,
        (SELECT sender_id FROM messages WHERE conversation_id=c.id ORDER BY id DESC LIMIT 1) AS last_sender,
        (SELECT COUNT(*) FROM messages WHERE conversation_id=c.id AND sender_id!=:u AND read_at IS NULL) AS unread
      FROM conversations c
      WHERE c.user_a=:u OR c.user_b=:u
      ORDER BY c.updated_at DESC LIMIT 60
    """, {"u": u["id"]}).fetchall()
    convs = []
    for r in rows:
        other = db().execute("SELECT username, display_name, avatar FROM users WHERE id=?", (r["other_id"],)).fetchone()
        convs.append({**dict(r), "other": dict(other)})
    return render_template("dms.html", convs=convs)

@app.route("/dms/<username>", methods=["GET","POST"])
def dm(username):
    u = need()
    other = db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not other or other["id"] == u["id"]: abort(404)
    if db().execute("SELECT 1 FROM blocks WHERE (blocker_id=? AND blocked_id=?) OR (blocker_id=? AND blocked_id=?)", (u["id"], other["id"], other["id"], u["id"])).fetchone():
        abort(403)
    cid = _get_or_create_conv(u["id"], other["id"])
    if request.method == "POST":
        body = (request.form.get("body") or "").strip()
        if body:
            db().execute("INSERT INTO messages(conversation_id,sender_id,body) VALUES(?,?,?)", (cid, u["id"], body))
            db().execute("UPDATE conversations SET updated_at=datetime('now') WHERE id=?", (cid,))
            db().commit()
            mid = db().execute("SELECT MAX(id) FROM messages WHERE conversation_id=?", (cid,)).fetchone()[0]
            if htmx():
                m = db().execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
                return render_template("partials/message.html", m=m, me_id=u["id"])
        return redirect(url_for("dm", username=username))
    msgs = db().execute("SELECT * FROM messages WHERE conversation_id=? ORDER BY id", (cid,)).fetchall()
    db().execute("UPDATE messages SET read_at=datetime('now') WHERE conversation_id=? AND sender_id!=? AND read_at IS NULL", (cid, u["id"]))
    db().commit()
    return render_template("dm.html", other=other, msgs=msgs, cid=cid)

@app.get("/dms/count")
def dms_count():
    u = need()
    n = db().execute("SELECT COUNT(*) FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE (c.user_a=? OR c.user_b=?) AND m.sender_id!=? AND m.read_at IS NULL", (u["id"], u["id"], u["id"])).fetchone()[0]
    return str(n)


@app.get("/search")
def search():
    q = (request.args.get("q") or "").strip()
    results = {"books": [], "lines": [], "users": []}
    if q:
        terms = re.findall(r"\w+", q)
        fq = " ".join(f'"{p}"*' for p in terms) if terms else '""'
        results["books"] = hydrate(db().execute(
            f"SELECT {FEED} FROM books b JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' AND b.repost_of IS NULL AND b.caption LIKE ? ORDER BY b.updated_at DESC LIMIT 12",
            (f"%{q}%",)).fetchall(), g.user)
        lines = db().execute(
            "SELECT p.book_id, p.idx, b.owner_id, b.caption, u.username, snippet(paragraphs_fts, 0, '<mark>', '</mark>', '…', 12) AS s FROM paragraphs_fts JOIN paragraphs p ON p.id=paragraphs_fts.paragraph_id JOIN books b ON b.id=p.book_id JOIN users u ON u.id=b.owner_id WHERE paragraphs_fts MATCH ? AND b.status='published' AND b.visibility='public' LIMIT 60",
            (fq,)).fetchall()
        ctx = _vis_ctx(g.user, {r["owner_id"] for r in lines})
        results["lines"] = [r for r in lines if r["owner_id"] not in ctx["blocked"]
                            and not (r["owner_id"] in ctx["private"] and r["owner_id"] not in ctx["following"])][:20]
        results["users"] = db().execute(
            "SELECT * FROM users WHERE username LIKE ? OR display_name LIKE ? LIMIT 12",
            (f"%{q}%", f"%{q}%")).fetchall()
    discover = {"books": [], "tags": [], "users": []}
    if not q:
        discover["books"] = hydrate(db().execute(
            f"SELECT {FEED}, (SELECT COUNT(*) FROM likes WHERE book_id=b.id) AS lk FROM books b JOIN users u ON u.id=b.owner_id WHERE b.status='published' AND b.visibility='public' AND b.repost_of IS NULL ORDER BY lk DESC, b.updated_at DESC LIMIT 9"
        ).fetchall(), g.user)
        discover["tags"] = db().execute("SELECT tag, COUNT(*) AS n FROM tags GROUP BY tag ORDER BY n DESC LIMIT 12").fetchall()
        discover["users"] = db().execute("SELECT username, display_name, avatar FROM users ORDER BY id DESC LIMIT 6").fetchall()
    tpl = "search_results.html" if request.headers.get("HX-Target") == "sres" else "search.html"
    return render_template(tpl, q=q, results=results, discover=discover)


@app.get("/uploads/<kind>/<name>")
def uploaded(kind, name):
    if kind not in UP: abort(404)
    return send_from_directory(UP[kind], name)

@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(404)
def _err(e):
    return render_template("error.html", code=e.code, msg={401:"Sign in.",403:"Not yours.",404:"Not found."}.get(e.code,"")), e.code


if __name__ == "__main__":
    init_db()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5050)), debug=DEV)
