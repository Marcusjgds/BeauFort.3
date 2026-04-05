from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import os, sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bf_2025_secret")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "models")
LOGO_DIR   = os.path.join(BASE_DIR, "uploads", "logos")
DB_PATH    = os.path.join(BASE_DIR, "database.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOGO_DIR, exist_ok=True)

ALLOWED_MODELS = {"rbxm", "rbxmx"}
ALLOWED_IMAGES = {"png", "jpg", "jpeg", "gif", "webp", "svg"}
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, description TEXT,
            price_type TEXT DEFAULT 'free', price INTEGER DEFAULT 0,
            category TEXT DEFAULT 'Other', file TEXT NOT NULL,
            thumbnail TEXT DEFAULT '', author TEXT NOT NULL,
            downloads INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            can_upload INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        db.execute("""CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            icon TEXT DEFAULT '📄',
            content TEXT DEFAULT '',
            visible INTEGER DEFAULT 1,
            sort_order INTEGER DEFAULT 0)""")
        db.execute("""CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        for k,v in [("maintenance","0"),("site_closed","0"),
                    ("maintenance_msg","Site en maintenance, revenez bientot !"),
                    ("site_closed_msg","Le site est ferme."),
                    ("site_logo",""),("theme","dark"),
                    ("site_name","Boutique de BeauFort"),
                    ("site_desc","La marketplace de modeles Roblox"),
                    ("discord_url",""),("discord_label","Discord")]:
            db.execute("INSERT OR IGNORE INTO site_settings (key,value) VALUES (?,?)",(k,v))
        for slug,title,icon,content,order in [
            ("histoire","Histoire","📖","<h2>Notre histoire</h2><p>Bienvenue dans l'histoire de Boutique de BeauFort...</p>",1),
            ("recrutement","Recrutement","🎯","<h2>Rejoins l'equipe</h2><p>Nous cherchons des personnes motivees...</p>",2),
            ("apropos","A propos","ℹ️","<h2>A propos</h2><p>Boutique de BeauFort est une marketplace Roblox...</p>",3)]:
            db.execute("INSERT OR IGNORE INTO pages (slug,title,icon,content,visible,sort_order) VALUES (?,?,?,?,1,?)",(slug,title,icon,content,order))
        db.commit()

init_db()

def get_setting(key, default=""):
    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO site_settings (key,value) VALUES (?,?)", (key,value))
        db.commit()

def get_all_settings():
    with get_db() as db:
        return {r["key"]:r["value"] for r in db.execute("SELECT key,value FROM site_settings").fetchall()}

def get_visible_pages():
    with get_db() as db:
        return [dict(p) for p in db.execute("SELECT * FROM pages WHERE visible=1 ORDER BY sort_order").fetchall()]

def allowed_model(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_MODELS
def allowed_image(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_IMAGES

@app.before_request
def check_status():
    exempt = ["/admin","/static","/uploads","/login","/logout","/api"]
    if any(request.path.startswith(e) for e in exempt): return None
    if get_setting("site_closed")=="1" and not session.get("is_admin"):
        return render_template("closed.html", msg=get_setting("site_closed_msg"), s=get_all_settings()), 503
    if get_setting("maintenance")=="1" and not session.get("is_admin"):
        return render_template("maintenance.html", msg=get_setting("maintenance_msg"), s=get_all_settings()), 503

def ctx():
    return dict(logged_in="user_id" in session, username=session.get("username",""),
                is_admin=session.get("is_admin",False), can_upload=session.get("can_upload",False),
                s=get_all_settings(), pages=get_visible_pages())

@app.route("/")
def index():
    with get_db() as db:
        models = [dict(m) for m in db.execute("SELECT * FROM models ORDER BY created_at DESC").fetchall()]
    return render_template("index.html", models=models, **ctx())

@app.route("/model/<int:mid>")
def model_page(mid):
    with get_db() as db:
        m = db.execute("SELECT * FROM models WHERE id=?",(mid,)).fetchone()
        if not m: return redirect(url_for("index"))
    return render_template("model_detail.html", m=dict(m), **ctx())

@app.route("/page/<slug>")
def custom_page(slug):
    with get_db() as db:
        page = db.execute("SELECT * FROM pages WHERE slug=? AND visible=1",(slug,)).fetchone()
        if not page: return redirect(url_for("index"))
    return render_template("custom_page.html", page=dict(page), **ctx())

@app.route("/login", methods=["GET","POST"])
def login():
    s = get_all_settings(); pg = get_visible_pages()
    if request.method=="GET":
        return render_template("login.html", error=None, s=s, pages=pg)
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    if not username or not password:
        return render_template("login.html", error="Pseudo et mot de passe requis.", s=s, pages=pg)
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?) AND password=?",(username,password)).fetchone()
    if not user:
        return render_template("login.html", error="Identifiants incorrects.", s=s, pages=pg)
    session.update({"user_id":user["id"],"username":user["username"],"is_admin":False,"can_upload":bool(user["can_upload"])})
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method=="POST":
        if request.form.get("password")==ADMIN_PASSWORD:
            session.update({"is_admin":True,"can_upload":True,"username":"Admin"})
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Mot de passe incorrect.", s=get_all_settings())
    if session.get("is_admin"): return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", error=None, s=get_all_settings())

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"): return redirect(url_for("admin"))
    with get_db() as db:
        users  = [dict(u) for u in db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()]
        models = [dict(m) for m in db.execute("SELECT * FROM models ORDER BY created_at DESC").fetchall()]
        pages  = [dict(p) for p in db.execute("SELECT * FROM pages ORDER BY sort_order").fetchall()]
    return render_template("admin_dashboard.html", users=users, models=models, pages=pages, **ctx())

@app.route("/admin/add_user", methods=["POST"])
def admin_add_user():
    if not session.get("is_admin"): return jsonify({"success":False})
    u = request.form.get("username","").strip(); p = request.form.get("password","").strip()
    if not u or not p: return jsonify({"success":False,"error":"Pseudo et mot de passe requis"})
    try:
        with get_db() as db:
            db.execute("INSERT INTO users (username,password,can_upload) VALUES (?,?,1)",(u,p))
            db.commit()
            uid = db.execute("SELECT id FROM users WHERE username=?",(u,)).fetchone()["id"]
        return jsonify({"success":True,"username":u,"id":uid})
    except: return jsonify({"success":False,"error":"Utilisateur deja existant"})

@app.route("/admin/remove_user/<int:uid>", methods=["POST"])
def admin_remove_user(uid):
    if not session.get("is_admin"): return jsonify({"success":False})
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=?",(uid,)); db.commit()
    return jsonify({"success":True})

@app.route("/admin/delete_model/<int:mid>", methods=["POST"])
def admin_delete_model(mid):
    if not session.get("is_admin"): return jsonify({"success":False})
    with get_db() as db:
        m = db.execute("SELECT * FROM models WHERE id=?",(mid,)).fetchone()
        if m:
            try: os.remove(os.path.join(UPLOAD_DIR, m["file"]))
            except: pass
            if m["thumbnail"]:
                try: os.remove(os.path.join(UPLOAD_DIR, m["thumbnail"]))
                except: pass
        db.execute("DELETE FROM models WHERE id=?",(mid,)); db.commit()
    return jsonify({"success":True})

@app.route("/admin/settings", methods=["POST"])
def admin_settings():
    if not session.get("is_admin"): return jsonify({"success":False})
    data = request.get_json() or {}
    for key in ["maintenance","site_closed","maintenance_msg","site_closed_msg","theme","site_name","site_desc","discord_url","discord_label"]:
        if key in data: set_setting(key, str(data[key]))
    return jsonify({"success":True})

@app.route("/admin/save_page", methods=["POST"])
def admin_save_page():
    if not session.get("is_admin"): return jsonify({"success":False})
    data = request.get_json() or {}
    pid = data.get("id")
    if pid:
        with get_db() as db:
            db.execute("UPDATE pages SET title=?,icon=?,content=?,visible=?,sort_order=? WHERE id=?",
                (data.get("title",""),data.get("icon","📄"),data.get("content",""),int(data.get("visible",1)),int(data.get("sort_order",0)),pid))
            db.commit()
        return jsonify({"success":True,"id":pid})
    slug = data.get("slug","").strip().replace(" ","-").lower()
    if not slug: return jsonify({"success":False,"error":"Slug requis"})
    try:
        with get_db() as db:
            db.execute("INSERT INTO pages (slug,title,icon,content,visible,sort_order) VALUES (?,?,?,?,1,0)",
                (slug,data.get("title",""),data.get("icon","📄"),data.get("content","")))
            db.commit()
            pid = db.execute("SELECT id FROM pages WHERE slug=?",(slug,)).fetchone()["id"]
        return jsonify({"success":True,"id":pid})
    except: return jsonify({"success":False,"error":"Slug deja utilise"})

@app.route("/admin/delete_page/<int:pid>", methods=["POST"])
def admin_delete_page(pid):
    if not session.get("is_admin"): return jsonify({"success":False})
    with get_db() as db:
        db.execute("DELETE FROM pages WHERE id=?",(pid,)); db.commit()
    return jsonify({"success":True})

@app.route("/upload_model", methods=["POST"])
def upload_model():
    if not ("user_id" in session or session.get("is_admin")):
        return jsonify({"success":False,"error":"Non connecte"})
    if not session.get("can_upload") and not session.get("is_admin"):
        return jsonify({"success":False,"error":"Non autorise"})
    name = request.form.get("model_name","").strip()
    if not name: return jsonify({"success":False,"error":"Nom requis"})
    mf = request.files.get("model_file")
    if not mf or not allowed_model(mf.filename): return jsonify({"success":False,"error":"Fichier .rbxm/.rbxmx requis"})
    mfn = secure_filename(f"{session.get('user_id','admin')}_{mf.filename}")
    mf.save(os.path.join(UPLOAD_DIR, mfn))
    tp = ""
    tf = request.files.get("thumbnail")
    if tf and allowed_image(tf.filename):
        tfn = secure_filename(f"th_{session.get('user_id','admin')}_{tf.filename}")
        tf.save(os.path.join(UPLOAD_DIR, tfn)); tp = tfn
    rp = 0
    price_type = request.form.get("price_type","free")
    if price_type=="paid":
        try: rp = int(request.form.get("price","0"))
        except: pass
    with get_db() as db:
        cur = db.execute("INSERT INTO models (name,description,price_type,price,category,file,thumbnail,author) VALUES (?,?,?,?,?,?,?,?)",
            (name,request.form.get("description",""),price_type,rp,request.form.get("category","Other"),mfn,tp,session.get("username","Admin")))
        db.commit()
        model = dict(db.execute("SELECT * FROM models WHERE id=?",(cur.lastrowid,)).fetchone())
    return jsonify({"success":True,"model":model})

@app.route("/upload_logo", methods=["POST"])
def upload_logo():
    if not session.get("is_admin"): return jsonify({"success":False})
    logo = request.files.get("logo")
    if not logo or not allowed_image(logo.filename): return jsonify({"success":False})
    fn = secure_filename(f"logo_{logo.filename}")
    logo.save(os.path.join(LOGO_DIR, fn)); set_setting("site_logo", fn)
    return jsonify({"success":True,"logo_path":fn})

@app.route("/api/theme")
def api_theme(): return jsonify({"theme":get_setting("theme","dark")})

@app.route("/uploads/models/<path:filename>")
def serve_model(filename): return send_from_directory(UPLOAD_DIR, filename)

@app.route("/uploads/logos/<path:filename>")
def serve_logo(filename): return send_from_directory(LOGO_DIR, filename)

@app.route("/download/<int:mid>")
def download_model(mid):
    with get_db() as db:
        m = db.execute("SELECT * FROM models WHERE id=?",(mid,)).fetchone()
        if not m: return "Introuvable",404
        db.execute("UPDATE models SET downloads=downloads+1 WHERE id=?",(mid,)); db.commit()
    return send_from_directory(UPLOAD_DIR, m["file"], as_attachment=True)

@app.route("/privacy")
def privacy(): return render_template("privacy.html", s=get_all_settings(), pages=get_visible_pages())

@app.route("/terms")
def terms(): return render_template("terms.html", s=get_all_settings(), pages=get_visible_pages())

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
