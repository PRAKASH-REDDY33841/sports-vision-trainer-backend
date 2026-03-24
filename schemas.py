from pydantic import BaseModel

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ForgotRequest(BaseModel):
    email: str

class OtpVerifyRequest(BaseModel):
    email: str
    otp: str

class ResetRequest(BaseModel):
    email: str
    password: str

class SessionSaveRequest(BaseModel):
    email: str
    gameType: str
    score: int
    avgReaction: int
    wrong: int
    timestamp: int

class DoctorRegisterRequest(BaseModel):
    full_name: str
    medical_license: str
    hospital_name: str
    clinic_email: str
    password: str

class DoctorLoginRequest(BaseModel):
    clinic_email: str
    password: str

class DoctorResponse(BaseModel):
    full_name: str
    medical_license: str
    hospital_name: str
    clinic_email: str

class DoctorListResponse(BaseModel):
    status: str
    doctors: list[DoctorResponse]

class AppointmentRequest(BaseModel):
    doctor_email: str
    athlete_email: str
    athlete_name: str
    athlete_phone: str
    date: str
    time: str

class UpdateStatusRequest(BaseModel):
    id: int
    status: str