import mysql.connector
from werkzeug.security import generate_password_hash

db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  # Your XAMPP password
    'database': 'attendance_db'
}

def add_student(student_id, name, plain_password):
    try:
        if not student_id or not name or not plain_password:
            raise ValueError("Student ID, name, and password cannot be empty!")
        
        conn = mysql.connector.connect(**db_config)
        c = conn.cursor()
        hashed_password = generate_password_hash(plain_password)
        sql = "INSERT INTO student (id, name, password_hash) VALUES (%s, %s, %s)"
        val = (student_id, name, hashed_password)
        c.execute(sql, val)
        conn.commit()
        print(f"Student {name} ({student_id}) added successfully.")
    except mysql.connector.Error as err:
        print(f"Database Error: {err}")
    except ValueError as ve:
        print(f"Validation Error: {ve}")
    finally:
        if conn and conn.is_connected():
            conn.close()

def add_test_student():
    add_student('S101', 'Alice Test', 'password123')
    add_student('S102', 'Bob Example', 'qwerty')

if __name__ == '__main__':
    add_test_student()