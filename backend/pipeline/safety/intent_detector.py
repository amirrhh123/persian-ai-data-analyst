import re
from typing import Dict, List, Tuple, Any


class SafetyIntentDetector:
    DANGEROUS_KEYWORDS_EN = [
        "DELETE", "UPDATE", "INSERT", "DROP", "ALTER", "TRUNCATE",
        "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
        "MODIFY", "CHANGE", "REMOVE", "ADD", "INSERT INTO",
        "UPDATE SET", "DELETE FROM"
    ]
    
    DANGEROUS_KEYWORDS_FA = [
        "حذف", "پاک کن", "ویرایش", "تغییر بده", "تغییر ده",
        "اضافه کن", "ثبت کن", "بروزرسانی", "به‌روزرسانی",
        "حذف کن", "پاک کردن", "ویرایش کردن", "تغییر دادن",
        "اضافه کردن", "ثبت کردن", "بروزرسانی کردن",
        "پاک کنید", "حذف کنید", "ویرایش کنید", "تغییر دهید",
        "اضافه کنید", "ثبت کنید", "بروزرسانی کنید",
        "تغییر بدهید", "به‌روزرسانی کنید",
        "دسترسی‌ها را دور بزن", "محدودیت را بردار",
        "رمز دیتابیس", "رمز عبور", "گذرواژه",
        "حذف رکورد", "پاک کردن رکورد", "ویرایش رکورد",
        "تغییر رکورد", "حذف داده", "پاک کردن داده",
        "تغییر داده", "ویرایش داده", "ثبت داده",
        "حذف اطلاعات", "پاک کردن اطلاعات", "ویرایش اطلاعات",
        "حذف حقوق", "تغییر حقوق", "ویرایش حقوق",
        "حذف دانش‌آموز", "پاک کردن دانش‌آموز", "حذف کارمند",
        "پاک کردن کارمند", "حذف مدرسه", "پاک کردن مدرسه",
        "محدودیت را حذف کن", "محدودیت را بردار",
        "دسترسی را تغییر بده", "رمز را نشان بده"
    ]
    
    CREDENTIAL_KEYWORDS = [
        "password", "secret", "token", "key", "credential",
        "password", "secret", "token", "key", "credential",
        "رمز عبور", "گذرواژه", "رمز", "توکن", "کلید",
        "اطلاعات اتصال", "连接信息"
    ]
    
    def detect(self, question: str) -> Dict[str, Any]:
        question_upper = question.upper()
        
        for keyword in self.DANGEROUS_KEYWORDS_EN:
            if keyword.upper() in question_upper:
                return {
                    "is_safe": False,
                    "rejection_reason": f"عملیات {keyword} مجاز نیست - فقط خواندن داده‌ها مجاز است."
                }
        
        for keyword in self.DANGEROUS_KEYWORDS_FA:
            if keyword in question:
                return {
                    "is_safe": False,
                    "rejection_reason": f"عملیات '{keyword}' مجاز نیست - فقط خواندن داده‌ها مجاز است."
                }
        
        for keyword in self.CREDENTIAL_KEYWORDS:
            if keyword.lower() in question.lower():
                return {
                    "is_safe": False,
                    "rejection_reason": "نمایش اطلاعات حساس مجاز نیست."
                }
        
        return {"is_safe": True, "rejection_reason": None}


safety_detector = SafetyIntentDetector()
