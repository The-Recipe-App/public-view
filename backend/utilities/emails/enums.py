# api/v1/auth/emails/enums.py
from enum import Enum

class EmailKind(str, Enum):
    OTP = "otp"
    WELCOME = "welcome"
    ACTIVATION = "activation"
    PASSWORD_CHANGE_OTP = "password_change_otp"
    PASSWORD_CHANGED = "password_changed"
    NEW_DEVICE_LOGIN_OTP = "new_device_login_otp"
    
    