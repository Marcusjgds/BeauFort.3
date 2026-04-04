from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory
import os, sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "bf_secret_2025")

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads", "models")
LOGO_DIR   = os.path.join(BASE_DIR, "uploads", "logos")
DB_PATH    = os.path.join(BASE_DIR, "database.db")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(LOGO_DIR,   exist_ok=True)

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
        db.execute("""CREATE TABLE IF NOT EXISTS site_settings (
            key TEXT PRIMARY KEY, value TEXT)""")
        for k, v in [("maintenance","0"),("site_closed","0"),
                     ("maintenance_msg","Site en maintenance, revenez bientôt !"),
                     ("site_closed_msg","Le site est temporairement fermé."),
                     ("site_logo","")]:
            db.execute("INSERT OR IGNORE INTO site_settings (key,value) VALUES (?,?)", (k,v))
        db.commit()

init_db()

def get_setting(key, default=""):
    with get_db() as db:
        row = db.execute("SELECT value FROM site_settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key, value):
    with get_db() as db:
        db.execute("INSERT OR REPLACE INTO site_settings (key,value) VALUES (?,?)", (key, value))
        db.commit()

def allowed_model(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_MODELS
def allowed_image(fn): return "." in fn and fn.rsplit(".",1)[1].lower() in ALLOWED_IMAGES

@app.before_request
def check_status():
    if request.path.startswith("/admin") or request.path.startswith("/static") or \
       request.path.startswith("/uploads") or request.path in ["/login", "/logout"]:
        return None
    if get_setting("site_closed") == "1" and not session.get("is_admin"):
        return render_template("closed.html", msg=get_setting("site_closed_msg")), 503
    if get_setting("maintenance") == "1" and not session.get("is_admin"):
        return render_template("maintenance.html", msg=get_setting("maintenance_msg")), 503

@app.route("/")
def index():
    with get_db() as db:
        models = [dict(m) for m in db.execute("SELECT * FROM models ORDER BY created_at DESC").fetchall()]
    return render_template("index.html",
        logged_in  = "user_id" in session,
        username   = session.get("username", ""),
        is_admin   = session.get("is_admin", False),
        can_upload = session.get("can_upload", False),
        models     = models,
        site_logo  = get_setting("site_logo"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", site_logo=get_setting("site_logo"), error=None)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    if not username or not password:
        return render_template("login.html", site_logo=get_setting("site_logo"), error="Pseudo et mot de passe requis.")
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?) AND password=?", (username, password)).fetchone()
    if not user:
        return render_template("login.html", site_logo=get_setting("site_logo"), error="Pseudo ou mot de passe incorrect.")
    session["user_id"]   = user["id"]
    session["username"]  = user["username"]
    session["is_admin"]  = False
    session["can_upload"] = bool(user["can_upload"])
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            session["can_upload"] = True
            session["username"] = "Admin"
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Mot de passe incorrect.", site_logo=get_setting("site_logo"))
    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html", error=None, site_logo=get_setting("site_logo"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("is_admin"):
        return redirect(url_for("admin"))
    with get_db() as db:
        users  = [dict(u) for u in db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()]
        models = [dict(m) for m in db.execute("SELECT * FROM models ORDER BY created_at DESC").fetchall()]
    return render_template("admin_dashboard.html",
        users=users, models=models,
        maintenance=get_setting("maintenance"),
        site_closed=get_setting("site_closed"),
        maintenance_msg=get_setting("maintenance_msg"),
        site_closed_msg=get_setting("site_closed_msg"),
        site_logo=get_setting("site_logo"))

@app.route("/admin/add_user", methods=["POST"])
def admin_add_user():
    if not session.get("is_admin"): return jsonify({"success": False})
    username = request.form.get("username","").strip()
    password = request.form.get("password","").strip()
    can_upload = request.form.get("can_upload","1")
    if not username or not password:
        return jsonify({"success": False, "error": "Pseudo et mot de passe requis"})
    try:
        with get_db() as db:
            db.execute("INSERT INTO users (username,password,can_upload) VALUES (?,?,?)", (username, password, int(can_upload)))
            db.commit()
        return jsonify({"success": True, "username": username})
    except:
        return jsonify({"success": False, "error": "Utilisateur déjà existant"})

@app.route("/admin/remove_user/<int:uid>", methods=["POST"])
def admin_remove_user(uid):
    if not session.get("is_admin"): return jsonify({"success": False})
    with get_db() as db:
        db.execute("DELETE FROM users WHERE id=?", (uid,))
        db.commit()
    return jsonify({"success": True})

@app.route("/admin/delete_model/<int:mid>", methods=["POST"])
def admin_delete_model(mid):
    if not session.get("is_admin"): return jsonify({"success": False})
    with get_db() as db:
        m = db.execute("SELECT * FROM models WHERE id=?", (mid,)).fetchone()
        if m:
            try: os.remove(os.path.join(UPLOAD_DIR, m["file"]))
            except: pass
            if m["thumbnail"]:
                try: os.remove(os.path.join(UPLOAD_DIR, m["thumbnail"]))
                except: pass
        db.execute("DELETE FROM models WHERE id=?", (mid,))
        db.commit()
    return jsonify({"success": True})

@app.route("/admin/settings", methods=["POST"])
def admin_settings():
    if not session.get("is_admin"): return jsonify({"success": False})
    data = request.get_json() or {}
    for key in ["maintenance","site_closed","maintenance_msg","site_closed_msg"]:
        if key in data: set_setting(key, str(data[key]))
    return jsonify({"success": True})

@app.route("/upload_model", methods=["POST"])
def upload_model():
    if "user_id" not in session and not session.get("is_admin"):
        return jsonify({"success": False, "error": "Non connecté"})
    if not session.get("can_upload") and not session.get("is_admin"):
        return jsonify({"success": False, "error": "Tu n'es pas autorisé à publier."})
    name = request.form.get("model_name","").strip()
    desc = request.form.get("description","").strip()
    price_type = request.form.get("price_type","free")
    price = request.form.get("price","0")
    category = request.form.get("category","Other").strip()
    if not name: return jsonify({"success": False, "error": "Nom requis"})
    mf = request.files.get("model_file")
    if not mf or not allowed_model(mf.filename):
        return jsonify({"success": False, "error": "Fichier .rbxm/.rbxmx requis"})
    mfn = secure_filename(f"{session.get('user_id','admin')}_{mf.filename}")
    mf.save(os.path.join(UPLOAD_DIR, mfn))
    tp = ""
    tf = request.files.get("thumbnail")
    if tf and allowed_image(tf.filename):
        tfn = secure_filename(f"thumb_{session.get('user_id','admin')}_{tf.filename}")
        tf.save(os.path.join(UPLOAD_DIR, tfn))
        tp = tfn
    rp = 0
    if price_type == "paid":
        try: rp = int(price)
        except: pass
    with get_db() as db:
        cur = db.execute("INSERT INTO models (name,description,price_type,price,category,file,thumbnail,author) VALUES (?,?,?,?,?,?,?,?)",
            (name,desc,price_type,rp,category,mfn,tp,session.get("username","Admin")))
        db.commit()
        model = dict(db.execute("SELECT * FROM models WHERE id=?", (cur.lastrowid,)).fetchone())
    return jsonify({"success": True, "model": model})

@app.route("/upload_logo", methods=["POST"])
def upload_logo():
    if not session.get("is_admin"): return jsonify({"success": False, "error": "Admin uniquement"})
    logo = request.files.get("logo")
    if not logo or not allowed_image(logo.filename): return jsonify({"success": False, "error": "Image requise"})
    fn = secure_filename(f"logo_{logo.filename}")
    logo.save(os.path.join(LOGO_DIR, fn))
    set_setting("site_logo", fn)
    return jsonify({"success": True, "logo_path": fn})

@app.route("/uploads/models/<path:filename>")
def serve_model(filename): return send_from_directory(UPLOAD_DIR, filename)

@app.route("/uploads/logos/<path:filename>")
def serve_logo(filename): return send_from_directory(LOGO_DIR, filename)

@app.route("/download/<int:model_id>")
def download_model(model_id):
    with get_db() as db:
        m = db.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
        if not m: return "Introuvable", 404
        db.execute("UPDATE models SET downloads=downloads+1 WHERE id=?", (model_id,))
        db.commit()
    return send_from_directory(UPLOAD_DIR, m["file"], as_attachment=True)

@app.route("/privacy")
def privacy(): return render_template("privacy.html", site_logo=get_setting("site_logo"))

@app.route("/terms")
def terms(): return render_template("terms.html", site_logo=get_setting("site_logo"))

if __name__ == "__main__":
    print("→ http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
