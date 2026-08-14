from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".tmp/pdfdeps").resolve()))

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "pdf" / "persian_ai_presentation_script.pdf"
FONT_REGULAR = ROOT / "vazirmatn-v33.003" / "misc" / "UI-Farsi-Digits" / "fonts" / "ttf" / "Vazirmatn-UI-FD-Regular.ttf"
FONT_BOLD = ROOT / "vazirmatn-v33.003" / "misc" / "UI-Farsi-Digits" / "fonts" / "ttf" / "Vazirmatn-UI-FD-Bold.ttf"


def fa(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def wrap_rtl(text: str, font: str, size: float, max_width: float) -> list[str]:
    words = clean(text).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        shaped = fa(candidate)
        if pdfmetrics.stringWidth(shaped, font, size) <= max_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines


class PdfWriter:
    def __init__(self) -> None:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        pdfmetrics.registerFont(TTFont("Vazir", str(FONT_REGULAR)))
        pdfmetrics.registerFont(TTFont("VazirBold", str(FONT_BOLD)))
        self.c = canvas.Canvas(str(OUT), pagesize=A4)
        self.w, self.h = A4
        self.page = 0
        self.margin_x = 18 * mm
        self.top = self.h - 18 * mm
        self.bottom = 17 * mm
        self.y = self.top

    def new_page(self, title: str | None = None) -> None:
        if self.page:
            self.footer()
            self.c.showPage()
        self.page += 1
        self.y = self.top
        self.background()
        if title:
            self.heading(title)

    def background(self) -> None:
        self.c.setFillColor(colors.HexColor("#fbfcfa"))
        self.c.rect(0, 0, self.w, self.h, fill=1, stroke=0)
        self.c.setFillColor(colors.white)
        self.c.roundRect(10 * mm, 10 * mm, self.w - 20 * mm, self.h - 20 * mm, 12, fill=1, stroke=0)

    def footer(self) -> None:
        self.c.setStrokeColor(colors.HexColor("#e6ebe1"))
        self.c.line(self.margin_x, 13 * mm, self.w - self.margin_x, 13 * mm)
        self.c.setFont("Vazir", 8)
        self.c.setFillColor(colors.HexColor("#899184"))
        self.c.drawRightString(self.w - self.margin_x, 8 * mm, fa("Persian AI Data Analyst"))
        self.c.drawString(self.margin_x, 8 * mm, str(self.page))

    def ensure(self, height: float) -> None:
        if self.y - height < self.bottom:
            self.new_page()

    def heading(self, text: str) -> None:
        self.ensure(28)
        self.c.setFont("VazirBold", 16)
        self.c.setFillColor(colors.HexColor("#1f5b3b"))
        self.c.drawRightString(self.w - self.margin_x, self.y, fa(text))
        self.y -= 8
        self.c.setStrokeColor(colors.HexColor("#dfe8d8"))
        self.c.setLineWidth(1.2)
        self.c.line(self.margin_x, self.y, self.w - self.margin_x, self.y)
        self.y -= 17

    def subheading(self, text: str) -> None:
        self.ensure(20)
        self.c.setFont("VazirBold", 11.5)
        self.c.setFillColor(colors.HexColor("#35523d"))
        self.c.drawRightString(self.w - self.margin_x, self.y, fa(text))
        self.y -= 16

    def paragraph(self, text: str, size: float = 10.2, lead: float = 17, color: str = "#263127", indent: float = 0) -> None:
        max_width = self.w - 2 * self.margin_x - indent
        lines = wrap_rtl(text, "Vazir", size, max_width)
        self.ensure(len(lines) * lead + 5)
        self.c.setFont("Vazir", size)
        self.c.setFillColor(colors.HexColor(color))
        for line in lines:
            self.c.drawRightString(self.w - self.margin_x - indent, self.y, fa(line))
            self.y -= lead
        self.y -= 3

    def box(self, paragraphs: list[str], title: str | None = None) -> None:
        line_count = sum(len(wrap_rtl(p, "Vazir", 10, self.w - 2 * self.margin_x - 18)) for p in paragraphs)
        height = 18 + line_count * 16 + (16 if title else 0)
        self.ensure(height + 8)
        x = self.margin_x
        y0 = self.y - height + 8
        self.c.setFillColor(colors.HexColor("#f8fbf5"))
        self.c.setStrokeColor(colors.HexColor("#dfe5d9"))
        self.c.roundRect(x, y0, self.w - 2 * self.margin_x, height, 8, fill=1, stroke=1)
        self.y -= 11
        if title:
            self.c.setFont("VazirBold", 10.5)
            self.c.setFillColor(colors.HexColor("#1f5b3b"))
            self.c.drawRightString(self.w - self.margin_x - 7, self.y, fa(title))
            self.y -= 15
        for p in paragraphs:
            self.paragraph(p, size=9.8, lead=15.5, indent=7)
        self.y = y0 - 10

    def demo(self, text: str) -> None:
        self.ensure(24)
        x = self.margin_x
        h = 22
        self.c.setFillColor(colors.HexColor("#eef5e9"))
        self.c.roundRect(x, self.y - h + 6, self.w - 2 * self.margin_x, h, 7, fill=1, stroke=0)
        self.c.setFont("VazirBold", 10.5)
        self.c.setFillColor(colors.HexColor("#173b2a"))
        self.c.drawRightString(self.w - self.margin_x - 8, self.y - 9, fa(text))
        self.y -= 28

    def bullet(self, text: str) -> None:
        self.ensure(18)
        self.c.setFont("VazirBold", 10)
        self.c.setFillColor(colors.HexColor("#1f5b3b"))
        self.c.drawRightString(self.w - self.margin_x, self.y, fa("•"))
        self.paragraph(text, size=9.9, lead=15, indent=10)

    def cover(self) -> None:
        self.page += 1
        self.background()
        self.c.setFillColor(colors.HexColor("#e8efe1"))
        self.c.roundRect(20 * mm, 42 * mm, self.w - 40 * mm, self.h - 84 * mm, 18, fill=1, stroke=0)
        self.c.setFillColor(colors.white)
        self.c.roundRect(23 * mm, 45 * mm, self.w - 46 * mm, self.h - 90 * mm, 16, fill=1, stroke=0)
        self.c.setFont("VazirBold", 24)
        self.c.setFillColor(colors.HexColor("#1f5b3b"))
        self.c.drawCentredString(self.w / 2, self.h - 95 * mm, fa("متن ارائه ۵ تا ۶ دقیقه‌ای"))
        self.c.drawCentredString(self.w / 2, self.h - 110 * mm, fa("پروژه تحلیلگر هوشمند فارسی"))
        self.c.setFont("Vazir", 13)
        self.c.setFillColor(colors.HexColor("#536052"))
        self.c.drawCentredString(self.w / 2, self.h - 130 * mm, fa("پرسش فارسی از دیتابیس، تولید SQL، اجرای امن و نمایش در UI"))
        self.c.setFillColor(colors.HexColor("#e7efdf"))
        self.c.roundRect(self.w / 2 - 38 * mm, self.h - 153 * mm, 76 * mm, 11 * mm, 14, fill=1, stroke=0)
        self.c.setFont("VazirBold", 10.5)
        self.c.setFillColor(colors.HexColor("#1f5b3b"))
        self.c.drawCentredString(self.w / 2, self.h - 149 * mm, fa("نسخه مناسب ارائه به کارفرما"))

    def save(self) -> None:
        self.footer()
        self.c.save()


def build() -> None:
    pdf = PdfWriter()
    pdf.cover()

    pdf.new_page("۱. شروع ارائه - حدود ۴۵ ثانیه")
    pdf.box([
        "سلام، وقت بخیر. امروز می‌خواهم نسخه دمو از یک تحلیلگر هوشمند فارسی را نشان بدهم که هدفش ساده‌تر کردن دسترسی به داده‌های سازمانی است.",
        "ایده اصلی این است که کاربر لازم نباشد SQL بلد باشد یا ساختار دیتابیس را حفظ کند. کاربر سؤالش را فارسی می‌پرسد؛ سیستم سؤال را تحلیل می‌کند، موجودیت‌های مرتبط را تشخیص می‌دهد، SQL مناسب تولید می‌کند، آن را اعتبارسنجی می‌کند و در نهایت خروجی را در یک UI خوانا نمایش می‌دهد.",
        "این دمو روی دیتابیس آموزشی شامل دانش‌آموزان، کارمندان، مدارس، واحدهای سازمانی، حقوق و سوابق بازنشستگی آماده شده؛ ولی معماری طوری طراحی شده که روی دیتابیس مشابه سازمان اصلی هم قابل توسعه باشد.",
    ])

    pdf.heading("۲. مسئله‌ای که حل می‌کنیم - حدود ۵۰ ثانیه")
    pdf.box([
        "در خیلی از سازمان‌ها داده‌ها وجود دارند، اما دسترسی عملی به آن‌ها سخت است. معمولاً برای گرفتن یک جواب ساده، مثل تعداد دانش‌آموزان یک استان یا اطلاعات یک کارمند خاص، باید یا گزارش آماده وجود داشته باشد یا از تیم فنی SQL درخواست شود.",
        "مشکل دوم این است که سؤال‌های واقعی کاربران همیشه ساده نیستند. مثلاً کاربر می‌پرسد: «دانش‌آموزان فعال پایه دهم استان تهران» یا «میانگین حقوق سال ۱۴۰۳ کارمندان فعال استان تهران با شغل دبیر». این‌ها چند فیلتر همزمان دارند و اگر سیستم فقط کلمات کلیدی را ساده جست‌وجو کند، جواب اشتباه می‌دهد.",
        "تمرکز این پروژه دقیقاً روی همین نقطه است: فهم فارسی، تشخیص رابطه بین جدول‌ها، ساختن SQL درست، و جلوگیری از خروجی‌های گمراه‌کننده.",
    ])

    pdf.new_page("۳. مسیر پردازش سیستم - حدود ۶۰ ثانیه")
    pdf.box([
        "سؤال فارسی ← تشخیص نیت ← انتخاب موجودیت ← استخراج فیلترها ← ساخت SQL ← اعتبارسنجی ← اجرای امن ← نمایش خروجی",
    ], title="جریان کلی سیستم")
    pdf.box([
        "از نظر فنی، سیستم چند لایه دارد. لایه اول سؤال فارسی را نرمال‌سازی و نیت کاربر را استخراج می‌کند: مثلاً آیا سؤال درباره دانش‌آموز است، کارمند است، مدرسه است یا حقوق؟ آیا سؤال شمارشی است، لیستی است، رتبه‌بندی است یا اطلاعات کامل یک رکورد را می‌خواهد؟",
        "لایه بعدی فیلترها را استخراج می‌کند؛ مثل استان، شهر، نام، نام خانوادگی، کد ملی، پایه، وضعیت، شغل، نوع مدرسه، سال ثبت‌نام یا سال پرداخت حقوق.",
        "بعد سیستم براساس semantic layer می‌فهمد برای جواب دادن باید کدام جدول‌ها join شوند. برای نمونه، فیلتر استان دانش‌آموز مستقیم روی جدول students نیست و باید از مسیر students به schools و بعد organization_units برسیم.",
        "در مرحله آخر SQL ساخته شده اعتبارسنجی می‌شود تا اگر سؤال شمارشی است واقعاً COUNT داشته باشد، اگر کد ملی است به شکل text فیلتر شود، و اگر join لازم است فراموش نشده باشد.",
    ])

    pdf.heading("۴. نکات مهمی که قوی‌تر شده")
    for item in [
        "پشتیبانی بهتر از فیلترهای ترکیبی برای دانش‌آموزان، کارمندان، مدارس و حقوق.",
        "تشخیص صحیح سؤال‌های «تعداد» و جلوگیری از برگرداندن لیست به جای شمارش.",
        "پشتیبانی از کد ملی برای دانش‌آموز و کارمند به عنوان شناسه متنی.",
        "تشخیص «سنوات» به عنوان pension amount در سوابق بازنشستگی، نه میانگین حقوق.",
        "نمایش مرتب‌تر خروجی‌های طولانی در UI.",
    ]:
        pdf.bullet(item)

    pdf.new_page("۵. بخش دمو - حدود ۲ تا ۳ دقیقه")
    demos = [
        ("سؤال اول - شمارش ساده اما با join درست", "تعداد دانش آموزان استان تهران را بگو", "اینجا سیستم باید بفهمد استان دانش‌آموز از خود جدول دانش‌آموز نمی‌آید و باید از مسیر مدرسه و واحد سازمانی فیلتر شود. این برای دیتابیس‌های واقعی خیلی مهم است."),
        ("سؤال دوم - فیلتر ترکیبی دانش‌آموز", "دانش آموزان فعال پایه دهم استان تهران", "در این سؤال چند شرط همزمان داریم: وضعیت فعال، پایه دهم و استان تهران. سیستم باید همه این شروط را در SQL نگه دارد و فقط یکی از آن‌ها را انتخاب نکند."),
        ("سؤال سوم - اطلاعات با کد ملی", "کارمند با کد ملی 4871587050 وضعیت و شغل و اسم و فامیل و تمام ستون ها", "اینجا کد ملی به عنوان شناسه دقیق استفاده می‌شود و خروجی باید اطلاعات پروفایل کارمند را برگرداند. این نمونه برای جست‌وجوی مستقیم اشخاص مناسب است."),
        ("سؤال چهارم - حقوق با فیلترهای ترکیبی", "میانگین حقوق سال ۱۴۰۳ کارمندان فعال استان تهران با شغل دبیر", "این سؤال نشان می‌دهد سیستم فقط روی یک جدول کار نمی‌کند. هم جدول حقوق لازم است، هم کارمندان، هم واحد سازمانی؛ و فیلترهای سال، وضعیت، استان و شغل باید با هم اعمال شوند."),
    ]
    for title, question, note in demos:
        pdf.subheading(title)
        pdf.demo(question)
        pdf.paragraph(note)

    pdf.new_page("۶. ادامه دمو و جمع‌بندی - حدود ۹۰ ثانیه")
    pdf.subheading("سؤال پنجم - رتبه‌بندی یا بیشترین/کمترین")
    pdf.demo("برای کدام کارمند کمترین سنوات پرداخت شده؟")
    pdf.paragraph("در این نمونه سیستم باید بفهمد منظور از سنوات در این پروژه مبلغ pension amount است و باید از جدول سوابق بازنشستگی استفاده کند، نه اینکه اشتباهاً میانگین حقوق را برگرداند.")

    pdf.subheading("اگر زمان اضافه بود")
    pdf.demo("تعداد مدارس دولتی استان تهران با ظرفیت بالای ۵۰۰")
    pdf.demo("تعداد مدارس و دانش آموزان هر استان")

    pdf.heading("۷. جمله پایانی پیشنهادی")
    pdf.box([
        "جمع‌بندی من این است که این پروژه یک رابط ساده برای پرسیدن سؤال فارسی از دیتابیس است، اما پشت آن چند لایه کنترل وجود دارد: فهم نیت، semantic layer، تولید SQL، اعتبارسنجی و نمایش قابل فهم.",
        "مزیت اصلی برای سازمان این است که کاربرهای غیر فنی می‌توانند سریع‌تر به جواب برسند، تیم فنی کمتر درگیر گزارش‌های تکراری شود، و تحلیل داده به جای اینکه وابسته به SQL دستی باشد، به یک فرآیند قابل توسعه تبدیل شود.",
        "مرحله بعدی می‌تواند اتصال به دیتابیس اصلی، کامل‌تر کردن semantic layer براساس جدول‌های واقعی، و اضافه کردن سطح دسترسی و لاگ برای استفاده سازمانی باشد.",
    ])
    pdf.box([
        "قبل از ارائه، Docker، API و UI را روشن کن و ۴ سؤال اصلی را یک بار تمرین کن. بهتر است هنگام ارائه SQL را هم کوتاه نشان بدهی تا مشخص شود سیستم فقط متن تولید نمی‌کند، بلکه واقعاً query قابل اجرا می‌سازد.",
    ], title="نکته برای اجرا")

    pdf.save()


if __name__ == "__main__":
    build()
    print(OUT)
