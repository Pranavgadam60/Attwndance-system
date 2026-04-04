import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'attendance.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL, -- 'admin', 'teacher', 'student'
            name TEXT NOT NULL
        )
    ''')

    # Students Details Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            roll_number TEXT UNIQUE NOT NULL,
            department TEXT NOT NULL,
            semester INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Subjects Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    ''')

    # Teacher_Subjects Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            subject_id INTEGER,
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )
    ''')

    # Student_Subjects Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS student_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            subject_id INTEGER,
            FOREIGN KEY (student_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )
    ''')

    # Attendance Sessions Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_id INTEGER,
            subject_id INTEGER,
            secret_code TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (subject_id) REFERENCES subjects (id)
        )
    ''')

    # Attendance Records Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            student_id INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES attendance_sessions (id),
            FOREIGN KEY (student_id) REFERENCES users (id),
            UNIQUE(session_id, student_id) -- Avoid duplicate attendance for the same lecture
        )
    ''')

    # Insert default admin if not exists
    from werkzeug.security import generate_password_hash
    cursor.execute("SELECT id FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        hashed_pw = generate_password_hash('admin123')
        cursor.execute("INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)", 
                       ('admin', hashed_pw, 'admin', 'System Administrator'))

    conn.commit()
    conn.close()
    print("Database initialized successfully.")

if __name__ == '__main__':
    init_db()
