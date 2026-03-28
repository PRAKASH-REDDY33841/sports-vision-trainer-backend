from fastapi import FastAPI, UploadFile, File, Form
from schemas import *
from database import get_db
from auth import hash_password, verify_password
import random, datetime, os, shutil

# ✅ EMAIL IMPORTS
import smtplib
from email.mime.text import MIMEText

# ✅ STATIC FILES
from fastapi.staticfiles import StaticFiles

# ✅ CORS IMPORT (ADDED)
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ BASE URL (Update this if your IP or port changes)
BASE_URL = "http://10.136.25.111:8141"

# ✅ CORS MIDDLEWARE (ADDED)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ STATIC MOUNT
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------------- EMAIL FUNCTION ----------------
def send_email_otp(to_email, otp):
    sender_email = "prakash33841@gmail.com"
    sender_password = "tbhazosrngtcefyd"

    subject = "Password Reset OTP"
    body = f"Your OTP is: {otp}"

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True
    except Exception as e:
        print("Email Error:", e)
        return False


# ---------------- USERS TABLE INITIALIZATION ----------------
def init_users_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            bio TEXT,
            profile_image VARCHAR(255),
            reset_otp VARCHAR(10),
            otp_expiry DATETIME
        )
    """)
    db.commit()

init_users_table()

# ---------------- REGISTER ----------------
@app.post("/register")
def register(req: RegisterRequest):
    init_users_table()  # Ensure table exists
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if req.username == "" or req.email == "" or req.password == "":
        return {
            "status": "error",
            "message": "Missing fields"
        }

    cursor.execute("SELECT id FROM users WHERE email=%s", (req.email,))
    if cursor.fetchone():
        return {
            "status": "error",
            "message": "User already registered"
        }

    hashed = hash_password(req.password)

    cursor.execute(
        "INSERT INTO users(username,email,password) VALUES (%s,%s,%s)",
        (req.username, req.email, hashed)
    )
    db.commit()

    return {
        "status": "success",
        "message": "Registered successfully"
    }


# ---------------- LOGIN ----------------
@app.post("/login")
def login(req: LoginRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if req.email == "" or req.password == "":
        return {
            "status": "error",
            "message": "Missing credentials"
        }

    cursor.execute(
        "SELECT username,password FROM users WHERE email=%s",
        (req.email,)
    )
    user = cursor.fetchone()

    if not user:
        return {
            "status": "error",
            "message": "User not found"
        }

    if verify_password(req.password, user["password"]):
        return {
            "status": "success",
            "username": user["username"]
        }
    else:
        return {
            "status": "error",
            "message": "Wrong password"
        }


# ---------------- SEND OTP ----------------
@app.post("/send_otp")
def send_otp(req: ForgotRequest):
    db = get_db()
    cursor = db.cursor()

    if not req.email:
        return {"status": "error", "msg": "Email required"}

    otp = str(random.randint(100000, 999999))
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)

    cursor.execute(
        "UPDATE users SET reset_otp=%s, otp_expiry=%s WHERE email=%s",
        (otp, expiry, req.email)
    )
    db.commit()

    if send_email_otp(req.email, otp):
        return {"status": "success"}
    else:
        return {"status": "error", "msg": "Failed to send email"}


# ---------------- VERIFY OTP ----------------
@app.post("/verify_otp")
def verify_otp(req: OtpVerifyRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if not req.email or not req.otp:
        return {"status": "error", "msg": "Missing email or otp"}

    cursor.execute(
        "SELECT reset_otp, otp_expiry FROM users WHERE email=%s",
        (req.email,)
    )
    row = cursor.fetchone()

    if not row:
        return {"status": "error", "msg": "User not found"}

    if row["reset_otp"] != req.otp:
        return {"status": "error", "msg": "Invalid OTP"}

    if row["otp_expiry"] < datetime.datetime.now():
        return {"status": "error", "msg": "OTP expired"}

    return {"status": "success"}


# ---------------- RESET PASSWORD ----------------
@app.post("/reset_password_final")
def reset_password(req: ResetRequest):
    db = get_db()
    cursor = db.cursor()

    if not req.email or not req.password:
        return {"status": "error", "msg": "Missing data"}

    hashed = hash_password(req.password)

    cursor.execute(
        "UPDATE users SET password=%s, reset_otp=NULL, otp_expiry=NULL WHERE email=%s",
        (hashed, req.email)
    )
    db.commit()

    return {"status": "success"}


# ---------------- GET PROFILE ----------------
@app.get("/get_profile")
def get_profile(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT username,bio,profile_image FROM users WHERE email=%s",
        (email,)
    )
    user = cursor.fetchone()

    if user and user["profile_image"]:
        user["profile_image"] = f"{BASE_URL}/{user['profile_image']}"

    return user


# ---------------- SAVE PROFILE ----------------
@app.post("/save_profile")
async def save_profile(
    email: str = Form(...),
    name: str = Form(...),
    bio: str = Form(...),
    photo: UploadFile = File(None)
):
    db = get_db()
    cursor = db.cursor()

    image_path = ""

    if photo:
        filename = f"{int(datetime.datetime.now().timestamp())}_{photo.filename}"
        path = os.path.join(UPLOAD_DIR, filename)

        with open(path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        image_path = f"uploads/{filename}"

    cursor.execute(
        "UPDATE users SET username=%s, bio=%s, profile_image=%s WHERE email=%s",
        (name, bio, image_path, email)
    )
    db.commit()

    return {"status": "success"}


# ---------------- SAVE SESSION ----------------
@app.post("/save_session")
def save_session(req: SessionSaveRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(100),
            game_type VARCHAR(50),
            score INT,
            avg_reaction BIGINT,
            wrong INT,
            timestamp BIGINT
        )
    """)

    cursor.execute(
        "INSERT INTO game_sessions (email, game_type, score, avg_reaction, wrong, timestamp) VALUES (%s, %s, %s, %s, %s, %s)",
        (req.email, req.gameType, req.score, req.avgReaction, req.wrong, req.timestamp)
    )
    db.commit()

    return {"status": "success"}


# ---------------- GET SESSIONS ----------------
@app.get("/get_sessions")
def get_sessions(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            email VARCHAR(100),
            game_type VARCHAR(50),
            score INT,
            avg_reaction BIGINT,
            wrong INT,
            timestamp BIGINT
        )
    """)

    cursor.execute(
        "SELECT game_type as gameType, score, avg_reaction as avgReaction, wrong, timestamp FROM game_sessions WHERE email=%s ORDER BY timestamp ASC",
        (email,)
    )
    rows = cursor.fetchall()
    
    sessions = []
    if rows:
        for row in rows:
            sessions.append({
                "gameType": row["gameType"],
                "score": int(row["score"]),
                "avgReaction": int(row["avgReaction"]),
                "wrong": int(row["wrong"]),
                "timestamp": int(row["timestamp"])
            })

    return {"status": "success", "sessions": sessions}

# ---------------- DOCTOR REGISTER ----------------
@app.post("/doctor_register")
def doctor_register(req: DoctorRegisterRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(100),
            medical_license VARCHAR(100),
            hospital_name VARCHAR(255),
            clinic_email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            reset_otp VARCHAR(10),
            otp_expiry DATETIME
        )
    """)

    if not req.full_name or not req.clinic_email or not req.password:
        return {"status": "error", "message": "Missing fields"}

    cursor.execute("SELECT id FROM doctors WHERE clinic_email=%s OR medical_license=%s", (req.clinic_email, req.medical_license))
    if cursor.fetchone():
        return {"status": "error", "message": "Email or Medical License already registered"}

    hashed = hash_password(req.password)

    cursor.execute(
        "INSERT INTO doctors(full_name, medical_license, hospital_name, clinic_email, password) VALUES (%s,%s,%s,%s,%s)",
        (req.full_name, req.medical_license, req.hospital_name, req.clinic_email, hashed)
    )
    db.commit()

    return {"status": "success", "message": "Doctor registered successfully"}


# ---------------- DOCTOR LOGIN ----------------
@app.post("/doctor_login")
def doctor_login(req: DoctorLoginRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if not req.clinic_email or not req.password:
        return {"status": "error", "message": "Missing credentials"}

    try:
        cursor.execute("SELECT full_name, password FROM doctors WHERE clinic_email=%s", (req.clinic_email,))
        user = cursor.fetchone()
    except Exception as e:
        return {"status": "error", "message": f"Database error: {str(e)}"}

    if not user:
        return {"status": "error", "message": "Doctor not found"}

    if verify_password(req.password, user["password"]):
        return {"status": "success", "username": user["full_name"]}
    else:
        return {"status": "error", "message": "Wrong password"}

# ---------------- DOCTOR SEND OTP ----------------
@app.post("/doctor_send_otp")
def doctor_send_otp(req: ForgotRequest):
    db = get_db()
    cursor = db.cursor()

    if not req.email:
        return {"status": "error", "msg": "Email required"}

    # Add columns if they don't exist
    try:
        cursor.execute("ALTER TABLE doctors ADD COLUMN reset_otp VARCHAR(10), ADD COLUMN otp_expiry DATETIME")
        db.commit()
    except:
        pass

    otp = str(random.randint(100000, 999999))
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)

    cursor.execute(
        "UPDATE doctors SET reset_otp=%s, otp_expiry=%s WHERE clinic_email=%s",
        (otp, expiry, req.email)
    )
    db.commit()

    if cursor.rowcount == 0:
        return {"status": "error", "msg": "Doctor email not found"}

    if send_email_otp(req.email, otp):
        return {"status": "success"}
    else:
        return {"status": "error", "msg": "Failed to send email"}

# ---------------- DOCTOR VERIFY OTP ----------------
@app.post("/doctor_verify_otp")
def doctor_verify_otp(req: OtpVerifyRequest):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    if not req.email or not req.otp:
        return {"status": "error", "msg": "Missing email or otp"}

    cursor.execute(
        "SELECT reset_otp, otp_expiry FROM doctors WHERE clinic_email=%s",
        (req.email,)
    )
    row = cursor.fetchone()

    if not row:
        return {"status": "error", "msg": "Doctor not found"}

    if row["reset_otp"] != req.otp:
        return {"status": "error", "msg": "Invalid OTP"}

    if row["otp_expiry"] and row["otp_expiry"] < datetime.datetime.now():
        return {"status": "error", "msg": "OTP expired"}

    return {"status": "success"}

# ---------------- DOCTOR RESET PASSWORD ----------------
@app.post("/doctor_reset_password_final")
def doctor_reset_password(req: ResetRequest):
    db = get_db()
    cursor = db.cursor()

    if not req.email or not req.password:
        return {"status": "error", "msg": "Missing data"}

    hashed = hash_password(req.password)

    cursor.execute(
        "UPDATE doctors SET password=%s, reset_otp=NULL, otp_expiry=NULL WHERE clinic_email=%s",
        (hashed, req.email)
    )
    db.commit()

    return {"status": "success"}

# ---------------- GET DOCTOR PROFILE ----------------
@app.get("/get_doctor_profile")
def get_doctor_profile(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    # Ensure columns exist
    try:
        cursor.execute("ALTER TABLE doctors ADD COLUMN bio TEXT, ADD COLUMN profile_image VARCHAR(255)")
        db.commit()
    except:
        pass

    cursor.execute(
        "SELECT full_name as username, bio, profile_image FROM doctors WHERE clinic_email=%s",
        (email,)
    )
    doctor = cursor.fetchone()

    if doctor and doctor["profile_image"]:
        doctor["profile_image"] = f"{BASE_URL}/{doctor['profile_image']}"

    return doctor


# ---------------- SAVE DOCTOR PROFILE ----------------
@app.post("/save_doctor_profile")
async def save_doctor_profile(
    email: str = Form(...),
    name: str = Form(...),
    bio: str = Form(...),
    photo: UploadFile = File(None)
):
    db = get_db()
    cursor = db.cursor()

    image_path = None

    if photo:
        filename = f"doctor_{int(datetime.datetime.now().timestamp())}_{photo.filename}"
        path = os.path.join(UPLOAD_DIR, filename)

        with open(path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        image_path = f"uploads/{filename}"

    if image_path:
        cursor.execute(
            "UPDATE doctors SET full_name=%s, bio=%s, profile_image=%s WHERE clinic_email=%s",
            (name, bio, image_path, email)
        )
    else:
        cursor.execute(
            "UPDATE doctors SET full_name=%s, bio=%s WHERE clinic_email=%s",
            (name, bio, email)
        )
    
    db.commit()

    return {"status": "success"}

# ---------------- GET DOCTORS ----------------
@app.get("/get_doctors")
def get_doctors():
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("SELECT full_name, medical_license, hospital_name, clinic_email, profile_image FROM doctors")
    doctors = cursor.fetchall()

    for doctor in doctors:
        if doctor.get("profile_image"):
            doctor["profile_image"] = f"{BASE_URL}/{doctor['profile_image']}"
        else:
            doctor["profile_image"] = None

    return {"status": "success", "doctors": doctors}

# ---------------- APPOINTMENTS TABLE INITIALIZATION ----------------
def init_appointments_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            doctor_email VARCHAR(255),
            athlete_email VARCHAR(255),
            athlete_name VARCHAR(255),
            athlete_phone VARCHAR(20),
            date DATE,
            time TIME,
            status VARCHAR(50) DEFAULT 'PENDING'
        )
    """)
    db.commit()

init_appointments_table()
init_users_table()

# ---------------- BOOK APPOINTMENT ----------------
@app.post("/book_appointment")
def book_appointment(req: AppointmentRequest):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO appointments (doctor_email, athlete_email, athlete_name, athlete_phone, date, time) VALUES (%s, %s, %s, %s, %s, %s)",
        (req.doctor_email, req.athlete_email, req.athlete_name, req.athlete_phone, req.date, req.time)
    )
    db.commit()
    return {"status": "success", "message": "Appointment requested"}

# ---------------- GET DOCTOR APPOINTMENTS ----------------
@app.get("/get_doctor_appointments")
def get_doctor_appointments(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, doctor_email, athlete_email, athlete_name, athlete_phone,
               CAST(date AS CHAR) as date, CAST(time AS CHAR) as time, status 
        FROM appointments WHERE doctor_email=%s AND status='PENDING'
    """, (email,))
    return {"status": "success", "appointments": cursor.fetchall()}

# ---------------- GET DOCTOR HISTORY ----------------
@app.get("/get_doctor_history")
def get_door_history(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS CHAR) as date, CAST(a.time AS CHAR) as time, a.status,
               CONCAT('{BASE_URL}/', u.profile_image) as profile_image
        FROM appointments a
        LEFT JOIN users u ON a.athlete_email = u.email
        WHERE a.doctor_email=%s AND a.status IN ('ACCEPTED', 'REJECTED', 'CANCELLED')
        ORDER BY a.id DESC
    """, (email,))
    return {"status": "success", "appointments": cursor.fetchall()}

# ---------------- UPDATE APPOINTMENT STATUS ----------------
@app.post("/update_appointment_status")
def update_appointment_status(req: UpdateStatusRequest):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE appointments SET status=%s WHERE id=%s", (req.status, req.id))
    db.commit()
    return {"status": "success", "message": f"Appointment {req.status}"}

# ---------------- GET ATHLETE NOTIFICATIONS ----------------
@app.get("/get_athlete_notifications")
def get_athlete_notifications(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    # Get accepted appointments that haven't been "dismissed" (we'll just show all active accepted ones for now)
    cursor.execute("SELECT * FROM appointments WHERE athlete_email=%s AND status IN ('ACCEPTED', 'REJECTED') ORDER BY id DESC LIMIT 1", (email,))
    app = cursor.fetchone()
    
    if app:
        if app['status'] == 'ACCEPTED':
            return {
                "status": "success", 
                "id": app['id'],
                "app_status": "ACCEPTED",
                "message": f"doctor call to your mobile number at you booking time please be alert"
            }
        else:
            return {
                "status": "success",
                "id": app['id'],
                "app_status": "REJECTED",
                "message": f"Your appointment request has been rejected by the doctor."
            }
    return {"status": "error", "message": "No new notifications"}

# ---------------- GET ACCEPTED APPOINTMENTS ----------------
@app.get("/get_accepted_appointments")
def get_accepted_appointments(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute(f"""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS CHAR) as date, CAST(a.time AS CHAR) as time, a.status,
               CONCAT('{BASE_URL}/', u.profile_image) as profile_image
        FROM appointments a
        LEFT JOIN users u ON a.athlete_email = u.email
        WHERE a.doctor_email=%s AND a.status='ACCEPTED'
        ORDER BY a.date ASC, a.time ASC
    """, (email,))
    return {"status": "success", "appointments": cursor.fetchall()}

# ---------------- GET ATHLETE BOOKINGS ----------------
@app.get("/get_athlete_bookings")
def get_athlete_bookings(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)
    cursor.execute("""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS CHAR) as date, 
               CAST(a.time AS CHAR) as time,
               a.status, d.full_name as doctor_name 
        FROM appointments a
        LEFT JOIN doctors d ON a.doctor_email = d.clinic_email
        WHERE a.athlete_email=%s 
        ORDER BY a.id DESC
    """, (email,))
    return {"status": "success", "bookings": cursor.fetchall()}

# ---------------- CANCEL APPOINTMENT ----------------
@app.post("/cancel_appointment")
def cancel_appointment(id: int):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("UPDATE appointments SET status='CANCELLED' WHERE id=%s", (id,))
    db.commit()
    return {"status": "success", "message": "Appointment cancelled"}