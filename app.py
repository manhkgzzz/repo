import os
import json
from datetime import datetime, date, timedelta
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'CHUTICH_VIP_2027_ULTIMATE_KEY'

# --- CẤU HÌNH DATABASE & UPLOAD ---
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ---------------------------------------------------------
# 🗄️ CƠ SỞ DỮ LIỆU CHÍNH
# ---------------------------------------------------------

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False) 
    phone = db.Column(db.String(20), nullable=False)
    fb_link = db.Column(db.String(300))
    avatar = db.Column(db.String(200), default='default_avatar.png')
    
    # Logic Streak & Pomodoro
    streak_count = db.Column(db.Integer, default=0)
    seconds_today = db.Column(db.Integer, default=0)
    last_study_date = db.Column(db.Date, nullable=True)
    
    # MỚI: Tracking IP để phát hiện share acc
    ip_list = db.Column(db.Text, default='[]')
    
    # Phân quyền
    is_admin = db.Column(db.Boolean, default=False)
    is_vip = db.Column(db.Boolean, default=False) 
    is_banned = db.Column(db.Boolean, default=False)

    @property
    def ip_count(self):
        try: return len(json.loads(self.ip_list)) if self.ip_list else 0
        except: return 0

class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    documents = db.relationship('Document', backref='folder', cascade="all, delete-orphan")

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    original_name = db.Column(db.String(255), nullable=True)
    filename = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey('folder.id'), nullable=True)
    note = db.Column(db.Text)        # Ghi chú tài liệu (Vault)
    link = db.Column(db.String(500)) # Link chia sẻ (Vault)
    upload_date = db.Column(db.DateTime, default=datetime.now)

class LibraryDoc(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, nullable=False)
    author_name = db.Column(db.String(100))
    category = db.Column(db.String(50), default="Khác") # MỚI: Phân loại môn học
    is_approved = db.Column(db.Boolean, default=False)
    upload_date = db.Column(db.DateTime, default=datetime.now)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.now)
    lessons = db.relationship('Lesson', backref='course', cascade="all, delete-orphan")

class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    lesson_name = db.Column(db.String(200)) 
    session_num = db.Column(db.String(50))  
    date_text = db.Column(db.String(50))   
    video_link = db.Column(db.String(500))
    material_link = db.Column(db.String(500)) 
    note = db.Column(db.Text)
    notice = db.Column(db.String(200))
    order = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Khởi tạo dữ liệu Admin gốc
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@gmail.com').first():
        admin = User(username='Chủ Tịch Admin', email='admin@gmail.com', password='123', phone='09', is_admin=True, is_vip=True)
        db.session.add(admin); db.session.commit()

# ---------------------------------------------------------
# 🏠 HÀNH CHÍNH & STREAK
# ---------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email']).first()
        if u and u.password == request.form['password']:
            if u.is_banned:
                flash("Tài khoản của ngài đã bị khóa!")
                return redirect(url_for('login'))
            
            # MỚI: Thu thập IP đăng nhập để kiểm tra Share account
            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if client_ip:
                client_ip = client_ip.split(',')[0].strip()
                try: ips = json.loads(u.ip_list) if u.ip_list else []
                except: ips = []
                if client_ip not in ips:
                    ips.append(client_ip)
                    u.ip_list = json.dumps(ips)

            # Xử lý Streak: Kểm tra xem có bị đứt chuỗi không
            today = date.today()
            if u.last_study_date:
                delta = today - u.last_study_date
                if delta.days > 1:
                    u.streak_count = 0 # Nghỉ quá 1 ngày -> Reset chuỗi
            
            # Sang ngày mới thì reset giờ học trong ngày
            if u.last_study_date != today:
                u.seconds_today = 0

            login_user(u)
            db.session.commit()
            return redirect(url_for('index'))
        flash("Sai email hoặc mật khẩu!")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            flash("Email này đã có người sử dụng!")
            return redirect(url_for('register'))
        u = User(username=request.form['username'], email=request.form['email'], 
                 password=request.form['password'], phone=request.form['phone'])
        db.session.add(u); db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user(); return redirect(url_for('login'))

@app.route('/update_time', methods=['POST'])
@login_required
def update_time():
    # Nhận số giây học (từ tiến trình ngầm 10s hoặc từ Pomodoro 1500s)
    data = request.get_json() if request.is_json else {}
    added_seconds = data.get('seconds', 10)
    
    today = date.today()
    if current_user.last_study_date != today:
        current_user.seconds_today = 0
        current_user.last_study_date = today

    current_user.seconds_today += added_seconds
    
    # Nếu VỪA đạt mốc 2 tiếng (7200s) trong lần cộng này -> Tăng streak
    if current_user.seconds_today >= 7200 and (current_user.seconds_today - added_seconds < 7200):
        current_user.streak_count += 1

    db.session.commit()
    return jsonify({'seconds_today': current_user.seconds_today, 'streak_count': current_user.streak_count})

@app.route('/upgrade_vip')
@login_required
def upgrade_vip():
    return render_template('upgrade_vip.html')

# ---------------------------------------------------------
# 👤 PROFILE (HỒ SƠ CÁ NHÂN)
# ---------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.username = request.form.get('username')
        current_user.fb_link = request.form.get('fb_link')
        current_user.phone = request.form.get('phone')
        
        if 'avatar' in request.files:
            file = request.files['avatar']
            if file and file.filename != '':
                fname = f"avatar_{current_user.id}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                current_user.avatar = fname
                
        db.session.commit()
        flash("Đã cập nhật hồ sơ thành công!")
        return redirect(url_for('index'))
    return render_template('profile.html')

# ---------------------------------------------------------
# 🎓 HỆ THỐNG KHÓA HỌC (LỘ TRÌNH VIP)
# ---------------------------------------------------------

@app.route('/courses', methods=['GET', 'POST'])
@login_required
def courses():
    if not current_user.is_vip and not current_user.is_admin:
        flash("Hãy nâng cấp thành viên VIP để truy cập Khóa Học!")
        return redirect(url_for('index'))

    if request.method == 'POST' and current_user.is_admin:
        title = request.form.get('title')
        desc = request.form.get('description')
        if title:
            new_c = Course(title=title, description=desc)
            db.session.add(new_c); db.session.commit()
            flash("Đã tạo khóa học thành công!")
        return redirect(url_for('courses'))
    
    all_courses = Course.query.order_by(Course.created_at.desc()).all()
    return render_template('courses.html', courses=all_courses)

@app.route('/api/get_lessons/<int:course_id>')
@login_required
def get_lessons(course_id):
    if not current_user.is_vip and not current_user.is_admin: return jsonify([])
    lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.id).all()
    
    # Helper: Khử chữ "None" hiển thị trên giao diện
    def clean_val(v): return "" if v is None or str(v).strip().lower() == "none" else v

    return jsonify([{
        'id': l.id, 
        'lesson_name': clean_val(l.lesson_name),
        'session_num': clean_val(l.session_num), 
        'date_text': clean_val(l.date_text), 
        'video_link': clean_val(l.video_link), 
        'material_link': clean_val(l.material_link), 
        'note': clean_val(l.note)
    } for l in lessons])

@app.route('/api/save_lesson', methods=['POST'])
@login_required
def save_lesson():
    if not current_user.is_admin: return jsonify({'error': 'Unauthorized'}), 403
    try:
        l_id = request.form.get('id')
        if l_id and l_id != 'null' and l_id != '':
            lesson = db.session.get(Lesson, int(l_id))
            if not lesson: return jsonify({'error': 'Không tìm thấy buổi học'}), 404
        else:
            lesson = Lesson(course_id=int(request.form.get('course_id')))
            db.session.add(lesson)
        
        lesson.lesson_name = request.form.get('lesson_name', '')
        lesson.session_num = request.form.get('session_num', '')
        lesson.date_text = request.form.get('date_text', '')
        lesson.video_link = request.form.get('video_link', '')
        lesson.note = request.form.get('note', '')
        
        if 'material_file' in request.files:
            file = request.files['material_file']
            if file and file.filename != '':
                fname = f"lesson_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                lesson.material_link = url_for('static', filename='uploads/' + fname)
        
        db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/delete_lesson/<int:lesson_id>', methods=['POST'])
@login_required
def delete_lesson(lesson_id):
    if not current_user.is_admin: return jsonify({'error': 'Unauthorized'}), 403
    lesson = db.session.get(Lesson, lesson_id)
    if lesson:
        db.session.delete(lesson)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'error': 'Không tìm thấy'}), 404

# ---------------------------------------------------------
# 📂 KHO TÀI LIỆU CÁ NHÂN (VAULT)
# ---------------------------------------------------------

@app.route('/vault', defaults={'f_id': 0}, methods=['GET', 'POST'])
@app.route('/vault/<int:f_id>', methods=['GET', 'POST'])
@login_required
def vault(f_id):
    current_f = db.session.get(Folder, f_id) if f_id > 0 else None
    if request.method == 'POST':
        # 1. Tạo thư mục mới
        if 'folder_name' in request.form:
            db.session.add(Folder(name=request.form['folder_name'], user_id=current_user.id))
        
        # 2. Đổi tên thư mục
        elif 'edit_f_id' in request.form:
            f = db.session.get(Folder, request.form['edit_f_id'])
            if f and f.user_id == current_user.id: f.name = request.form['new_name']
        
        # 3. Tải tài liệu lên (hỗ trợ File, Note, Link)
        elif 'is_upload' in request.form:
            note = request.form.get('doc_note', '')
            link = request.form.get('doc_link', '')
            new_doc = Document(user_id=current_user.id, folder_id=f_id if f_id > 0 else None, note=note, link=link)
            
            if 'document' in request.files:
                file = request.files['document']
                if file and file.filename != '':
                    fname = f"doc_{current_user.id}_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
                    new_doc.original_name = file.filename
                    new_doc.filename = fname
            
            if not new_doc.original_name and link:
                new_doc.original_name = "Tài liệu Liên kết (Link)"
                
            db.session.add(new_doc)
            
        db.session.commit(); return redirect(url_for('vault', f_id=f_id))
    
    folders = Folder.query.filter_by(user_id=current_user.id).all() if f_id == 0 else []
    docs = Document.query.filter_by(user_id=current_user.id, folder_id=(f_id if f_id > 0 else None)).all()
    return render_template('vault.html', folders=folders, docs=docs, current_f=current_f)

@app.route('/delete_doc/<int:d_id>')
@login_required
def delete_doc(d_id):
    d = db.session.get(Document, d_id)
    f_id = d.folder_id or 0
    if d and d.user_id == current_user.id:
        if d.filename:
            try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], d.filename))
            except: pass
        db.session.delete(d); db.session.commit()
    return redirect(url_for('vault', f_id=f_id))

@app.route('/vault/del_folder/<int:f_id>')
@login_required
def delete_folder(f_id):
    f = db.session.get(Folder, f_id)
    if f and f.user_id == current_user.id:
        for d in f.documents:
            if d.filename:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], d.filename))
                except: pass
        db.session.delete(f); db.session.commit()
    return redirect(url_for('vault'))

# ---------------------------------------------------------
# 📚 THƯ VIỆN CỘNG ĐỒNG (LIBRARY)
# ---------------------------------------------------------

@app.route('/library', methods=['GET', 'POST'])
@login_required
def library():
    if request.method == 'POST' and 'doc' in request.files:
        file = request.files['doc']
        if file.filename:
            fname = f"lib_{int(datetime.now().timestamp())}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            
            # MỚI: Lấy dữ liệu phân loại từ Form
            category = request.form.get('category', 'Khác')
            
            new_doc = LibraryDoc(title=request.form.get('title'), filename=fname, user_id=current_user.id, author_name=current_user.username, category=category)
            db.session.add(new_doc); db.session.commit()
            flash("Tài liệu đã được gửi và đang chờ phê duyệt!")
            return redirect(url_for('library'))
            
    approved_docs = LibraryDoc.query.filter_by(is_approved=True).order_by(LibraryDoc.upload_date.desc()).all()
    return render_template('library.html', docs=approved_docs)

@app.route('/admin/delete_library_doc/<int:doc_id>')
@login_required
def delete_library_doc(doc_id):
    if not current_user.is_admin: return "Unauthorized", 403
    doc = db.session.get(LibraryDoc, doc_id)
    if doc:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.filename))
        except: pass
        db.session.delete(doc); db.session.commit()
        flash("Đã xóa tài liệu khỏi thư viện!")
    return redirect(url_for('library'))

# ---------------------------------------------------------
# 👑 QUẢN TRỊ VIÊN (ADMIN)
# ---------------------------------------------------------

@app.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin: return "No!", 403
    users_list = User.query.all()
    pending_docs = LibraryDoc.query.filter_by(is_approved=False).all()
    return render_template('admin_users.html', users=users_list, pending_docs=pending_docs)

@app.route('/admin/toggle_vip/<int:user_id>')
@login_required
def toggle_vip(user_id):
    if not current_user.is_admin: return "No!", 403
    u = db.session.get(User, user_id)
    if u: u.is_vip = not u.is_vip; db.session.commit()
    return redirect(url_for('admin_users'))

@app.route('/admin/approve_doc/<int:doc_id>')
@login_required
def approve_doc(doc_id):
    if not current_user.is_admin: return "No!", 403
    doc = db.session.get(LibraryDoc, doc_id)
    if doc: 
        doc.is_approved = True
        db.session.commit()
        flash("Tài liệu đã được duyệt và hiển thị trên Thư viện!")
    return redirect(url_for('admin_users'))

# MỚI: TỪ CHỐI DUYỆT TÀI LIỆU
@app.route('/admin/reject_doc/<int:doc_id>')
@login_required
def reject_doc(doc_id):
    if not current_user.is_admin: return "No!", 403
    doc = db.session.get(LibraryDoc, doc_id)
    if doc:
        try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.filename))
        except: pass
        db.session.delete(doc)
        db.session.commit()
        flash("Đã TỪ CHỐI và dọn dẹp tài liệu!")
    return redirect(url_for('admin_users'))

# MỚI: XÓA VĨNH VIỄN TÀI KHOẢN VÀ DỌN RÁC
@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if not current_user.is_admin: return "No!", 403
    u = db.session.get(User, user_id)
    if u and not u.is_admin: # Không cho Admin tự sát
        # Xóa sạch file trong Vault
        for doc in Document.query.filter_by(user_id=u.id).all():
            if doc.filename:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], doc.filename))
                except: pass
            db.session.delete(doc)
            
        # Xóa sạch file trong Library
        for ldoc in LibraryDoc.query.filter_by(user_id=u.id).all():
            if ldoc.filename:
                try: os.remove(os.path.join(app.config['UPLOAD_FOLDER'], ldoc.filename))
                except: pass
            db.session.delete(ldoc)
        
        db.session.delete(u)
        db.session.commit()
        flash(f"Đã XÓA VĨNH VIỄN tài khoản {u.username} cùng toàn bộ dữ liệu!")
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_course/<int:course_id>')
@login_required
def delete_course(course_id):
    if not current_user.is_admin: return "Unauthorized", 403
    c = db.session.get(Course, course_id)
    if c: 
        db.session.delete(c)
        db.session.commit()
        flash("Đã xóa hoàn toàn khóa học!")
    return redirect(url_for('courses'))

@app.route('/admin/reset/<int:user_id>')
@login_required
def reset_password(user_id):
    if not current_user.is_admin: return "No!", 403
    u = db.session.get(User, user_id)
    if u: 
        u.password = '123456'
        db.session.commit()
        flash(f"Đã reset mật khẩu cho {u.username} thành: 123456")
    return redirect(url_for('admin_users'))

@app.route('/admin/toggle_ban/<int:user_id>')
@login_required
def toggle_ban(user_id):
    if not current_user.is_admin: return "No!", 403
    u = db.session.get(User, user_id)
    if u: 
        u.is_banned = not u.is_banned
        db.session.commit()
    return redirect(url_for('admin_users'))

if __name__ == '__main__':
    app.run(debug=True)