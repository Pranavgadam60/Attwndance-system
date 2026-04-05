from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import sqlite3
import os
from datetime import datetime, timedelta
import random
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super_secret_attendance_key_wow'
DB_PATH = os.path.join(os.path.dirname(__file__), 'attendance.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# --- DECORATORS FOR RBAC ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session or session.get('role') != role:
                flash(f"Access restricted to {role}s only.", "error")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- AUTH ROUTES ---
@app.route('/', methods=['GET'])
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'admin': return redirect(url_for('admin_dashboard'))
        elif role == 'teacher': return redirect(url_for('teacher_dashboard'))
        elif role == 'student': return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            session['name'] = user['name']
            
            if user['role'] == 'admin': return redirect(url_for('admin_dashboard'))
            elif user['role'] == 'teacher': return redirect(url_for('teacher_dashboard'))
            elif user['role'] == 'student': return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid username or password', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---
@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    conn = get_db_connection()
    teachers = conn.execute("SELECT * FROM users WHERE role = 'teacher'").fetchall()
    
    # Get students with details
    students_query = """
    SELECT u.id, u.username, u.name, s.roll_number, s.department, s.semester 
    FROM users u JOIN students s ON u.id = s.user_id 
    WHERE u.role = 'student'
    ORDER BY s.department, s.roll_number
    """
    students = conn.execute(students_query).fetchall()
    
    subjects = conn.execute("SELECT * FROM subjects").fetchall()
    conn.close()
    
    students_list = [dict(s) for s in students]
    departments = {}
    for s in students_list:
        dept = s['department']
        if dept not in departments:
            departments[dept] = []
        departments[dept].append(s)
        
    return render_template('admin.html', teachers=teachers, departments=departments, subjects=subjects)

@app.route('/admin/add_teacher', methods=['POST'])
@role_required('admin')
def add_teacher():
    username = request.form['username']
    name = request.form['name']
    password = generate_password_hash(request.form['password'])
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)",
                     (username, password, 'teacher', name))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Username already exists.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_student', methods=['POST'])
@role_required('admin')
def add_student():
    username = request.form['username']
    name = request.form['name']
    password = generate_password_hash(request.form['password'])
    roll_number = request.form['roll_number']
    department = request.form['department']
    semester = request.form['semester']
    
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)",
                       (username, password, 'student', name))
        user_id = cursor.lastrowid
        cursor.execute("INSERT INTO students (user_id, roll_number, department, semester) VALUES (?, ?, ?, ?)",
                       (user_id, roll_number, department, semester))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Username or Roll Number already exists.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/add_subject', methods=['POST'])
@role_required('admin')
def add_subject():
    code = request.form['code']
    name = request.form['name']
    
    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO subjects (code, name) VALUES (?, ?)", (code, name))
        conn.commit()
    except sqlite3.IntegrityError:
        flash('Subject Code already exists.', 'error')
    finally:
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/assign_subject', methods=['POST'])
@role_required('admin')
def assign_subject():
    teacher_id = request.form['teacher_id']
    subject_id = request.form['subject_id']
    
    conn = get_db_connection()
    # Check if assignment already exists
    exists = conn.execute("SELECT id FROM teacher_subjects WHERE teacher_id = ? AND subject_id = ?",
                          (teacher_id, subject_id)).fetchone()
    if not exists:
        conn.execute("INSERT INTO teacher_subjects (teacher_id, subject_id) VALUES (?, ?)", (teacher_id, subject_id))
        conn.commit()
    conn.close()
    flash("Subject assigned to teacher successfully.", "success")
    return redirect(url_for('admin_dashboard'))

# --- TEACHER ROUTES ---
@app.route('/teacher')
@role_required('teacher')
def teacher_dashboard():
    teacher_id = session['user_id']
    conn = get_db_connection()
    
    # Get subjects assigned to this teacher
    query = """
    SELECT s.id, s.name, s.code 
    FROM subjects s 
    JOIN teacher_subjects ts ON s.id = ts.subject_id 
    WHERE ts.teacher_id = ?
    """
    subjects = conn.execute(query, (teacher_id,)).fetchall()
    
    # Get active session if exists
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    active_session = conn.execute("""
        SELECT * FROM attendance_sessions 
        WHERE teacher_id = ? AND expires_at > ? 
        ORDER BY expires_at DESC LIMIT 1
    """, (teacher_id, now)).fetchone()
    
    # Get recent sessions for manual attendance
    recent_sessions = conn.execute("""
        SELECT a.id, s.name, a.created_at, a.secret_code
        FROM attendance_sessions a
        JOIN subjects s ON a.subject_id = s.id
        WHERE a.teacher_id = ?
        ORDER BY a.created_at DESC
        LIMIT 15
    """, (teacher_id,)).fetchall()
    
    # Get all students for manual attendance combobox
    students = conn.execute("""
        SELECT u.id, u.name, st.roll_number 
        FROM users u 
        JOIN students st ON u.id = st.user_id 
        WHERE u.role = 'student'
        ORDER BY st.roll_number
    """).fetchall()
    
    conn.close()
    return render_template('teacher.html', subjects=subjects, active_session=active_session, recent_sessions=recent_sessions, students=students)

@app.route('/teacher/manual_attendance', methods=['POST'])
@role_required('teacher')
def manual_attendance():
    session_id = request.form.get('session_id')
    student_id = request.form.get('student_id')
    
    if not session_id or not student_id:
        flash("Please select both a session and a student.", "error")
        return redirect(url_for('teacher_dashboard'))
        
    conn = get_db_connection()
    teacher_id = session['user_id']
    valid_session = conn.execute("SELECT id FROM attendance_sessions WHERE id = ? AND teacher_id = ?", (session_id, teacher_id)).fetchone()
    
    if not valid_session:
        flash("Invalid session.", "error")
        conn.close()
        return redirect(url_for('teacher_dashboard'))
        
    try:
        conn.execute("INSERT INTO attendance_records (session_id, student_id) VALUES (?, ?)", (session_id, student_id))
        conn.commit()
        flash("Manual attendance marked successfully.", "success")
    except sqlite3.IntegrityError:
        flash("Attendance already marked for this student in this session.", "error")
    finally:
        conn.close()
        
    return redirect(url_for('teacher_dashboard'))

@app.route('/teacher/generate_code', methods=['POST'])
@role_required('teacher')
def generate_code():
    data = request.get_json()
    subject_id = data.get('subject_id')
    teacher_id = session['user_id']
    
    if not subject_id:
        return jsonify({'error': 'Subject ID is required'}), 400

    # Generate 6 digit code
    code = str(random.randint(100000, 999999))
    created_at = datetime.now()
    expires_at = created_at + timedelta(minutes=2)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO attendance_sessions (teacher_id, subject_id, secret_code, created_at, expires_at) 
        VALUES (?, ?, ?, ?, ?)
    """, (teacher_id, subject_id, code, created_at.strftime('%Y-%m-%d %H:%M:%S'), expires_at.strftime('%Y-%m-%d %H:%M:%S')))
    session_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return jsonify({
        'session_id': session_id,
        'code': code,
        'expires_at': expires_at.strftime('%Y-%m-%dT%H:%M:%S')
    })

@app.route('/teacher/session_attendance/<int:session_id>')
@role_required('teacher')
def session_attendance(session_id):
    conn = get_db_connection()
    query = """
    SELECT u.name, s.roll_number, ar.timestamp
    FROM attendance_records ar
    JOIN users u ON ar.student_id = u.id
    JOIN students s ON u.id = s.user_id
    WHERE ar.session_id = ?
    ORDER BY ar.timestamp DESC
    """
    records = conn.execute(query, (session_id,)).fetchall()
    conn.close()
    
    return jsonify([dict(r) for r in records])

# --- STUDENT ROUTES ---
@app.route('/student')
@role_required('student')
def student_dashboard():
    student_id = session['user_id']
    conn = get_db_connection()
    
    # Get subjects currently active? Maybe just general ones or specific to student.
    # For now, get all subjects as possible options for analytics.
    subjects = conn.execute("SELECT * FROM subjects").fetchall()
    conn.close()
    return render_template('student.html', subjects=subjects)

@app.route('/student/mark_attendance', methods=['POST'])
@role_required('student')
def mark_attendance():
    data = request.get_json()
    code = data.get('code')
    student_id = session['user_id']
    
    if not code:
        return jsonify({'error': 'Code is required'}), 400

    conn = get_db_connection()
   session_record = conn.execute("""
    SELECT * FROM attendance_sessions 
    WHERE secret_code = ?
""", (code,)).fetchone()

if not session_record:
    conn.close()
    return jsonify({'error': 'Invalid code'}), 400

# Convert expiry time
expires_at = datetime.strptime(session_record['expires_at'], '%Y-%m-%d %H:%M:%S')

if datetime.now() > expires_at:
    conn.close()
    return jsonify({'error': 'Code expired'}), 400
    
    if not session_record:
        conn.close()
        return jsonify({'error': 'Invalid or expired code'}), 400
        
    session_id = session_record['id']
    
    # Check if already marked
    existing = conn.execute("SELECT id FROM attendance_records WHERE session_id = ? AND student_id = ?", (session_id, student_id)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Attendance already marked for this class'}), 400
        
    # Mark attendance
    try:
        conn.execute("INSERT INTO attendance_records (session_id, student_id) VALUES (?, ?)", (session_id, student_id))
        conn.commit()
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500
        
    # Fetch subject name for UI confirmation
    subject = conn.execute("SELECT name FROM subjects WHERE id = ?", (session_record['subject_id'],)).fetchone()
    conn.close()
    
    return jsonify({'message': f'Attendance marked successfully for {subject["name"]}'})

@app.route('/student/analytics')
@role_required('student')
def student_analytics():
    student_id = session['user_id']
    conn = get_db_connection()
    
    # This requires knowing total sessions vs attended.
    # Count sessions per subject
    total_sessions_query = """
    SELECT subject_id, count(id) as total 
    FROM attendance_sessions 
    GROUP BY subject_id
    """
    total_by_subject = {r['subject_id']: r['total'] for r in conn.execute(total_sessions_query).fetchall()}
    
    # Count attended per subject for student
    attended_query = """
    SELECT s.subject_id, count(ar.id) as attended
    FROM attendance_sessions s
    JOIN attendance_records ar ON s.id = ar.session_id
    WHERE ar.student_id = ?
    GROUP BY s.subject_id
    """
    attended_by_subject = {r['subject_id']: r['attended'] for r in conn.execute(attended_query, (student_id,)).fetchall()}
    
    subjects = conn.execute("SELECT * FROM subjects").fetchall()
    
    data = []
    total_attended = 0
    total_overall = 0
    for subj in subjects:
        sid = subj['id']
        total = total_by_subject.get(sid, 0)
        if total > 0:
            attended = attended_by_subject.get(sid, 0)
            percentage = (attended / total) * 100
            
            # Smart logic: required to reach 75%
            # Eq: (attended + x) / (total + x) = 0.75
            # attended + x = 0.75*total + 0.75*x
            # 0.25*x = 0.75*total - attended
            # x = 3*total - 4*attended
            required_lectures = 0
            if percentage < 75:
                required = 3 * total - 4 * attended
                required_lectures = int(required) if required > 0 else 0
                
            data.append({
                'subject': subj['name'],
                'total': total,
                'attended': attended,
                'percentage': round(percentage, 2),
                'required_for_75': required_lectures
            })
            total_attended += attended
            total_overall += total

    conn.close()
    
    overall_percentage = round((total_attended / total_overall * 100), 2) if total_overall > 0 else 0
    
    return jsonify({
        'subjects': data,
        'overall_percentage': overall_percentage
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
