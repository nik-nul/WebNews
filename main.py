from flask import Flask, render_template, request, redirect, url_for, flash, session, abort, send_file
from functools import wraps
from datetime import datetime, timedelta
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from bs4 import BeautifulSoup
import requests
import os
import hashlib
from urllib.parse import urlparse
import re
import json
import subprocess
import email.message
import smtplib
import time
import logging

app = Flask(__name__)
app.secret_key = 'A_SECRET_KEY_HERE'
app.permanent_session_lifetime = timedelta(days=7)

EMAIL_ADDRESS = "test@smail.nju.edu.cn"
EMAIL_PASSWORD = "A_SECRET_KEY_HERE"
SMTP_SERVER = "smtp.exmail.qq.com"
SMTP_PORT = 465
SYNC_KEY = "A_SYNC_KEY_HERE"

def sync_entry_to_platform(entry_id, lecture_data_json, secret_key=SYNC_KEY):
    try:
        lecture_data = json.loads(lecture_data_json)

        sync_data = {
            "secret_key": secret_key,
            "id": f"lecture_{entry_id}",
            "title": lecture_data.get("title", {}).get("primary", ""),
            "teacher": "",
            "classroom": lecture_data.get("venue", ""),
            "department": lecture_data.get("organizer", ""),
            "date": lecture_data.get("schedule", {}).get("date", ""),
            "startTime": lecture_data.get("schedule", {}).get("start_time", ""),
            "endTime": lecture_data.get("schedule", {}).get("end_time", ""),
            "info": lecture_data.get("abstract", ""),
            "special": lecture_data.get("registration", ""),
            "other": lecture_data.get("target_audience", ""),
            "imgUrl": "",
            "tags": []
        }

        speakers = lecture_data.get("speakers", [])
        if speakers:
            teacher_names = []
            for speaker in speakers:
                name = speaker.get("name", "")
                title = speaker.get("title", "")
                if name:
                    if title:
                        teacher_names.append(f"{name}（{title}）")
                    else:
                        teacher_names.append(name)
            sync_data["teacher"] = "、".join(teacher_names)

        other_info = []
        if sync_data["other"]:
            other_info.append(f"面向人群: {sync_data['other']}")

        discussants = lecture_data.get("discussants", [])
        if discussants:
            discussant_names = [d.get("name", "") for d in discussants if d.get("name")]
            if discussant_names:
                other_info.append(f"与谈人: {', '.join(discussant_names)}")

        moderator = lecture_data.get("moderator", {})
        if moderator.get("name"):
            other_info.append(f"主持人: {moderator['name']}")

        inviter = lecture_data.get("inviter", {})
        if inviter.get("name"):
            other_info.append(f"邀请人: {inviter['name']}")

        online_access = lecture_data.get("online_access", "")
        if online_access:
            other_info.append(f"线上参与: {online_access}")

        sync_data["other"] = "; ".join(other_info)

        response = requests.post(
            "https://lecture.idealclover.cn/createOrUpdate",
            json=sync_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )

        if response.status_code == 200:
            return True, f"条目 {entry_id} 同步成功"
        else:
            return False, f"条目 {entry_id} 同步失败，HTTP状态码: {response.status_code}"

    except json.JSONDecodeError:
        return False, f"条目 {entry_id} lecture_data格式错误"
    except requests.RequestException as e:
        return False, f"条目 {entry_id} 网络请求失败: {str(e)}"
    except Exception as e:
        return False, f"条目 {entry_id} 同步异常: {str(e)}"


def fetch_title(url):
    for _ in range(2):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            with requests.get(url, headers=headers, stream=True, timeout=5) as response:
                response.raise_for_status()
                partial_content = ""
                for chunk in response.iter_content(chunk_size=4096):
                    partial_content += chunk.decode('utf-8', errors='replace')
                    if "</head>" in partial_content.lower():
                        soup = BeautifulSoup(partial_content, 'html.parser')
                        meta_tag = soup.find("meta", property="og:title")
                        if meta_tag and meta_tag.get("content"):
                            return meta_tag.get("content")
                        title_tag = soup.find("title")
                        if title_tag and title_tag.string:
                            return title_tag.string.strip()
            soup = BeautifulSoup(partial_content, 'html.parser')
            meta_tag = soup.find("meta", property="og:title")
            if meta_tag and meta_tag.get("content"):
                return meta_tag.get("content")
        except Exception as e:
            pass
    return "标题获取失败"

EDITOR_LIST = ["editor1", "editor2"]
ADMIN_LIST = ["admin1", "admin2"]

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

LINK_REGEX = re.compile(r"(https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)?)")

def allowed_file(filename):
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def hash_file(file_obj):
    file_obj.seek(0)
    file_content = file_obj.read()
    file_hash = hashlib.md5(file_content).hexdigest()
    file_obj.seek(0)
    return file_hash

def is_valid_url(url):
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False

def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL)''')

    c.execute('''CREATE TABLE IF NOT EXISTS entries
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  uploader TEXT NOT NULL,
                  upload_time TIMESTAMP NOT NULL,
                  title TEXT NOT NULL,
                  link TEXT,
                  description TEXT,
                  describer TEXT,
                  reviewer TEXT,
                  due_time TIMESTAMP,
                  status TEXT,
                  type TEXT,
                  locked_by TEXT,
                  lock_time TIMESTAMP,
                  use_image INTEGER DEFAULT 0,
                  publish_date TIMESTAMP DEFAULT NULL,
                  tag TEXT,
                  short_title TEXT,
                  lecture_data TEXT,
                  priority INTEGER DEFAULT 0)''')

    try:
        c.execute("ALTER TABLE entries ADD COLUMN use_image INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN publish_date TIMESTAMP DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN tag TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN short_title TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN lecture_data TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        c.execute("ALTER TABLE entries ADD COLUMN priority INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] not in ADMIN_LIST:
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function

def editor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session or session['username'] not in EDITOR_LIST:
            return abort(401)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session.permanent = True
            session['username'] = username
            return redirect(url_for('main'))
        else:
            flash('Invalid username or password')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@admin_required
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                     (username, generate_password_hash(password)))
            conn.commit()
            flash('Registration successful')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists')
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/')
@login_required
def main():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    cutoff = datetime.now() - timedelta(minutes=15)
    c.execute("UPDATE entries SET locked_by=NULL, lock_time=NULL WHERE lock_time IS NOT NULL AND lock_time < ?", (cutoff,))
    conn.commit()

    status_filter = request.args.get('status', 'all').strip()
    order = request.args.get('order', 'desc').strip()
    if order not in ('asc', 'desc'):
        order = 'desc'
    order_sql = 'ASC' if order == 'asc' else 'DESC'
    allowed_statuses = ('pending', 'described', 'modified', 'approved', 'Approved')
    if status_filter in allowed_statuses:
        c.execute(f"SELECT * FROM entries WHERE publish_date IS NULL AND status=? ORDER BY upload_time {order_sql}", (status_filter,))
        entries = c.fetchall()
        total_count = len(entries)
    elif status_filter == 'none':
        status_filter = 'none'
        c.execute(f"SELECT * FROM entries WHERE publish_date IS NULL ORDER BY upload_time {order_sql}")
        entries = c.fetchall()
        total_count = len(entries)
    else:
        status_filter = 'all'
        c.execute(f"SELECT * FROM entries WHERE publish_date IS NULL ORDER BY upload_time {order_sql}")
        entries = c.fetchall()
        total_count = len(entries)
    conn.close()
    return render_template('main.html', entries=entries, status_filter=status_filter, total_count=total_count, order=order)

@app.route('/stats')
@login_required
def stats():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    five_days_ago = datetime.now() - timedelta(days=5)
    c.execute("SELECT uploader, COUNT(*) AS count FROM entries WHERE upload_time >= ? GROUP BY uploader ORDER BY count DESC LIMIT 20", (five_days_ago,))
    uploader_stats = c.fetchall()
    c.execute("SELECT describer, COUNT(*) AS count FROM entries WHERE upload_time >= ? AND describer IS NOT NULL GROUP BY describer ORDER BY count DESC LIMIT 20", (five_days_ago,))
    describer_stats = c.fetchall()
    c.execute("SELECT reviewer, COUNT(*) AS count FROM entries WHERE upload_time >= ? AND reviewer IS NOT NULL GROUP BY reviewer ORDER BY count DESC LIMIT 20", (five_days_ago,))
    reviewer_stats = c.fetchall()
    conn.close()
    return render_template('stats.html', uploader_stats=uploader_stats, describer_stats=describer_stats, reviewer_stats=reviewer_stats)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        due_time = request.form['due_time']
        entry_type = request.form['entry_type']
        tag = request.form.get('tag')
        short_title = request.form.get('short_title') or title
        try:
            priority = int(request.form.get('priority', 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        link = request.form.get('link') or None
        lecture_data = request.form.get('lecture_data') or None
        use_image = 1 if request.form.get('use_image') == 'on' else 0
        
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("""INSERT INTO entries 
                    (uploader, describer, upload_time, title, short_title, description, due_time, status, type, tag, priority, link, lecture_data, use_image)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                 (session['username'], session['username'], datetime.now(), title, short_title, description, due_time, 'described', entry_type, tag, priority, link, lecture_data, use_image))
        new_id = c.lastrowid
        conn.commit()
        conn.close()
        if request.form.get('format') == 'json':
            return json.dumps({"ok": True, "id": new_id}, ensure_ascii=False), 200, {'Content-Type': 'application/json; charset=utf-8'}
        return redirect(url_for('main'))

    return render_template('upload.html')

@app.route('/describe/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def describe(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        entry_type = request.form['entry_type']
        description = request.form['description']
        due_time = request.form['due_time'] or None
        use_image = 1 if request.form.get('use_image') == 'on' else 0
        tag = request.form.get('tag')
        short_title = request.form.get('short_title') or title
        lecture_data = request.form.get('lecture_data')
        try:
            priority = int(request.form.get('priority', 0) or 0)
        except (TypeError, ValueError):
            priority = 0

        c.execute("""UPDATE entries
                    SET title=?, short_title=?, due_time=?, description=?, describer=?, status=?, type=?, use_image=?, tag=?, lecture_data=?, priority=?
                    WHERE id=?""",
                 (title, short_title, due_time, description, session['username'], 'described', entry_type, use_image, tag, lecture_data, priority, entry_id))

        c.execute("UPDATE entries SET locked_by=NULL, lock_time=NULL WHERE id=?", (entry_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('main'))
    else:
        c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
        entry = c.fetchone()

        c.execute("SELECT locked_by, lock_time FROM entries WHERE id=?", (entry_id,))
        lock_info = c.fetchone()
        if lock_info and lock_info[0] and lock_info[0] != session['username']:
            lock_time = datetime.strptime(lock_info[1], "%Y-%m-%d %H:%M:%S.%f") if lock_info[1] else None
            if lock_time and datetime.now() - lock_time < timedelta(minutes=15):
                flash("该条目正被其他人编辑")
                conn.close()
                return redirect(url_for('main'))

        c.execute("UPDATE entries SET locked_by=?, lock_time=? WHERE id=?", (session['username'], datetime.now(), entry_id))
        conn.commit()
        conn.close()
        return render_template('describe.html', entry=entry)

@app.route('/review/<int:entry_id>', methods=['GET', 'POST'])
@login_required
def review(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        action = request.form['action']

        c.execute("SELECT * FROM entries WHERE ID=?", (entry_id,))
        entry = c.fetchone()

        modified_entry = list(entry)
        modified_entry[3] = request.form.get('title', entry[3])
        modified_entry[5] = request.form.get('description', entry[5])
        modified_entry[8] = request.form.get('due_time', entry[8])
        modified_entry[10] = request.form.get('entry_type', entry[10])
        modified_entry[15] = request.form.get('tag', entry[15])
        try:
            _req_pri = int(request.form.get('priority', 0) or 0)
        except (TypeError, ValueError):
            _req_pri = 0
        if len(modified_entry) > 18:
            modified_entry[18] = _req_pri
        else:
            while len(modified_entry) < 18:
                modified_entry.append(None)
            modified_entry.append(_req_pri)

        if (session['username'] == entry[6] or session['username'] == entry[7]) and action != "modify":
            flash("不可通过自己所写的内容！")
            conn.close()
            return render_template('review.html', entry=modified_entry)

        title = request.form['title']
        due_time = request.form['due_time']
        description = request.form['description']
        entry_type = request.form['entry_type']
        use_image = 1 if request.form.get('use_image') == 'on' else 0
        tag = request.form.get('tag')
        short_title = request.form.get('short_title')
        lecture_data = request.form.get('lecture_data')
        try:
            priority = int(request.form.get('priority', 0) or 0)
        except (TypeError, ValueError):
            priority = 0
        _old_pri = entry[18] if len(entry) > 18 and entry[18] is not None else 0
        unchanged = (title == entry[3] and
                     due_time == entry[8] and
                     description == entry[5] and
                     entry_type == entry[10] and
                     use_image == entry[13] and
                     tag == entry[15] and
                     short_title == entry[16] and
                     priority == _old_pri)

        if action == 'approve':
            if not unchanged:
                flash("内容已作出修改，无法 approve")
                conn.close()
                return render_template('review.html', entry=modified_entry)

            c.execute("UPDATE entries SET reviewer=?, status=?, short_title=?, tag=?, lecture_data=?, priority=? WHERE id=?",
                     (session['username'], 'approved', short_title, tag, lecture_data, priority, entry_id))
        else:

            c.execute("UPDATE entries SET title=?, short_title=?, due_time=?, description=?, reviewer=?, status=?, type=?, use_image=?, tag=?, lecture_data=?, priority=? WHERE id=?",
                      (title, short_title, due_time, description, session['username'], 'modified', entry_type, use_image, tag, lecture_data, priority, entry_id))

        c.execute("UPDATE entries SET locked_by=NULL, lock_time=NULL WHERE id=?", (entry_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('main'))
    else:
        c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
        entry = c.fetchone()

        c.execute("SELECT locked_by, lock_time FROM entries WHERE id=?", (entry_id,))
        lock_info = c.fetchone()
        if lock_info and lock_info[0] and lock_info[0] != session['username']:
            lock_time = datetime.strptime(lock_info[1], "%Y-%m-%d %H:%M:%S.%f") if lock_info[1] else None
            if lock_time and datetime.now() - lock_time < timedelta(minutes=15):
                flash("该条目正被其他人编辑")
                conn.close()
                return redirect(url_for('main'))

        c.execute("UPDATE entries SET locked_by=?, lock_time=? WHERE id=?", (session['username'], datetime.now(), entry_id))
        conn.commit()
        conn.close()
        return render_template('review.html', entry=entry)

@app.route('/cancel/<int:entry_id>')
@login_required
def cancel(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT locked_by FROM entries WHERE id=?", (entry_id,))
    entry_lock_info = c.fetchone()
    if entry_lock_info and entry_lock_info[0] == session['username']:
        c.execute("UPDATE entries SET locked_by=NULL, lock_time=NULL WHERE id=?", (entry_id,))
        conn.commit()
    conn.close()
    return redirect(url_for('main'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        original_password = request.form.get('original_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        if new_password != confirm_password:
            flash("New passwords do not match")
            return redirect(url_for('change_password'))
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=?", (session['username'],))
        user = c.fetchone()
        if user and check_password_hash(user[2], original_password):
            c.execute("UPDATE users SET password=? WHERE username=?", (generate_password_hash(new_password), session['username']))
            conn.commit()
            flash("Password successfully updated. Please log in again.")
            session.pop('username', None)
            conn.close()
            return redirect(url_for('login'))
        else:
            flash("Original password is incorrect")
            conn.close()
        return redirect(url_for('change_password'))
    return render_template('change_password.html')

@app.route('/paste', methods=['POST'])
@login_required
def paste():
    link = request.form['link'].strip()
    if not link or not is_valid_url(link):
        flash('请输入有效的地址')
        return redirect(url_for('main'))
    parsed = urlparse(link)
    canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id FROM entries WHERE link=?", (canonical_url,))
    if c.fetchone():
        conn.close()
        flash("该链接已经上传")
        return redirect(url_for('main'))
    title = fetch_title(link)
    print(title)
    c.execute("""INSERT INTO entries
                (uploader, upload_time, title, link, due_time, status, type)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
              (session['username'], datetime.now(), title, canonical_url, None, 'pending', '活动预告'))
    conn.commit()
    conn.close()
    flash('地址添加成功')
    return redirect(url_for('main'))

@app.route('/batch_upload_links', methods=['GET', 'POST'])
@login_required
def batch_upload_links():
    if request.method == 'POST':
        links_text = request.form.get('links', '')
        links = [line.strip() for line in links_text.split('\n') if line.strip()]
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        success_count = 0
        skip_count = 0
        for link in links:
            if not is_valid_url(link):
                continue
            parsed = urlparse(link)
            canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            c.execute("SELECT id FROM entries WHERE link=?", (canonical_url,))
            if c.fetchone():
                skip_count += 1
                continue
            title = fetch_title(link)
            c.execute("""INSERT INTO entries
                        (uploader, upload_time, title, link, due_time, status, type)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""",
                      (session['username'], datetime.now(), title, canonical_url, None, 'pending', '活动预告'))
            success_count += 1
        conn.commit()
        conn.close()
        msg = f'批量处理完成：成功添加了 {success_count} 个地址'
        if skip_count > 0:
            msg += f'，跳过了 {skip_count} 个已存在的地址'
        flash(msg)
        return redirect(url_for('main'))
    return render_template('batch_upload_links.html')

@app.route('/batch_upload_invalid_links', methods=['GET', 'POST'])
@editor_required
def batch_upload_invalid_links():
    if request.method == 'POST':
        links_text = request.form.get('links', '')
        links = [line.strip() for line in links_text.split('\n') if line.strip()]
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        success_count = 0
        skip_count = 0
        invalid_date = datetime(1970, 1, 1)
        for link in links:
            if not is_valid_url(link):
                continue
            parsed = urlparse(link)
            canonical_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            c.execute("SELECT id FROM entries WHERE link=?", (canonical_url,))
            if c.fetchone():
                skip_count += 1
                continue
            title = fetch_title(link)
            c.execute("""INSERT INTO entries
                        (uploader, upload_time, title, link, due_time, status, type, describer)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                      (session['username'], datetime.now(), "【无效】"+title, canonical_url, None, 'described', '活动预告', session['username']))
            entry_id = c.lastrowid
            success_count += 1
            c.execute("UPDATE entries SET publish_date=? WHERE id=?", (invalid_date, entry_id))

        conn.commit()
        conn.close()
        msg = f'批量无效化完成：新上传了 {success_count} 个地址并标为无效'
        if skip_count > 0:
            msg += f'，跳过了 {skip_count} 个已存在的地址'
        flash(msg)
        return redirect(url_for('main'))
    return render_template('batch_upload_invalid_links.html')

@app.route('/upload_image', methods=['POST'])
@login_required
def upload_image():
    if 'image' not in request.files:
        flash("没有文件上传")
        return redirect(url_for('main'))
    file = request.files['image']
    if file.filename == '':
        flash("未选择文件")
        return redirect(url_for('main'))
    if file and allowed_file(file.filename):
        extension = file.filename.rsplit('.', 1)[1].lower()
        file_hash = hash_file(file)
        filename = f"{file_hash}.{extension}"
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id FROM entries WHERE link=?", (filename,))
        if c.fetchone():
            conn.close()
            flash("该图片已经上传")
            return redirect(url_for('main'))
        conn.close()
        upload_folder = os.path.join(app.root_path, 'static/uploads')
        os.makedirs(upload_folder, exist_ok=True)
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        dynamic_img_url = url_for('static', filename='uploads/' + filename, _external=True)
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("""INSERT INTO entries
                     (uploader, upload_time, title, link, due_time, status, type)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (session['username'], datetime.now(), file.filename, filename, None, 'pending', '活动预告'))
        conn.commit()
        conn.close()
        flash("图片上传成功，并已添加到条目, 图片链接：<a href='" + dynamic_img_url + "' target='_blank'>" + dynamic_img_url + "</a>")
        return redirect(url_for('main'))
    else:
        flash("不支持的文件格式")
        return redirect(url_for('main'))

@app.route('/admin')
@editor_required
def admin():
    page = request.args.get('page', default=1, type=int)
    page_size = 25
    offset = (page - 1) * page_size
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM entries")
    total_count = c.fetchone()[0]
    total_pages = (total_count + page_size - 1) // page_size
    c.execute("SELECT * FROM entries ORDER BY upload_time DESC LIMIT ? OFFSET ?", (page_size, offset))
    entries = c.fetchall()
    conn.close()
    default_publish_date = get_beijing_date_str()
    return render_template('admin.html', entries=entries, page=page, total_pages=total_pages, default_publish_date=default_publish_date)

@app.route('/admin/edit/<int:entry_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    if request.method == 'POST':
        uploader = request.form['uploader']
        upload_time = request.form['upload_time']
        title = request.form['title']
        link = request.form['link']
        description = request.form['description']
        describer = request.form['describer']
        reviewer = request.form['reviewer']
        due_time = request.form['due_time']
        status = request.form['status']
        entry_type = request.form['entry_type']
        c.execute("""UPDATE entries SET uploader=?, upload_time=?, title=?, link=?, description=?, describer=?, reviewer=?, due_time=?, status=?, type=? WHERE id=?""",
                  (uploader, upload_time, title, link, description, describer, reviewer, due_time, status, entry_type, entry_id))
        conn.commit()
        conn.close()
        flash("条目已更新")
        return redirect(url_for('admin'))
    else:
        c.execute("SELECT * FROM entries WHERE id=?", (entry_id,))
        entry = c.fetchone()
        conn.close()
        return render_template('admin_edit.html', entry=entry)

@app.route('/admin/delete/<int:entry_id>', methods=['POST'])
@admin_required
def admin_delete(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    flash("条目已删除")
    return redirect(url_for('admin'))

@app.route('/admin/publish', methods=['POST'])
@editor_required
def admin_publish():
    entry_ids = request.form.getlist("entry_ids")
    publish_time_input = request.form.get("publish_time")

    if not entry_ids:
        flash("请至少选择一个条目")
        return redirect(url_for('admin'))

    try:
        publish_time = datetime.strptime(publish_time_input, "%Y-%m-%d")
    except (ValueError, TypeError):
        publish_time = datetime.now()

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    sync_results = []

    try:
        for eid in entry_ids:
            c.execute("UPDATE entries SET publish_date=? WHERE id=?", (publish_time, eid))

            c.execute("SELECT lecture_data FROM entries WHERE id=?", (eid,))
            result = c.fetchone()

            if result and result[0]:
                lecture_data = result[0]
                success, message = sync_entry_to_platform(eid, lecture_data)
                sync_results.append(message)

                if not success:
                    logging.warning(f"同步失败: {message}")
            else:
                sync_results.append(f"条目 {eid} 缺少lecture_data，跳过同步")

        conn.commit()

        flash("选定条目的发布时间已更新")

        success_count = sum(1 for msg in sync_results if "同步成功" in msg)
        total_count = len(entry_ids)

        if success_count == total_count:
            flash(f"所有 {total_count} 个条目同步成功")
        elif success_count > 0:
            flash(f"{success_count}/{total_count} 个条目同步成功，部分同步失败")
        else:
            flash("所有条目同步失败，请检查网络连接或联系管理员")

        for msg in sync_results:
            if "同步失败" in msg or "异常" in msg:
                flash(msg, category='warning')

    except Exception as e:
        conn.rollback()
        flash(f"发布过程中出现错误: {str(e)}")
        logging.error(f"发布错误: {str(e)}")
    finally:
        conn.close()

    return redirect(url_for('admin'))
@app.route('/admin/publish_today', methods=['POST'])
@editor_required
def admin_publish_today():
    publish_time = datetime.now().date()
    today = datetime.now().date()
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("UPDATE entries SET publish_date=? WHERE date(upload_time)=?", (publish_time, today))
    conn.commit()
    conn.close()
    flash("今天上传的条目的发布时间已更新")
    return redirect(url_for('admin'))

@app.route('/admin/unpublish', methods=['POST'])
@editor_required
def admin_unpublish():
    entry_ids = request.form.getlist("entry_ids")
    if not entry_ids:
        flash("请至少选择一个条目")
        return redirect(url_for('admin'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    for eid in entry_ids:
        c.execute("UPDATE entries SET publish_date=NULL WHERE id=?", (eid,))
    conn.commit()
    conn.close()
    flash("选定条目已取消发布")
    return redirect(url_for('admin'))

@app.route('/admin/make_invalid', methods=['POST'])
@editor_required
def admin_make_invalid():
    entry_ids = request.form.getlist("entry_ids")
    if not entry_ids:
        flash("请至少选择一个条目")
        return redirect(url_for('admin'))
    invalid_date = datetime(1970, 1, 1)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    for eid in entry_ids:
        c.execute("UPDATE entries SET publish_date=? WHERE id=?", (invalid_date, eid))
    conn.commit()
    conn.close()
    flash("选定条目已标记为无效")
    return redirect(url_for('admin'))

@app.route('/admin/user_admin', methods=['GET'])
@admin_required
def user_admin():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username FROM users")
    users = c.fetchall()
    conn.close()
    return render_template('user_admin.html', users=users)

@app.route('/admin/user_edit/<int:user_id>', methods=['GET', 'POST'])
@admin_required
def user_edit(user_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, username FROM users WHERE id=?", (user_id,))
    user = c.fetchone()
    if not user:
        conn.close()
        flash("User not found")
        return redirect(url_for('user_admin'))

    if request.method == 'POST':
        new_password = request.form.get('new_password')
        if not new_password:
            flash("请输入新密码")
            return redirect(url_for('user_edit', user_id=user_id))
        c.execute("UPDATE users SET password=? WHERE id=?", (generate_password_hash(new_password), user_id))
        conn.commit()
        conn.close()
        flash("密码更新成功")
        return redirect(url_for('user_admin'))
    conn.close()
    return render_template('user_edit.html', user=user)

@app.route('/search', methods=['GET'])
@login_required
def search():
    page = request.args.get('page', default=1, type=int)
    page_size = 5
    offset = (page - 1) * page_size
    query = request.args.get('q', '').strip()
    results = []
    total_pages = 0

    if query:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        like_query = f'%{query}%'
        c.execute("SELECT COUNT(*) FROM entries WHERE title LIKE ? OR description LIKE ?", (like_query, like_query))
        total_count = c.fetchone()[0]
        total_pages = (total_count + page_size - 1) // page_size

        c.execute("""SELECT * FROM entries
                     WHERE title LIKE ? OR description LIKE ?
                     ORDER BY upload_time DESC
                     LIMIT ? OFFSET ?""",
                  (like_query, like_query, page_size, offset))
        results = c.fetchall()
        conn.close()

    return render_template('search.html', query=query, results=results, page=page, total_pages=total_pages)

DEFAULT_SAYING = "謹言慎行"
DEFAULT_LOC = "南京市栖霞区"
DEFAULT_COLUMNS = 4
MIN_COLUMNS = 1
MAX_COLUMNS = 8
MAX_PNG_BYTES = int(30.5 * 1024 * 1024)
DEFAULT_PPI = 300


def get_beijing_date_str(now=None):
    if now is None:
        now = datetime.utcnow() + timedelta(hours=8)
    else:
        pass
    if now.hour < 12:
        d = (now - timedelta(days=1)).date()
    else:
        d = now.date()
    return d.strftime("%Y-%m-%d")


def _read_archived_no_map():
    no_map = {}
    max_no = 0
    arc_dir = os.path.join(app.root_path, 'archived')
    if not os.path.isdir(arc_dir):
        return no_map, max_no
    for fn in os.listdir(arc_dir):
        if not fn.endswith('.json'):
            continue
        fp = os.path.join(arc_dir, fn)
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            no = obj.get('data', {}).get('no')
            date = obj.get('data', {}).get('date')
            if isinstance(no, bool):
                continue
            if isinstance(no, str):
                try:
                    no = int(no)
                except (TypeError, ValueError):
                    continue
            if isinstance(no, int) and no > 0:
                if no > max_no:
                    max_no = no
                if isinstance(date, str) and len(date) >= 8:
                    if date not in no_map or no > no_map[date]:
                        no_map[date] = no
        except Exception:
            continue
    return no_map, max_no


def get_issue_no(date_str):
    no_map, max_no = _read_archived_no_map()
    if date_str in no_map:
        return no_map[date_str], True
    try:
        if os.path.exists(os.path.join(app.root_path, 'latest.json')):
            with open(os.path.join(app.root_path, 'latest.json'), 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if obj.get('data', {}).get('date') == date_str:
                no = obj['data'].get('no')
                if isinstance(no, int) and no > 0:
                    return no, True
                if isinstance(no, str):
                    try:
                        return int(no), True
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass
    return (max_no + 1 if max_no else 1), False


def _sanitize_columns(raw, fallback=DEFAULT_COLUMNS):
    try:
        if isinstance(raw, bool):
            raise ValueError("bool is not columns")
        v = int(raw)
    except (TypeError, ValueError):
        try:
            return int(fallback)
        except (TypeError, ValueError):
            return DEFAULT_COLUMNS
    return max(MIN_COLUMNS, min(MAX_COLUMNS, v))


def get_columns(date_str):
    arc_fp = os.path.join(app.root_path, 'archived', date_str + '.json')
    if os.path.exists(arc_fp):
        try:
            with open(arc_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            return _sanitize_columns(obj.get('data', {}).get('columns'), fallback=DEFAULT_COLUMNS)
        except Exception:
            pass
    latest_fp = os.path.join(app.root_path, 'latest.json')
    if os.path.exists(latest_fp):
        try:
            with open(latest_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if obj.get('data', {}).get('date') == date_str:
                return _sanitize_columns(obj.get('data', {}).get('columns'), fallback=DEFAULT_COLUMNS)
        except Exception:
            pass
    return DEFAULT_COLUMNS


def get_saying_loc(date_str):
    arc_fp = os.path.join(app.root_path, 'archived', date_str + '.json')
    if os.path.exists(arc_fp):
        try:
            with open(arc_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            saying = obj.get('data', {}).get('saying') or DEFAULT_SAYING
            loc = obj.get('data', {}).get('loc') or DEFAULT_LOC
            return saying, loc
        except Exception:
            pass
    latest_fp = os.path.join(app.root_path, 'latest.json')
    if os.path.exists(latest_fp):
        try:
            with open(latest_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            saying = obj.get('data', {}).get('saying') or DEFAULT_SAYING
            loc = obj.get('data', {}).get('loc') or DEFAULT_LOC
            return saying, loc
        except Exception:
            pass
    return DEFAULT_SAYING, DEFAULT_LOC


NOTICE_SIZES = ("huge", "large", "medium")
MAX_NOTICES = 20


def _sanitize_notices(raw):
    out = []
    if not isinstance(raw, list):
        return out
    for n in raw:
        if not isinstance(n, dict):
            continue
        text = str(n.get("text", "") or "").strip()
        if not text:
            continue
        size = n.get("size", "medium")
        if size not in NOTICE_SIZES:
            size = "medium"
        out.append({"text": text, "size": size})
        if len(out) >= MAX_NOTICES:
            break
    return out


def get_notices(date_str):
    arc_fp = os.path.join(app.root_path, 'archived', date_str + '.json')
    if os.path.exists(arc_fp):
        try:
            with open(arc_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            ns = _sanitize_notices(obj.get('data', {}).get('notices'))
            return ns
        except Exception:
            pass
    latest_fp = os.path.join(app.root_path, 'latest.json')
    if os.path.exists(latest_fp):
        try:
            with open(latest_fp, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            if obj.get('data', {}).get('date') == date_str:
                return _sanitize_notices(obj.get('data', {}).get('notices'))
        except Exception:
            pass
    return []


def _parse_notices(form):
    texts = form.getlist("notice_text")
    sizes = form.getlist("notice_size")
    raw = [{"text": t, "size": s} for t, s in zip(texts, sizes)]
    return _sanitize_notices(raw)


def _typst_base_command():
    cmd = ["./typst", "compile", "--pdf-standard", "2.0"]
    return cmd


def compile_pdf(json_path, typ_path, pdf_path, timeout=180):
    cmd = _typst_base_command() + [typ_path, pdf_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return result


def compile_png_adaptive(typ_path, out_base, requested_ppi=DEFAULT_PPI, timeout=300):
    import glob as _glob
    import math as _math

    try:
        requested_ppi = int(requested_ppi)
    except (TypeError, ValueError):
        requested_ppi = DEFAULT_PPI
    R = max(40, min(600, requested_ppi))
    LOW, PROBE, PREC = 40, 250, 5
    tried = []
    cache = {}

    def _clean():
        single = out_base if out_base.endswith('.png') else out_base + '.png'
        try:
            if os.path.exists(single):
                os.remove(single)
        except Exception:
            pass
        for old in _glob.glob(out_base + '-*.png'):
            try:
                os.remove(old)
            except Exception:
                pass
        return single

    def _once(ppi):
        if ppi in cache:
            return cache[ppi]
        single = _clean()
        cmd = _typst_base_command() + ["--pages", "1", "--ppi", str(int(ppi)), typ_path, single]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            tried.append((ppi, 'timeout'))
            cache[ppi] = ('timeout', None, None)
            return cache[ppi]
        if r.returncode == 0 and os.path.exists(single):
            size = os.path.getsize(single)
            tried.append((ppi, size))
            cache[ppi] = ('ok', size, single)
            return cache[ppi]
        tried.append((ppi, 'compile-fail'))
        cache[ppi] = ('fail', None, None)
        return cache[ppi]

    def _fits(ppi):
        st, size, _ = _once(ppi)
        return st == 'ok' and size is not None and size <= MAX_PNG_BYTES

    def _size(ppi):
        st, size, _ = _once(ppi)
        return size if st == 'ok' else None

    def _round5(x):
        return int(round(x / PREC) * PREC)

    def _estimate(lo, s_lo, hi, s_hi):
        try:
            if s_lo is None or s_hi is None:
                return None
            if not (s_lo <= MAX_PNG_BYTES < s_hi):
                return None
            if s_hi <= s_lo:
                return None
            denom = hi * hi - lo * lo
            if denom <= 0:
                return None
            a = (s_hi - s_lo) / denom
            if a <= 0:
                return None
            b = s_lo - a * lo * lo
            if MAX_PNG_BYTES <= b:
                return None
            p_est = _math.sqrt((MAX_PNG_BYTES - b) / a)
            p_est = _round5(p_est)
            if p_est <= lo or p_est >= hi:
                return None
            return p_est
        except Exception:
            return None

    def _bisect(lo, s_lo, hi, s_hi):
        guard = 0
        while hi - lo > PREC and guard < 20:
            guard += 1
            est = _estimate(lo, s_lo, hi, s_hi)
            if est is None:
                mid = _round5((lo + hi) / 2)
            else:
                mid = est
            if mid <= lo:
                mid = lo + PREC
            elif mid >= hi:
                mid = hi - PREC
            mid = _round5(mid)
            if mid <= lo:
                mid = lo + PREC
            if mid >= hi:
                mid = hi - PREC
                mid = _round5(mid)
            if mid <= lo or mid >= hi:
                break
            st, size, _ = _once(mid)
            if st == 'ok' and size is not None and size <= MAX_PNG_BYTES:
                lo, s_lo = mid, size
            else:
                hi = mid
                if st == 'ok' and size is not None:
                    s_hi = size
        return lo

    if _fits(R):
        st, size, path = cache[R]
        single = out_base if out_base.endswith('.png') else out_base + '.png'
        if not os.path.exists(single) and not _glob.glob(out_base + '-*.png'):
            cache.pop(R, None)
            st, size, path = _once(R)
        return R, path, size, tried
    if R <= PROBE:
        if R == LOW:
            st, size, path = cache[R]
            return LOW, path, size, tried
        st_low, size_low, _ = _once(LOW)
        if st_low != 'ok':
            raise RuntimeError(f"PNG 编译失败：tried={tried}")
        if size_low is not None and size_low > MAX_PNG_BYTES:
            st, size, path = cache[LOW]
            return LOW, path, size, tried
        s_hi = _size(R)
        opt = _bisect(LOW, size_low, R, s_hi)
        cache.pop(opt, None)
        st, size, path = _once(opt)
        return opt, path, size, tried

    st_p, size_p, _ = _once(PROBE)
    if st_p != 'ok':
        st_low, size_low, _ = _once(LOW)
        if st_low != 'ok':
            raise RuntimeError(f"PNG 编译失败：tried={tried}")
        if size_low is not None and size_low > MAX_PNG_BYTES:
            st, size, path = cache[LOW]
            return LOW, path, size, tried
        opt = _bisect(LOW, size_low, PROBE, None)
        cache.pop(opt, None)
        st, size, path = _once(opt)
        return opt, path, size, tried
    if size_p is not None and size_p > MAX_PNG_BYTES:
        st_low, size_low, _ = _once(LOW)
        if st_low != 'ok':
            raise RuntimeError(f"PNG 编译失败：tried={tried}")
        if size_low is not None and size_low > MAX_PNG_BYTES:
            st, size, path = cache[LOW]
            return LOW, path, size, tried
        opt = _bisect(LOW, size_low, PROBE, size_p)
        cache.pop(opt, None)
        st, size, path = _once(opt)
        return opt, path, size, tried
    s_hi = _size(R)
    opt = _bisect(PROBE, size_p, R, s_hi)
    cache.pop(opt, None)
    st, size, path = _once(opt)
    return opt, path, size, tried


def typst(date, saying=None, loc=None, no=None, columns=None, notices=None):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")
    print(date, today_str)
    try:
        c.execute("SELECT priority FROM entries LIMIT 1")
        has_priority = True
    except sqlite3.OperationalError:
        has_priority = False
    if date != today_str:
        if has_priority:
            c.execute("SELECT title, description, link, tag, type, id, priority, upload_time, use_image FROM entries WHERE DATE(publish_date)=? ORDER BY upload_time ASC", (date,))
        else:
            c.execute("SELECT title, description, link, tag, type, id, upload_time, use_image FROM entries WHERE DATE(publish_date)=? ORDER BY upload_time ASC", (date,))
    else:
        if has_priority:
            c.execute("SELECT title, description, link, tag, type, id, priority, upload_time, use_image FROM entries WHERE DATE(publish_date)=? OR publish_date IS NULL ORDER BY upload_time ASC", (date,))
        else:
            c.execute("SELECT title, description, link, tag, type, id, upload_time, use_image FROM entries WHERE DATE(publish_date)=? OR publish_date IS NULL ORDER BY upload_time ASC", (date,))
    rows = c.fetchall()
    conn.close()
    other, college, club, career, lecture  = [], [], [], [], []
    _ref_pending = []
    for row in rows:
        if len(row) == 9:
            title, description, link, tag, sector, num, pri, upload_time, ui = row
        elif len(row) == 8:
            title, description, link, tag, sector, num, upload_time, ui = row
            pri = 0
        else:
            title, description, link, tag, sector, num = row
            pri, upload_time, ui = 0, "", 0
        try:
            pri = int(pri) if pri is not None else 0
        except (TypeError, ValueError):
            pri = 0
        try:
            ui = int(ui) if ui is not None else 0
        except (TypeError, ValueError):
            ui = 0
        if sector == "DDLOnly":
            continue
        try:
            description = re.split(LINK_REGEX, description)
        except:
            continue
        splitted = []
        for e in description:
            if is_valid_url(e):
                splitted.append({"type": "link", "content": e})
            else:
                splitted.append({"type": "text", "content": e})
        description = splitted
        if allowed_file(link):
            image = link if ui == 1 else None
            link = None
        else:
            image = None
        item = {"title": title, "description": description, "link": link, "id": num, "priority": pri, "image": image}
        if sector == "参考消息":
            _ref_pending.append((pri, str(upload_time or ""), item))
        elif(tag == "讲座" or sector == "讲座"):
            lecture.append(item)
        elif(tag == "院级活动"):
            college.append(item)
        elif(tag == "社团活动"):
            club.append(item)
        elif(tag == "招聘升学宣讲"):
            career.append(item)
        else:
            other.append(item)
    _ref_pending.sort(key=lambda t: (-t[0], t[1]))
    reference = [t[2] for t in _ref_pending]
    if saying is None or loc is None:
        _d_saying, _d_loc = get_saying_loc(date)
        if saying is None:
            saying = _d_saying
        if loc is None:
            loc = _d_loc
    if no is None:
        no, _ = get_issue_no(date)
    else:
        try:
            no = int(no)
        except (TypeError, ValueError):
            no, _ = get_issue_no(date)
    if columns is None:
        columns = get_columns(date)
    else:
        columns = _sanitize_columns(columns, fallback=get_columns(date))
    if notices is None:
        notices = get_notices(date)
    else:
        notices = _sanitize_notices(notices)
    data = {
        "date": date,
        "no": no,
        "saying": saying,
        "loc": loc,
        "columns": columns,
        "college": college,
        "club": club,
        "career": career,
        "lecture": lecture,
        "other": other,
        "reference": reference,
        "notices": notices
    }
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT title, link, tag, due_time, publish_date, short_title, type, id FROM entries WHERE due_time IS NOT NULL AND due_time > ? AND DATE(publish_date) <= ? AND publish_date >= '2023-01-01' AND type != '参考消息' ORDER BY due_time ASC", (date, date))
    due_entries = c.fetchall()
    conn.close()
    other_due, college_due, club_due, career_due, lecture_due  = [], [], [], [], []
    for title, link, tag, due_time, publish_date, short_title, sector, num in due_entries:
        if short_title:
            title = short_title
        if allowed_file(link):
            link = None
        if(tag == "讲座" or sector == "讲座"):
            lecture_due.append({"title": title, "link": link, "due_time": due_time, "publish_date": publish_date[:10], "id": num})
        elif(tag == "院级活动"):
            college_due.append({"title": title, "link": link, "due_time": due_time, "publish_date": publish_date[:10], "id": num})
        elif(tag == "社团活动"):
            club_due.append({"title": title, "link": link, "due_time": due_time, "publish_date": publish_date[:10], "id": num})
        elif(tag == "招聘升学宣讲"):
            career_due.append({"title": title, "link": link, "due_time": due_time, "publish_date": publish_date[:10], "id": num})
        else:
            other_due.append({"title": title, "link": link, "due_time": due_time, "publish_date": publish_date[:10], "id": num})
    due = {
        "college": college_due,
        "club": club_due,
        "career": career_due,
        "lecture": lecture_due,
        "other": other_due
    }

    return {"data": data, "due": due}

@app.route('/typst/<date>')
def typst_pub(date):
    saying = request.args.get('saying') or None
    loc = request.args.get('loc') or None
    no = request.args.get('no') or None
    columns = request.args.get('columns') or None
    return json.dumps(typst(date, saying=saying, loc=loc, no=no, columns=columns), ensure_ascii=False, indent=2), 200, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/api/query', methods=['GET'])
def api_query():
    q = request.args.get('id', type=int)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("""SELECT * FROM entries
                    WHERE id=?""", (q,))
    results = c.fetchall()
    conn.close()
    return json.dumps(results, ensure_ascii=False, indent=2), 200, {'Content-Type': 'application/json; charset=utf-8'}

@app.route('/api/search', methods=['GET'])
def api_search():
    page = request.args.get('page', default=1, type=int)
    page_size = 5
    offset = (page - 1) * page_size
    query = request.args.get('q', '').strip()
    results = []

    if query:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        like_query = f'%{query}%'
        c.execute("""SELECT id FROM entries
                     WHERE title LIKE ? OR description LIKE ?
                     ORDER BY upload_time DESC
                     LIMIT ? OFFSET ?""",
                  (like_query, like_query, page_size, offset))
        results = c.fetchall()
        conn.close()
    return json.dumps(results, ensure_ascii=False, indent=2), 200, {'Content-Type': 'application/json; charset=utf-8'}

@app.route("/preview_edit")
def preview_edit():
    return render_template("preview_edit.html")

@app.route('/latex/<date>')
@login_required
def latex_entries(date):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT title, description, link, tag, describer FROM entries WHERE DATE(publish_date)=? ORDER BY tag ASC", (date,))
    entries = c.fetchall()
    conn.close()

    def escape_latex(text):
        if not text:
            return ""
        text = text.replace('\\', r'\textbackslash{}')
        special_chars = {
            '&': r'\&',
            '%': r'\%',
            '$': r'\$',
            '#': r'\#',
            '_': r'\_',
            '{': r'\{',
            '}': r'\}',
            '~': r'\textasciitilde{}',
            '^': r'\^{}',
        }
        for char, replacement in special_chars.items():
            text = text.replace(char, replacement)
        return text

    latex_output = ""
    for title, description, link, tag, describer in entries:
        title = escape_latex(title)
        title = title.rstrip('\r\n')
        description = escape_latex(description).replace('\n', r'\\')
        if tag in ["讲座", "院级活动", "社团活动", "招聘升学宣讲"]:
            latex_output += r"\subsection{" + title + "} % " + tag + " describer: " + describer + "\n"
        else:
            latex_output += r"\section{" + title + "} % " + tag + " describer: " + describer + "\n"
        latex_output += description + "\n"
        if link and len(link) > 10:
            latex_output += "\\\\详见：" + r"\url{" + link + "}" + "\n\n"
    return latex_output, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/delete/<int:entry_id>', methods=['POST'])
@login_required
def delete_entry(entry_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT uploader FROM entries WHERE id=?", (entry_id,))
    entry = c.fetchone()
    if not entry:
        conn.close()
        flash("条目不存在")
        return redirect(url_for('main'))
    if entry[0] != session['username']:
        conn.close()
        flash("你没有权限删除此条目，仅可删除自己上传的条目")
        return redirect(url_for('main'))
    c.execute("DELETE FROM entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    flash("条目已删除")
    return redirect(url_for('main'))


@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(401)
def page_not_found(e):
    return render_template('401.html'), 401


@app.route('/add_deadline', methods=['GET', 'POST'])
@login_required
def add_deadline():
    if request.method == 'POST':
        link = request.form.get('link', '').strip()
        link_value = link if link else None
        short_title = request.form.get('short_title', '').strip()
        tag = request.form.get('tag', '').strip()
        today = datetime.now().strftime("%Y-%m-%d")
        publish_time = request.form.get('publish_time', today)
        due_time = request.form.get('due_time', today)

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("""INSERT INTO entries
                     (uploader, describer, upload_time, title, link, short_title, description, due_time, publish_date, status, tag, type)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                  (session['username'], session['username'], datetime.now(), short_title, link_value, short_title, '', due_time, publish_time, 'Approved', tag, "DDLOnly"))
        conn.commit()
        conn.close()
        flash("Deadline entry added successfully")
        return redirect(url_for('main'))
    today = datetime.now().strftime("%Y-%m-%d")
    return render_template('add_deadline.html', today=today)

@app.route('/publish', methods=["GET", "POST"])
@editor_required
def publish():
    if request.method == "POST":
        action = request.form.get("action", "preview_pdf")
        if action == "save_raw":
            new_content = request.form.get("content", "")
            try:
                parsed = json.loads(new_content)
            except Exception as e:
                flash(f"JSON 解析失败：{e}")
                return render_template("publish.html", **_publish_context(request.form.get("date") or get_beijing_date_str(), raw_content=new_content))
            date_str = parsed["data"]["date"]
            with open("./latest.json", "w", encoding="utf-8") as f:
                f.write(new_content)
            with open("./archived/" + date_str + ".json", "w", encoding="utf-8") as f:
                f.write(new_content)
            try:
                r = compile_pdf("./latest.json", "news_template.typ", "./static/latest.pdf")
                if r.returncode != 0:
                    flash(f"PDF 编译失败：{(r.stderr or '')[-1000:]}")
                else:
                    try:
                        import shutil as _sh
                        _sh.copyfile("./static/latest.pdf", f"./archived/{date_str}.pdf")
                    except Exception:
                        pass
                    flash(f"已刊发 {date_str}（raw JSON），PDF 已更新")
            except Exception as e:
                flash(f"Compilation failed: {e}")
            return redirect(url_for('publish', date=date_str))
        date_str = (request.form.get("date") or get_beijing_date_str()).strip()
        saying = request.form.get("saying", DEFAULT_SAYING).strip() or DEFAULT_SAYING
        loc = request.form.get("loc", DEFAULT_LOC).strip() or DEFAULT_LOC
        try:
            no = int(request.form.get("no") or 0)
        except (TypeError, ValueError):
            no, _ = get_issue_no(date_str)
        try:
            ppi = int(request.form.get("ppi", DEFAULT_PPI) or DEFAULT_PPI)
        except (TypeError, ValueError):
            ppi = DEFAULT_PPI
        columns = _sanitize_columns(request.form.get("columns"), fallback=get_columns(date_str))
        updates = _save_priorities_from_form(request.form)
        tidied = _auto_tidy_date(date_str)
        issue = typst(date_str, saying=saying, loc=loc, no=no, columns=columns, notices=_parse_notices(request.form))
        content = json.dumps(issue, ensure_ascii=False, indent=2)
        with open("./latest.json", "w", encoding="utf-8") as f:
            f.write(content)
        with open(f"./archived/{date_str}.json", "w", encoding="utf-8") as f:
            f.write(content)
        try:
            r = compile_pdf("./latest.json", "news_template.typ", "./static/latest.pdf")
            if r.returncode != 0:
                flash(f"PDF 编译失败：{(r.stderr or '')[-1000:]}")
                return render_template("publish.html", **_publish_context(date_str, raw_content=content, ppi=ppi, columns=columns))
            try:
                import shutil as _sh
                _sh.copyfile("./static/latest.pdf", f"./archived/{date_str}.pdf")
            except Exception:
                pass
            flash(f"已刊发 {date_str} No.{no}（更新 {updates} 条优先级，整理 {tidied} 条），PDF 已更新")
        except Exception as e:
            flash(f"Compilation failed: {e}")
        return redirect(url_for('publish', date=date_str))
    else:
        date_q = request.args.get('date') or get_beijing_date_str()
        return render_template("publish.html", **_publish_context(date_q))


def _publish_context(date_str, raw_content=None, ppi=None, columns=None):
    no, existed = get_issue_no(date_str)
    saying, loc = get_saying_loc(date_str)
    if columns is None:
        columns = get_columns(date_str)
    else:
        columns = _sanitize_columns(columns, fallback=get_columns(date_str))
    try:
        if os.path.exists("./latest.json"):
            with open("./latest.json", "r", encoding="utf-8") as f:
                _lj = json.load(f)
            if _lj.get("data", {}).get("date") == date_str:
                saying = _lj["data"].get("saying", saying)
                loc = _lj["data"].get("loc", loc)
                columns = _sanitize_columns(_lj["data"].get("columns", columns), fallback=columns)
                try:
                    no = int(_lj["data"].get("no", no))
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    issue = typst(date_str, saying=saying, loc=loc, no=no, columns=columns)
    if raw_content is None:
        raw_content = json.dumps(issue, ensure_ascii=False, indent=2)
    if ppi is None:
        ppi = DEFAULT_PPI
    else:
        try:
            ppi = int(ppi)
        except (TypeError, ValueError):
            ppi = DEFAULT_PPI
    default_date = get_beijing_date_str()
    return {
        "date": date_str,
        "no": no,
        "no_existed": existed,
        "saying": saying,
        "loc": loc,
        "columns": columns,
        "ppi": ppi,
        "issue": issue,
        "content": raw_content,
        "default_date": default_date,
        "max_png_mb": 30.5,
    }


def _save_priorities_from_form(form):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("SELECT id FROM entries")
        valid_ids = {str(r[0]) for r in c.fetchall()}
    except Exception:
        valid_ids = set()
    updates = 0
    for key, val in form.items():
        if key.startswith("priority_"):
            eid = key[len("priority_"):]
            if eid not in valid_ids:
                continue
            try:
                p = int(val or 0)
            except (TypeError, ValueError):
                p = 0
            c.execute("UPDATE entries SET priority=? WHERE id=?", (p, int(eid)))
            updates += 1
    conn.commit()
    conn.close()
    return updates


def _auto_tidy_date(date_str):
    issue = typst(date_str)
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    changed = 0
    for key in ("other", "lecture", "college", "club", "career", "reference"):
        items = issue["data"].get(key) or []
        pris = []
        for m in items:
            try:
                pris.append(int(m.get("priority", 0) or 0))
            except (TypeError, ValueError):
                pris.append(0)
        levels = sorted(set(pris), reverse=True)
        if len(levels) <= 1:
            continue
        remap = {lv: (len(levels) - 1 - i) for i, lv in enumerate(levels)}
        for m, pr in zip(items, pris):
            new_p = remap[pr]
            if new_p != pr:
                c.execute("UPDATE entries SET priority=? WHERE id=?", (new_p, m.get("id")))
                changed += 1
    conn.commit()
    conn.close()
    return changed


@app.route('/publish/png', methods=["POST"])
@editor_required
def publish_png():
    date_str = (request.form.get("date") or get_beijing_date_str()).strip()
    saying = request.form.get("saying", DEFAULT_SAYING).strip() or DEFAULT_SAYING
    loc = request.form.get("loc", DEFAULT_LOC).strip() or DEFAULT_LOC
    try:
        no = int(request.form.get("no") or 0)
    except (TypeError, ValueError):
        no, _ = get_issue_no(date_str)
    try:
        ppi_req = int(request.form.get("ppi", DEFAULT_PPI) or DEFAULT_PPI)
    except (TypeError, ValueError):
        ppi_req = DEFAULT_PPI
    columns = _sanitize_columns(request.form.get("columns"), fallback=get_columns(date_str))
    _save_priorities_from_form(request.form)
    _auto_tidy_date(date_str)
    issue = typst(date_str, saying=saying, loc=loc, no=no, columns=columns, notices=_parse_notices(request.form))
    content = json.dumps(issue, ensure_ascii=False, indent=2)
    with open("./latest.json", "w", encoding="utf-8") as f:
        f.write(content)
    with open(f"./archived/{date_str}.json", "w", encoding="utf-8") as f:
        f.write(content)
    os.makedirs("./static", exist_ok=True)
    out_base = os.path.join(app.root_path, 'static', f'news_{date_str}')
    try:
        actual_ppi, out_path, size, tried = compile_png_adaptive("news_template.typ", out_base, requested_ppi=ppi_req)
    except Exception as e:
        flash(f"PNG 编译失败：{e}")
        return redirect(url_for('publish', date=date_str))
    try:
        import shutil as _sh, glob as _glob
        if os.path.isfile(out_path):
            _sh.copyfile(out_path, f"./archived/{date_str}@ppi{actual_ppi}.png")
            dl_url = url_for('download', kind='news_png', date=date_str)
        else:
            dl_url = '/static/' + os.path.basename(out_path)
    except Exception:
        dl_url = '/static/' + os.path.basename(out_path)
    mb = size / 1024 / 1024
    if size <= MAX_PNG_BYTES:
        flash(f"PNG 已生成：ppi={actual_ppi}（请求 {ppi_req}），大小 {mb:.1f}MB ≤ 30.5MB，tried={tried}，<a href='{dl_url}'>下载</a>")
    else:
        flash(f"PNG 已生成但仍超限：ppi 已降至 {actual_ppi}，大小 {mb:.1f}MB 仍 &gt; 30.5MB，tried={tried}，<a href='{dl_url}'>下载</a>")
    return redirect(url_for('publish', date=date_str))

LECTURE_JSON = "lecture_latest.json"
LECTURE_ARCHIVE_DIR = "archived_lecture"
LECTURE_PDF = "./static/lecture_latest.pdf"


def _lecture_context(date_str, raw_content=None, ppi=None, columns=None):
    if columns is None:
        columns = get_columns(date_str)
    else:
        columns = _sanitize_columns(columns, fallback=get_columns(date_str))
    issue = typst(date_str, columns=columns)
    if raw_content is None:
        raw_content = json.dumps(issue, ensure_ascii=False, indent=2)
    if ppi is None:
        ppi = DEFAULT_PPI
    else:
        try:
            ppi = int(ppi)
        except (TypeError, ValueError):
            ppi = DEFAULT_PPI
    default_date = get_beijing_date_str()
    return {
        "date": date_str,
        "columns": columns,
        "ppi": ppi,
        "issue": issue,
        "content": raw_content,
        "default_date": default_date,
        "max_png_mb": 30.5,
    }


@app.route('/publish_lecture', methods=["GET", "POST"])
@editor_required
def publish_lecture():
    if request.method == "POST":
        action = request.form.get("action", "preview_pdf")
        if action == "save_raw":
            new_content = request.form.get("content", "")
            try:
                parsed = json.loads(new_content)
            except Exception as e:
                flash(f"JSON 解析失败：{e}")
                return render_template("publish_lecture.html", **_lecture_context(request.form.get("date") or get_beijing_date_str(), raw_content=new_content))
            date_str = parsed["data"]["date"]
            os.makedirs(LECTURE_ARCHIVE_DIR, exist_ok=True)
            with open("./" + LECTURE_JSON, "w", encoding="utf-8") as f:
                f.write(new_content)
            with open(f"./{LECTURE_ARCHIVE_DIR}/" + date_str + ".json", "w", encoding="utf-8") as f:
                f.write(new_content)
            try:
                r = compile_pdf("./" + LECTURE_JSON, "lecture_template.typ", LECTURE_PDF)
                if r.returncode != 0:
                    flash(f"PDF 编译失败：{(r.stderr or '')[-1000:]}")
                else:
                    try:
                        import shutil as _sh
                        _sh.copyfile(LECTURE_PDF, f"./{LECTURE_ARCHIVE_DIR}/{date_str}.pdf")
                    except Exception:
                        pass
                    flash(f"已刊发讲座 {date_str}（raw JSON），PDF 已更新")
            except Exception as e:
                flash(f"Compilation failed: {e}")
            return redirect(url_for('publish_lecture', date=date_str))
        date_str = (request.form.get("date") or get_beijing_date_str()).strip()
        try:
            ppi = int(request.form.get("ppi", DEFAULT_PPI) or DEFAULT_PPI)
        except (TypeError, ValueError):
            ppi = DEFAULT_PPI
        columns = _sanitize_columns(request.form.get("columns"), fallback=get_columns(date_str))
        updates = _save_priorities_from_form(request.form)
        tidied = _auto_tidy_date(date_str)
        issue = typst(date_str, columns=columns)
        content = json.dumps(issue, ensure_ascii=False, indent=2)
        os.makedirs(LECTURE_ARCHIVE_DIR, exist_ok=True)
        with open("./" + LECTURE_JSON, "w", encoding="utf-8") as f:
            f.write(content)
        with open(f"./{LECTURE_ARCHIVE_DIR}/{date_str}.json", "w", encoding="utf-8") as f:
            f.write(content)
        try:
            r = compile_pdf("./" + LECTURE_JSON, "lecture_template.typ", LECTURE_PDF)
            if r.returncode != 0:
                flash(f"PDF 编译失败：{(r.stderr or '')[-1000:]}")
                return render_template("publish_lecture.html", **_lecture_context(date_str, raw_content=content, ppi=ppi, columns=columns))
            try:
                import shutil as _sh
                _sh.copyfile(LECTURE_PDF, f"./{LECTURE_ARCHIVE_DIR}/{date_str}.pdf")
            except Exception:
                pass
            flash(f"已刊发讲座 {date_str}（{columns} 列，更新 {updates} 条优先级，整理 {tidied} 条），PDF 已更新")
        except Exception as e:
            flash(f"Compilation failed: {e}")
        return redirect(url_for('publish_lecture', date=date_str))
    else:
        date_q = request.args.get('date') or get_beijing_date_str()
        return render_template("publish_lecture.html", **_lecture_context(date_q))


@app.route('/publish_lecture/png', methods=["POST"])
@editor_required
def publish_lecture_png():
    date_str = (request.form.get("date") or get_beijing_date_str()).strip()
    try:
        ppi_req = int(request.form.get("ppi", DEFAULT_PPI) or DEFAULT_PPI)
    except (TypeError, ValueError):
        ppi_req = DEFAULT_PPI
    columns = _sanitize_columns(request.form.get("columns"), fallback=get_columns(date_str))
    _save_priorities_from_form(request.form)
    _auto_tidy_date(date_str)
    issue = typst(date_str, columns=columns)
    content = json.dumps(issue, ensure_ascii=False, indent=2)
    os.makedirs(LECTURE_ARCHIVE_DIR, exist_ok=True)
    with open("./" + LECTURE_JSON, "w", encoding="utf-8") as f:
        f.write(content)
    with open(f"./{LECTURE_ARCHIVE_DIR}/{date_str}.json", "w", encoding="utf-8") as f:
        f.write(content)
    os.makedirs("./static", exist_ok=True)
    out_base = os.path.join(app.root_path, 'static', f'lecture_{date_str}')
    try:
        actual_ppi, out_path, size, tried = compile_png_adaptive("lecture_template.typ", out_base, requested_ppi=ppi_req)
    except Exception as e:
        flash(f"PNG 编译失败：{e}")
        return redirect(url_for('publish_lecture', date=date_str))
    try:
        import shutil as _sh
        if os.path.isfile(out_path):
            _sh.copyfile(out_path, f"./{LECTURE_ARCHIVE_DIR}/{date_str}@ppi{actual_ppi}.png")
            dl_url = url_for('download', kind='lec_png', date=date_str)
        else:
            dl_url = '/static/' + os.path.basename(out_path)
    except Exception:
        dl_url = '/static/' + os.path.basename(out_path)
    mb = size / 1024 / 1024
    if size <= MAX_PNG_BYTES:
        flash(f"讲座 PNG 已生成：ppi={actual_ppi}（请求 {ppi_req}），大小 {mb:.1f}MB ≤ 30.5MB，tried={tried}，<a href='{dl_url}'>下载</a>")
    else:
        flash(f"讲座 PNG 已生成但仍超限：ppi 已降至 {actual_ppi}，大小 {mb:.1f}MB 仍 &gt; 30.5MB，tried={tried}，<a href='{dl_url}'>下载</a>")
    return redirect(url_for('publish_lecture', date=date_str))


def _dl_filename(kind, date_str):
    y, m, d = date_str.split("-")
    dotted = f"{y}.{m}.{d}"
    short = f"{y[2:]}.{m}.{d}"
    suffix = ".png" if kind.endswith("_png") else ".pdf"
    if kind.startswith("lec_"):
        return f"lec{short}{suffix}"
    return f"南哪消息{dotted}{suffix}"


def _latest_json_date(path):
    try:
        with open(path, encoding='utf-8') as f:
            obj = json.load(f)
        return obj.get('data', {}).get('date')
    except Exception:
        return None


@app.route('/download/<kind>/<date>')
@editor_required
def download(kind, date):
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except (ValueError, TypeError):
        return abort(404)
    if kind == "news_pdf":
        cands = [f"./archived/{date}.pdf"]
        if _latest_json_date("./latest.json") == date:
            cands.append("./static/latest.pdf")
        for cand in cands:
            if os.path.isfile(cand):
                return send_file(os.path.abspath(cand), as_attachment=True, download_name=_dl_filename(kind, date))
    elif kind == "news_png":
        cand = os.path.join(app.root_path, 'static', f'news_{date}.png')
        if os.path.isfile(cand):
            return send_file(cand, as_attachment=True, download_name=_dl_filename(kind, date))
    elif kind == "lec_pdf":
        cands = [f"./{LECTURE_ARCHIVE_DIR}/{date}.pdf"]
        if _latest_json_date("./" + LECTURE_JSON) == date:
            cands.append("./static/lecture_latest.pdf")
        for cand in cands:
            if os.path.isfile(cand):
                return send_file(os.path.abspath(cand), as_attachment=True, download_name=_dl_filename(kind, date))
    elif kind == "lec_png":
        cand = os.path.join(app.root_path, 'static', f'lecture_{date}.png')
        if os.path.isfile(cand):
            return send_file(cand, as_attachment=True, download_name=_dl_filename(kind, date))
    else:
        return abort(404)
    flash(f"该日期尚无{'讲座' if kind.startswith('lec_') else ''}文件，先刊发再下载")
    return redirect(url_for('publish_lecture' if kind.startswith('lec_') else 'publish', date=date))


def read_mailing_list():
    try:
        with open('mailinglist', 'r') as f:
            emails = [line.strip() for line in f.readlines() if line.strip()]
            return emails
    except FileNotFoundError:
        return []

def generate_news_html(date):
    news_data = typst(date)

    toc_html = "<h2>目录</h2><ul>"
    toc_counter = 0

    sections = {
        'other': '校级活动',
        'lecture': '讲座',
        'college': '院级活动',
        'club': '社团活动',
        'career': '招聘升学宣讲'
    }

    for section_key, section_title in sections.items():
        has_news = section_key in news_data['data'] and news_data['data'][section_key]
        has_due = section_key in news_data['due'] and news_data['due'][section_key]

        if has_news or has_due:
            toc_counter += 1
            section_id = f"section-{toc_counter}"
            toc_html += f'<li><a href="#{section_id}">{section_title}</a>'

            if has_news:
                toc_html += '<ul>'
                for i, item in enumerate(news_data['data'][section_key]):
                    item_id = f"{section_id}-item-{i+1}"
                    toc_html += f'<li><a href="#{item_id}">{item["title"]}</a></li>'
                toc_html += '</ul>'

            toc_html += '</li>'

    for _ri, _ritem in enumerate(news_data['data'].get('reference') or []):
        if _ri == 0:
            toc_counter += 1
            _ref_section_id = f"section-{toc_counter}"
            toc_html += f'<li><a href="#{_ref_section_id}">参考消息</a><ul>'
        toc_html += f'<li><a href="#{_ref_section_id}-item-{_ri+1}">{_ritem["title"]}</a></li>'
    if news_data['data'].get('reference'):
        toc_html += '</ul></li>'

    toc_html += "</ul><hr>"

    html_content = f"""<!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <link rel="preload" href="https://nik-nul.github.io/css/news.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
        <noscript><link rel="stylesheet" href="https://nik-nul.github.io/css/news.css"></noscript>
        <title>南哪消息 {date}</title>
    </head>
    <body>
        <h1>南哪消息 {date}</h1>
        <div class="toc">
            {toc_html}
        </div>
    """

    toc_counter = 0
    for section_key, section_title in sections.items():
        has_news = section_key in news_data['data'] and news_data['data'][section_key]
        has_due = section_key in news_data['due'] and news_data['due'][section_key]

        if has_news or has_due:
            toc_counter += 1
            section_id = f"section-{toc_counter}"
            html_content += f'<div class="section"><h2 id="{section_id}">{section_title}</h2>'

            if has_due:
                html_content += '<table><thead><tr><th>活动标题</th><th>截止时间</th><th>刊载时间</th></tr></thead><tbody>'

                for item in news_data['due'][section_key]:
                    link_html = f'<a href="{item["link"]}" target="_blank">{item["title"]}</a>' if item.get('link') else item['title']
                    due_time = item['due_time'][:10] if len(item['due_time']) >= 10 else item['due_time']
                    publish_time = item['publish_date'][:10] if item.get('publish_date') and len(item['publish_date']) >= 10 else item.get('publish_date', '')
                    html_content += f'<tr><td>{link_html}</td><td>{due_time}</td><td>{publish_time}</td></tr>'

                html_content += '</tbody></table>'

            if has_news:
                html_content += '<ul>'

                for i, item in enumerate(news_data['data'][section_key]):
                    item_id = f"{section_id}-item-{i+1}"
                    html_content += f'<li><h3 id="{item_id}">{item["title"]}</h3>'

                    if item.get('link'):
                        html_content += f'原文链接： <a href="{item["link"]}" target="_blank">{item["link"]}</a>'

                    if item.get('description'):
                        desc_html = ""
                        for desc_part in item['description']:
                            if desc_part['type'] == 'text':
                                desc_html += desc_part['content'].replace('\n', '<br>')
                            elif desc_part['type'] == 'link':
                                desc_html += f' <a href="{desc_part["content"]}" target="_blank">{desc_part["content"]}</a>'
                        html_content += f'<br>{desc_html}'
                    if item.get('image'):
                        html_content += '<br>（图片见PDF版第二页）'

                    html_content += '</li>'

                html_content += '</ul>'

            html_content += '</div>'

    _ref_items = news_data['data'].get('reference') or []
    if _ref_items:
        toc_counter += 1
        section_id = f"section-{toc_counter}"
        html_content += f'<div class="section"><h2 id="{section_id}">参考消息</h2><ul>'
        for i, item in enumerate(_ref_items):
            item_id = f"{section_id}-item-{i+1}"
            html_content += f'<li><h3 id="{item_id}">{item["title"]}</h3>'
            if item.get('link'):
                html_content += f'原文链接： <a href="{item["link"]}" target="_blank">{item["link"]}</a>'
            if item.get('description'):
                desc_html = ""
                for desc_part in item['description']:
                    if desc_part['type'] == 'text':
                        desc_html += desc_part['content'].replace('\n', '<br>')
                    elif desc_part['type'] == 'link':
                        desc_html += f' <a href="{desc_part["content"]}" target="_blank">{desc_part["content"]}</a>'
                html_content += f'<br>{desc_html}'
            if item.get('image'):
                html_content += '<br>（图片见PDF版）'
            html_content += '</li>'
        html_content += '</ul></div>'

    for _n in (news_data['data'].get('notices') or []):
        _t = (_n.get('text') or '').strip()
        if _t:
            html_content += f'<hr><p style="text-align:center;font-weight:bold;">{_t}</p>'

    html_content += """
        <hr>
        <p>南哪小报编辑部<br>{}</p>
        <hr>
    </body>
    </html>
    """.format(date)

    return html_content

def send_news_email(date, recipient_list=None):
    if recipient_list is None:
        recipient_list = read_mailing_list()

    if not recipient_list:
        return False, "邮件列表为空"

    html_content = generate_news_html(date)

    msg = email.message.EmailMessage()
    msg["Subject"] = f"南哪消息 {date}"
    msg["From"] = "南哪小报编辑部 <231220103@smail.nju.edu.cn>"
    msg["Bcc"] = ", ".join(recipient_list)
    msg.set_content(html_content, subtype="html")

    for attempt in range(5):
        try:
            with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.send_message(msg)
            return True, f"邮件发送成功，发送给 {len(recipient_list)} 个收件人"
        except Exception as e:
            if attempt == 4:
                return False, f"邮件发送失败: {str(e)}"
            time.sleep(1)

    return False, "邮件发送失败"

@app.route("/preview/<date>")
def preview(date):
    return generate_news_html(date), 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/send_email', methods=['GET', 'POST'])
@admin_required
def send_email():
    if request.method == 'POST':
        date = request.form.get('date')
        if not date:
            flash("请选择日期")
            return redirect(url_for('send_email'))

        success, message = send_news_email(date)
        flash(message)

        if success:
            return redirect(url_for('send_email'))
        else:
            return redirect(url_for('send_email'))

    today = datetime.now().strftime("%Y-%m-%d")
    mailing_list = read_mailing_list()
    return render_template('send_email.html', today=today, mailing_list=mailing_list)


if __name__ == '__main__':
    app.run(host="0.0.0.0", debug=False, port=80)
