from fastapi import FastAPI, UploadFile, File, Form, Request
from schemas import *
from database import get_db
from auth import hash_password, verify_password
import random, datetime, os, shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ✅ EMAIL IMPORTS
import smtplib
from email.mime.text import MIMEText

# ✅ STATIC FILES
from fastapi.staticfiles import StaticFiles

# ✅ CORS IMPORT (ADDED)
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# ✅ BASE URL (Loaded from environment)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8141")

# ✅ CORS MIDDLEWARE
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
    subject = "Password Reset OTP"
    body = f"Your OTP is: {otp}"

    # Check if Resend API is configured (recommended for Render Free Tier)
    resend_api_key = os.getenv("RESEND_API_KEY")
    if resend_api_key:
        import json
        import urllib.request
        import urllib.error

        url = "https://api.resend.com/emails"
        from_email = os.getenv("RESEND_SENDER_EMAIL", "onboarding@resend.dev")

        headers = {
            "Authorization": f"Bearer {resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "sports-vision-trainer-backend/1.0"
        }

        payload = {
            "from": from_email,
            "to": [to_email],
            "subject": subject,
            "html": f"<p>{body}</p>"
        }

        try:
            req = urllib.request.Request(
                url, 
                data=json.dumps(payload).encode("utf-8"), 
                headers=headers, 
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return True, "Success"
        except urllib.error.HTTPError as e:
            error_info = e.read().decode("utf-8")
            try:
                err_json = json.loads(error_info)
                msg = err_json.get("message", error_info)
            except Exception:
                msg = error_info
            return False, f"Resend API Error: {msg}"
        except Exception as e:
            return False, f"Resend Connection Error: {str(e)}"

    # Fallback to standard SMTP
    sender_email = os.getenv("SMTP_SENDER_EMAIL")
    sender_password = os.getenv("SMTP_SENDER_PASSWORD")
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))

    if not sender_email or not sender_password:
        return False, "Email sending failed. On Render Free Tier, standard SMTP ports (587, 465) are blocked. Please set 'RESEND_API_KEY' in Render environment variables to send emails via HTTP API for free."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, to_email, msg.as_string())
        server.quit()
        return True, "Success"
    except smtplib.SMTPAuthenticationError:
        return False, "SMTP Authentication Failed. If using Gmail, make sure to use a 16-character Google 'App Password', NOT your regular login password."
    except Exception as e:
        error_msg = str(e)
        if "101" in error_msg or "unreachable" in error_msg.lower() or "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            return False, f"SMTP Error: {error_msg}. (Note: Standard SMTP ports are blocked on Render Free Tier. Please register on Resend.com and add 'RESEND_API_KEY' in Render environment variables to send emails via HTTP API for free)."
        return False, f"SMTP Error: {error_msg}"


from psycopg2 import extras

# ---------------- USERS TABLE INITIALIZATION ----------------
def init_users_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100),
            email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            bio TEXT,
            profile_image VARCHAR(255),
            reset_otp VARCHAR(10),
            otp_expiry TIMESTAMP
        )
    """)
    db.commit()

def init_game_sessions_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS game_sessions (
            id SERIAL PRIMARY KEY,
            email VARCHAR(100),
            game_type VARCHAR(50),
            score INT,
            avg_reaction BIGINT,
            wrong INT,
            timestamp BIGINT
        )
    """)
    db.commit()

def init_doctors_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            id SERIAL PRIMARY KEY,
            full_name VARCHAR(100),
            medical_license VARCHAR(100),
            hospital_name VARCHAR(255),
            clinic_email VARCHAR(100) UNIQUE,
            password VARCHAR(255),
            reset_otp VARCHAR(10),
            otp_expiry TIMESTAMP,
            bio TEXT,
            profile_image VARCHAR(255)
        )
    """)
    db.commit()

def init_appointments_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
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

# ---------------- STARTUP INITIALIZATION ----------------
@app.on_event("startup")
def on_startup():
    init_users_table()
    init_game_sessions_table()
    init_doctors_table()
    init_appointments_table()

@app.get("/test_email_config")
def test_email_config():
    resend_key = os.getenv("RESEND_API_KEY")
    resend_sender = os.getenv("RESEND_SENDER_EMAIL")
    smtp_sender = os.getenv("SMTP_SENDER_EMAIL")
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    
    resend_status = "Not Set"
    if resend_key:
        resend_status = f"Set (Length: {len(resend_key)}, Starts with: {resend_key[:5]}...)" if len(resend_key) > 5 else "Set (Too Short)"
        
    return {
        "status": "success",
        "resend_config": {
            "resend_api_key_configured": resend_key is not None and len(resend_key.strip()) > 0,
            "resend_api_key_details": resend_status,
            "resend_sender_email": resend_sender or "onboarding@resend.dev (default)"
        },
        "smtp_config": {
            "smtp_sender_configured": smtp_sender is not None and len(smtp_sender.strip()) > 0,
            "smtp_server": smtp_server or "smtp.gmail.com (default)",
            "smtp_port": smtp_port or "587 (default)"
        },
        "note": "Standard SMTP is blocked on Render Free Tier. You MUST configure a valid RESEND_API_KEY in Render dashboard environment variables."
    }

@app.post("/register")
def register(req: RegisterRequest):
    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=extras.RealDictCursor)

        req.email = req.email.strip().lower()

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
    except Exception as e:
        return {"status": "error", "message": f"Registration Error: {str(e)}"}


# ---------------- LOGIN ----------------
@app.post("/login")
def login(req: LoginRequest):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    req.email = req.email.strip().lower()

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

    cursor.execute("SELECT id FROM users WHERE email=%s", (req.email,))
    if not cursor.fetchone():
        return {"status": "error", "msg": "Email not found"}

    otp = str(random.randint(100000, 999999))
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)

    cursor.execute(
        "UPDATE users SET reset_otp=%s, otp_expiry=%s WHERE email=%s",
        (otp, expiry, req.email)
    )
    db.commit()

    success, msg = send_email_otp(req.email, otp)
    if success:
        return {"status": "success"}
    else:
        # Check if it is a sandbox restriction error
        if "sandbox" in msg.lower() or "testing emails" in msg.lower():
            return {"status": "success", "sandbox_otp": otp}
        return {"status": "error", "msg": msg}


# ---------------- VERIFY OTP ----------------
@app.post("/verify_otp")
def verify_otp(req: OtpVerifyRequest):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

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
def get_profile(email: str, request: Request):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    email = email.strip().lower()

    cursor.execute(
        "SELECT username,bio,profile_image FROM users WHERE email=%s",
        (email,)
    )
    user = cursor.fetchone()

    if user and user["profile_image"]:
        base_url = str(request.base_url).rstrip('/')
        user["profile_image"] = f"{base_url}/{user['profile_image']}"

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
    email = email.strip().lower()

    image_path = None

    if photo:
        filename = f"{int(datetime.datetime.now().timestamp())}_{photo.filename}"
        path = os.path.join(UPLOAD_DIR, filename)

        with open(path, "wb") as buffer:
            shutil.copyfileobj(photo.file, buffer)

        image_path = f"uploads/{filename}"

    if image_path:
        cursor.execute(
            "UPDATE users SET username=%s, bio=%s, profile_image=%s WHERE email=%s",
            (name, bio, image_path, email)
        )
    else:
        cursor.execute(
            "UPDATE users SET username=%s, bio=%s WHERE email=%s",
            (name, bio, email)
        )
    
    db.commit()

    return {"status": "success"}


# ---------------- SAVE SESSION ----------------
@app.post("/save_session")
def save_session(req: SessionSaveRequest):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    req.email = req.email.strip().lower()

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
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    email = email.strip().lower()

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
    try:
        db = get_db()
        cursor = db.cursor(cursor_factory=extras.RealDictCursor)

        req.clinic_email = req.clinic_email.strip().lower()

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
    except Exception as e:
        return {"status": "error", "message": f"Doctor Registration Error: {str(e)}"}


# ---------------- DOCTOR LOGIN ----------------
@app.post("/doctor_login")
def doctor_login(req: DoctorLoginRequest):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    req.clinic_email = req.clinic_email.strip().lower()

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

    cursor.execute("SELECT id FROM doctors WHERE clinic_email=%s", (req.email,))
    if not cursor.fetchone():
        return {"status": "error", "msg": "Doctor email not found"}

    otp = str(random.randint(100000, 999999))
    expiry = datetime.datetime.now() + datetime.timedelta(minutes=10)

    cursor.execute(
        "UPDATE doctors SET reset_otp=%s, otp_expiry=%s WHERE clinic_email=%s",
        (otp, expiry, req.email)
    )
    db.commit()

    success, msg = send_email_otp(req.email, otp)
    if success:
        return {"status": "success"}
    else:
        # Check if it is a sandbox restriction error
        if "sandbox" in msg.lower() or "testing emails" in msg.lower():
            return {"status": "success", "sandbox_otp": otp}
        return {"status": "error", "msg": msg}

# ---------------- DOCTOR VERIFY OTP ----------------
@app.post("/doctor_verify_otp")
def doctor_verify_otp(req: OtpVerifyRequest):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

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
def get_doctor_profile(email: str, request: Request):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)

    email = email.strip().lower()

    cursor.execute(
        "SELECT full_name as username, bio, profile_image FROM doctors WHERE clinic_email=%s",
        (email,)
    )
    doctor = cursor.fetchone()

    if doctor and doctor["profile_image"]:
        base_url = str(request.base_url).rstrip('/')
        doctor["profile_image"] = f"{base_url}/{doctor['profile_image']}"

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
    email = email.strip().lower()

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
def get_doctors(request: Request):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("SELECT full_name, medical_license, hospital_name, clinic_email, profile_image FROM doctors")
    doctors = cursor.fetchall()

    base_url = str(request.base_url).rstrip('/')
    for doctor in doctors:
        if doctor.get("profile_image"):
            doctor["profile_image"] = f"{base_url}/{doctor['profile_image']}"
        else:
            doctor["profile_image"] = None

    return {"status": "success", "doctors": doctors}

# ---------------- APPOINTMENTS TABLE INITIALIZATION ----------------
    db = get_db()
    cursor = db.cursor()

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
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("""
        SELECT id, doctor_email, athlete_email, athlete_name, athlete_phone,
               CAST(date AS VARCHAR) as date, CAST(time AS VARCHAR) as time, status 
        FROM appointments WHERE doctor_email=%s AND status='PENDING'
    """, (email,))
    return {"status": "success", "appointments": cursor.fetchall()}

# ---------------- GET DOCTOR HISTORY ----------------
@app.get("/get_doctor_history")
def get_door_history(email: str, request: Request):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS VARCHAR) as date, CAST(a.time AS VARCHAR) as time, a.status,
               u.profile_image
        FROM appointments a
        LEFT JOIN users u ON a.athlete_email = u.email
        WHERE a.doctor_email=%s AND a.status IN ('ACCEPTED', 'REJECTED', 'CANCELLED')
        ORDER BY a.id DESC
    """, (email,))
    rows = cursor.fetchall()
    base_url = str(request.base_url).rstrip('/')
    for row in rows:
        if row.get("profile_image"):
            row["profile_image"] = f"{base_url}/{row['profile_image']}"
        else:
            row["profile_image"] = None
    return {"status": "success", "appointments": rows}

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
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
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
def get_accepted_appointments(email: str, request: Request):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS VARCHAR) as date, CAST(a.time AS VARCHAR) as time, a.status,
               u.profile_image
        FROM appointments a
        LEFT JOIN users u ON a.athlete_email = u.email
        WHERE a.doctor_email=%s AND a.status='ACCEPTED'
        ORDER BY a.date ASC, a.time ASC
    """, (email,))
    rows = cursor.fetchall()
    base_url = str(request.base_url).rstrip('/')
    for row in rows:
        if row.get("profile_image"):
            row["profile_image"] = f"{base_url}/{row['profile_image']}"
        else:
            row["profile_image"] = None
    return {"status": "success", "appointments": rows}

# ---------------- GET ATHLETE BOOKINGS ----------------
@app.get("/get_athlete_bookings")
def get_athlete_bookings(email: str):
    db = get_db()
    cursor = db.cursor(cursor_factory=extras.RealDictCursor)
    cursor.execute("""
        SELECT a.id, a.doctor_email, a.athlete_email, a.athlete_name, a.athlete_phone,
               CAST(a.date AS VARCHAR) as date, 
               CAST(a.time AS VARCHAR) as time,
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