from flask import Flask, request, render_template, redirect, url_for, flash, session
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import time
import re

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure random key

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',  # Replace with your MariaDB username
    'password': '',  # Replace with your MariaDB password
    'database': 'attendance_db'
}

# Institutional email domain
INSTITUTION_EMAIL_DOMAIN = '@university.com'  # Replace with your institution's domain

def get_db_connection():
    return mysql.connector.connect(**db_config)

def is_institutional_email(email):
    return email.endswith(INSTITUTION_EMAIL_DOMAIN)

def is_valid_phone(phone):
    return bool(re.match(r'^\d{10}$', phone))

@app.route('/')
@app.route('/auth')
def auth():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT department_id, department_name FROM Departments")
        departments = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('auth.html', departments=departments)
    except mysql.connector.Error as err:
        flash(f'Error: {err}', 'error')
        return render_template('auth.html', departments=[])

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.user_id, u.student_id, u.teacher_id, u.admin_id, u.password_hash
            FROM Users u
            LEFT JOIN Student s ON u.student_id = s.id
            LEFT JOIN Teachers t ON u.teacher_id = t.teacher_id
            LEFT JOIN Admins a ON u.admin_id = a.admin_id
            WHERE s.email = %s OR t.email = %s OR a.email = %s
        """, (email, email, email))
        user = cursor.fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['role'] = 'student' if user['student_id'] else 'teacher' if user['teacher_id'] else 'admin'
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'error')
            return render_template('auth.html', login_error='Invalid email or password', departments=[])
    except mysql.connector.Error as err:
        flash(f'Error: {err}', 'error')
        return render_template('auth.html', login_error='Database error', departments=[])
    finally:
        cursor.close()
        conn.close()

@app.route('/register', methods=['POST'])
def register():
    role = request.form['role']
    email = request.form['email']
    phone = request.form['phone']
    password = request.form['password']
    department_id = request.form['department_id']
    year = request.form.get('year')
    first_name = request.form.get('first_name', 'First')
    last_name = request.form.get('last_name', 'Last')
    
    # Institutional verification
    if not is_institutional_email(email):
        flash(f'Email must end with {INSTITUTION_EMAIL_DOMAIN}.', 'error')
        return render_template('auth.html', signup_error=f'Email must end with {INSTITUTION_EMAIL_DOMAIN}', departments=[])
    if not is_valid_phone(phone):
        flash('Phone must be a 10-digit number.', 'error')
        return render_template('auth.html', signup_error='Phone must be a 10-digit number', departments=[])
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Check for existing email or phone
        cursor.execute("SELECT id FROM Students WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or phone already registered.', 'error')
            return render_template('auth.html', signup_error='Email or phone already registered', departments=[])
        cursor.execute("SELECT teacher_id FROM Teachers WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or phone already registered.', 'error')
            return render_template('auth.html', signup_error='Email or phone already registered', departments=[])
        cursor.execute("SELECT admin_id FROM Admins WHERE email = %s OR phone = %s", (email, phone))
        if cursor.fetchone():
            flash('Email or phone already registered.', 'error')
            return render_template('auth.html', signup_error='Email or phone already registered', departments=[])
        
        # Generate unique ID
        timestamp = str(int(time.time()))
        user_id = f"{'S' if role == 'student' else 'T' if role == 'teacher' else 'A'}{timestamp}{random.randint(1000, 9999)}"
        password_hash = generate_password_hash(password)
        
        # Insert into role-specific table
        if role == 'student':
            cursor.execute("""
                INSERT INTO Student (id, email, phone, department_id, year, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (user_id, email, phone, department_id, year))
            student_id = user_id
            teacher_id = None
            admin_id = None
        elif role == 'teacher':
            cursor.execute("""
                INSERT INTO Teachers (teacher_id, first_name, last_name, email, phone, department_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
            """, (user_id, first_name, last_name, email, phone, department_id))
            student_id = None
            teacher_id = user_id
            admin_id = None
        else:  # admin
            cursor.execute("""
                INSERT INTO Admins (admin_id, first_name, last_name, email, phone, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (user_id, first_name, last_name, email, phone))
            student_id = None
            teacher_id = None
            admin_id = user_id
        
        # Insert into Users
        cursor.execute("""
            INSERT INTO Users (student_id, teacher_id, admin_id, password_hash, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (student_id, teacher_id, admin_id, password_hash))
        user_id_db = cursor.lastrowid
        
        # Generate OTP
        otp = ''.join(random.choices(string.digits, k=6))
        cursor.execute("""
            INSERT INTO OTP_Verifications (user_id, otp_code, created_at, expires_at)
            VALUES (%s, %s, NOW(), NOW() + INTERVAL 10 MINUTE)
        """, (user_id_db, otp))
        
        conn.commit()
        # Placeholder for OTP delivery
        print(f"OTP for {email}: {otp}")  # Replace with email/SMS service
        session['pending_user_id'] = user_id_db
        flash(f'OTP sent to {email}. Please verify.', 'success')
        return redirect(url_for('verify_otp'))
    except mysql.connector.Error as err:
        conn.rollback()
        flash(f'Error: {err}', 'error')
        return render_template('auth.html', signup_error='Registration failed', departments=[])
    finally:
        cursor.close()
        conn.close()

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        otp = request.form['otp']
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT user_id FROM OTP_Verifications
                WHERE otp_code = %s AND user_id = %s AND expires_at > NOW()
            """, (otp, session.get('pending_user_id')))
            if cursor.fetchone():
                flash('Registration successful! Please log in.', 'success')
                session.pop('pending_user_id', None)
                return redirect(url_for('auth'))
            else:
                flash('Invalid or expired OTP.', 'error')
                return render_template('verify_otp.html', otp_error='Invalid or expired OTP')
        except mysql.connector.Error as err:
            flash(f'Error: {err}', 'error')
            return render_template('verify_otp.html', otp_error='Database error')
        finally:
            cursor.close()
            conn.close()
    return render_template('verify_otp.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please log in.', 'error')
        return redirect(url_for('auth'))
    return render_template('dashboard.html', role=session['role'])

if __name__ == '__main__':
    app.run(debug=True, port=5000)  # Use port 5001 to avoid conflicts