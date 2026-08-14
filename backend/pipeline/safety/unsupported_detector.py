from typing import List, Dict, Any, Optional
from backend.database.models import DatabaseSchema


class UnsupportedIntentDetector:
    SUPPORTED_DOMAINS = {
        "student": ["دانش‌آموز", "دانش آموز", "محصل", "شاگرد", "مدرسه", "ثبت نام", "پایه", "امتحان"],
        "school": ["مدرسه", "آموزشگاه", "دبیرستان", "دبستان"],
        "employee": ["کارمند", "کارکن", "پرسنل", "مدیر", "دبیر", "کادر"],
        "salary": ["حقوق", "مزایا", "پرداخت", "دستمزد", "فیش"],
        "organization": ["واحد سازمانی", "سازمان", "استان", "منطقه", "اداره"],
        "ranking": ["ارتقا", "رتبه", "درخواست", "ترفیع"],
        "retirement": ["بازنشسته", "بازنشستگی"]
    }
    
    UNSUPPORTED_KEYWORDS = {
        "حمل‌ونقل": "حمل‌ونقل دانش‌آموزان",
        "حملونقل": "حملونقل دانش‌آموزان",
        "تغذیه": "تغذیه مدارس",
        "نمرات امتحان": "نمرات امتحانات نهایی",
        "نمره امتحان": "نمرات امتحانات",
        "سرقت": "اطلاعات سرقت",
        "تصادف": "حوادث"
    }
    
    UNSUPPORTED_ATTRIBUTES = [
        "نمره امتحان", "نمرات امتحان", "نمره نهایی",
        "تغذیه", "تغذیه مدارس", "سرپرستی",
        "حمل‌ونقل", "حملونقل", "اتوبوس مدرسه",
        "سرقت", "حوادث", "تصادف"
    ]
    
    def detect(self, question: str, schema: DatabaseSchema, report_tables: List[str]) -> Dict[str, Any]:
        for keyword, entity in self.UNSUPPORTED_KEYWORDS.items():
            if keyword in question:
                return {
                    "is_supported": False,
                    "reason": f"اطلاعات {entity} در پایگاه داده فعلی موجود نیست."
                }
        
        for attr in self.UNSUPPORTED_ATTRIBUTES:
            if attr in question:
                return {
                    "is_supported": False,
                    "reason": f"اطلاعات '{attr}' در پایگاه داده فعلی موجود نیست."
                }
        
        available_columns = set()
        for table in schema.tables:
            if table.name in report_tables:
                for col in table.columns:
                    available_columns.add(col.name.lower())
        
        question_words = set(question.lower().split())
        
        return {"is_supported": True, "reason": None}


unsupported_detector = UnsupportedIntentDetector()
