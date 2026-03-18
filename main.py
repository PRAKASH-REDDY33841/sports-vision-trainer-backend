from fastapi import FastAPI, UploadFile, File, Form
from schemas import *
from database import get_db
from auth import hash_password, verify_password
import random, datetime, os, shutil

# ✅ EMAIL IMPORTS
import smtplib
from email.mime.text import MIMEText

# ✅ NEW IMPORT (ADDED)
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# ✅ NEW LINE (ADDED)
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


# ---------------- REGISTER ----------------
@app.post("/register.php")
def register(req: RegisterRequest):
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
@app.post("/login.php")
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
@app.post("/send_otp.php")
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
@app.post("/verify_otp.php")
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
@app.post("/reset_password_final.php")
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
@app.get("/get_profile.php")
def get_profile(email: str):
    db = get_db()
    cursor = db.cursor(dictionary=True)

    cursor.execute(
        "SELECT username,bio,profile_image FROM users WHERE email=%s",
        (email,)
    )
    user = cursor.fetchone()

    if user and user["profile_image"]:
        user["profile_image"] = f"http://10.19.67.111:8000/{user['profile_image']}"

    return user


# ---------------- SAVE PROFILE ----------------
@app.post("/save_profile.php")
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