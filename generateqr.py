from flask import Flask, flash, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
import qrcode
import time
import os
import mysql.connector
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = 'hard_to_guess_string_123!@#'  # Change in production
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=False  # Set to True with HTTPS
)

# MySQL Configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Change in production
    'database': 'attendance_db'
}

@contextmanager
def get_db_connection():
    conn = mysql.connector.connect(**db_config)
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS student
                     (id VARCHAR(10) PRIMARY KEY, name VARCHAR(100), password_hash VARCHAR(255))''')
        c.execute('''CREATE TABLE IF NOT EXISTS attendance 
                     (student_id VARCHAR(10), qr_data VARCHAR(50), timestamp DATETIME,
                      FOREIGN KEY(student_id) REFERENCES student(id))''')
        conn.commit()
        print("Database initialized or checked.")

# Global QR variables
current_qr_data = None
qr_expiration_time = None
QR_LIFETIME = 900  # 15 minutes

def generate_qr_code():
    global current_qr_data, qr_expiration_time
    current_qr_data = f"Attendance_{int(time.time())}"
    qr = qrcode.make(current_qr_data, box_size=15)  # Increased box_size for clarity
    qr_path = "static/qr.png"
    qr.save(qr_path)
    qr_expiration_time = time.time() + QR_LIFETIME
    print(f"Generated QR: {current_qr_data}, Expires at: {time.ctime(qr_expiration_time)}")
    return qr_path

@app.route('/student_login', methods=['GET', 'POST'])
def student_login():
    session.pop('_flashes', None)
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        password = request.form.get('password')
        with get_db_connection() as conn:
            c = conn.cursor(dictionary=True)
            c.execute("SELECT id, name, password_hash FROM student WHERE id = %s", (student_id,))
            student = c.fetchone()
            if student and check_password_hash(student['password_hash'], password):
                session['student_id'] = student['id']
                session['student_name'] = student['name']
                print(f"Logged in: {student_id}, Session: {session}")
                return redirect(url_for('scan'))
            else:
                flash("Invalid Student ID or Password.", "danger")
                print(f"Login failed for: {student_id}")
                return redirect(url_for('student_login'))
    return render_template('student_login.html')

@app.route('/student_logout')
def student_logout():
    student_id = session.get('student_id')
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash("You have been logged out.", "info")
    print(f"Logged out: {student_id}")
    return redirect(url_for('student_login'))

@app.route('/')
def index():
    qr_path = generate_qr_code()
    time_left = int(qr_expiration_time - time.time()) if current_qr_data and time.time() < qr_expiration_time else 0
    return render_template('index.html', qr_path=qr_path, time_left=time_left)

@app.route('/generate', methods=['POST'])
def generate_new_qr():
    qr_path = generate_qr_code()
    time_left = int(qr_expiration_time - time.time()) if current_qr_data and time.time() < qr_expiration_time else 0
    return render_template('index.html', qr_path=qr_path, time_left=time_left)

@app.route('/check_qr')
def check_qr():
    if current_qr_data and time.time() < qr_expiration_time:
        time_left = int(qr_expiration_time - time.time())
        print(f"QR check: Valid, Time left: {time_left}")
        return {"valid": True, "data": current_qr_data, "time_left": time_left}
    else:
        print("QR check: Expired or invalid")
        return {"valid": False, "data": None, "time_left": 0}

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    student_id = session.get('student_id')
    print(f"Mark attendance request received. Student ID: {student_id}, Request Data: {request.get_data()}, JSON: {request.get_json()}")
    if not student_id:
        print("No student_id in session")
        return jsonify({"success": False, "message": "Please log in to mark attendance!"}), 401

    data = request.get_json()
    if not data or not data.get('qr_data'):
        print("No QR data provided in request")
        return jsonify({"success": False, "message": "No QR data provided!"}), 400

    qr_data = data['qr_data']
    print(f"Processing QR: Received {qr_data}, Current {current_qr_data}, Time {time.time()}, Expires {qr_expiration_time}")
    if qr_data != current_qr_data or time.time() > qr_expiration_time:
        print("QR invalid or expired")
        return jsonify({"success": False, "message": "Invalid or expired QR code!"}), 400

    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM attendance WHERE student_id=%s AND qr_data=%s", (student_id, qr_data))
        if c.fetchone():
            print("Attendance already marked")
            return jsonify({"success": False, "message": "Attendance already marked for this QR code!"}), 400

        try:
            c.execute("INSERT INTO attendance (student_id, qr_data, timestamp) VALUES (%s, %s, NOW())", (student_id, qr_data))
            conn.commit()
            print(f"Attendance marked successfully for {student_id} with QR {qr_data}")
        except mysql.connector.Error as e:
            print(f"Database error: {e}")
            return jsonify({"success": False, "message": f"Database error: {e}"}), 500

    return jsonify({"success": True, "message": "Attendance marked successfully!"})

@app.route('/scan')
def scan():
    if 'student_id' not in session:
        flash("Please log in to access the scanner.", "warning")
        return redirect(url_for('student_login'))
    student_name = session.get('student_name', 'Student')
    student_id = session.get('student_id')
    print(f"Scan page accessed by {student_id}, Session: {session}")
    return render_template('scan.html', student_name=student_name, student_id=student_id)

if __name__ == '__main__':
    if not os.path.exists('static'):
        os.makedirs('static')
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)