import os
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# -------------------------------------------------------------
# 1. خادم وهمي لإبقاء الخدمة تعمل على Render بدون توقف
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# -------------------------------------------------------------
# 2. إعداد التسجيل (Logging)
# -------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# مراحل المحادثة (States)
(
    INCIDENT_NO,
    PRIORITY,
    LOCATION,
    GATE,
    REPORTED_ISSUE,
    TIME_INCIDENT,
    RC,
    STATUS,
    TCC_REPORT,
    TIME_CLOSED,
    SOLUTION,
    ASSOCIATED_TICKET,
    REMARKS,
) = range(13)

# -------------------------------------------------------------
# 3. دالة تنسيق الوقت (تحويل am/pm إلى AM/PM)
# -------------------------------------------------------------
def format_time_input(text: str) -> str:
    val = text.strip()
    if val.lower().endswith("am"):
        return val[:-2].strip() + " AM"
    elif val.lower().endswith("pm"):
        return val[:-2].strip() + " PM"
    return val

# -------------------------------------------------------------
# 4. معالجات الخطوات (Bot Handlers)
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "مرحباً بك في بوت تسجيل البلاغات (TCC Incident Logging Bot).\n\n"
        "الرجاء إدخال رقم البلاغ (Incident No):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return INCIDENT_NO

async def get_incident_no(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["incident_no"] = update.message.text
    reply_keyboard = [["P1", "P2", "P3", "P4"]]
    await update.message.reply_text(
        "اختر مستوى الأولوية (Priority):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return PRIORITY

async def get_priority(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["priority"] = update.message.text
    reply_keyboard = [
        ["Departure", "Arrival"],
        ["Departure Altanfithi", "Arrival Altanfeethi"],
    ]
    await update.message.reply_text(
        "اختر الموقع (Location):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return LOCATION

async def get_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    location = update.message.text
    context.user_data["location"] = location

    # تحديد البوابات والخدمات بناءً على الموقع
    if location == "Departure":
        gates = [f"Gate {i}" for i in range(1, 39)]
    elif location == "Arrival":
        gates = [f"Gate {i}" for i in range(1, 27)]
    elif location in ["Departure Altanfithi", "Arrival Altanfeethi"]:
        gates = [f"Gate {i}" for i in range(1, 4)]
    else:
        gates = []

    options = gates + ["Services", "System"]
    keyboard = [options[i:i+3] for i in range(0, len(options), 3)]

    await update.message.reply_text(
        f"الموقع المحدد: {location}\nاختر البوابة أو الخدمة (Gate / Services / System):",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return GATE

async def get_gate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["gate"] = update.message.text
    await update.message.reply_text(
        "اكتب وصف المشكلة المبلغ عنها (Reported Issue):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REPORTED_ISSUE

async def get_reported_issue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["reported_issue"] = update.message.text
    await update.message.reply_text(
        "أدخل وقت الحادثة (مثال: 10:30 AM):"
    )
    return TIME_INCIDENT

async def get_time_incident(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    formatted_time = format_time_input(update.message.text)
    context.user_data["time_incident"] = formatted_time
    
    reply_keyboard = [["Hardware", "Software", "Network", "Power", "Other"]]
    await update.message.reply_text(
        "اختر السبب الجذر (R/C):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return RC

async def get_rc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["rc"] = update.message.text
    reply_keyboard = [["Open", "Closed", "Pending"]]
    await update.message.reply_text(
        "اختر حالة البلاغ (Status):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return STATUS

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["status"] = update.message.text
    issue = context.user_data.get("reported_issue", "غير محدد")
    await update.message.reply_text(
        f"📌 **المشكلة المسجلة:** {issue}\n\nاكتب تقرير TCC (TCC Report):",
        reply_markup=ReplyKeyboardRemove(),
    )
    return TCC_REPORT

async def get_tcc_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["tcc_report"] = update.message.text
    await update.message.reply_text(
        "أدخل وقت إغلاق البلاغ (Time Closed) أو اكتب N/A:"
    )
    return TIME_CLOSED

async def get_time_closed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_text = update.message.text
    if raw_text.strip().upper() != "N/A":
        formatted_time = format_time_input(raw_text)
    else:
        formatted_time = "N/A"
    context.user_data["time_closed"] = formatted_time

    issue = context.user_data.get("reported_issue", "غير محدد")
    await update.message.reply_text(
        f"📌 **المشكلة المسجلة:** {issue}\n\nاكتب الحل المقدم (Solution):"
    )
    return SOLUTION

async def get_solution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["solution"] = update.message.text
    await update.message.reply_text(
        "أدخل رقم التذكرة المرتبطة (Associated Ticket) إن وجد أو اكتب N/A:"
    )
    return ASSOCIATED_TICKET

async def get_associated_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["associated_ticket"] = update.message.text
    await update.message.reply_text(
        "اكتب الملاحظات (Remarks) إن وجدت أو اكتب None:"
    )
    return REMARKS

async def get_remarks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["remarks"] = update.message.text
    
    # تجميع التقرير النهائي
    data = context.user_data
    summary = (
        "📋 **ملخص البلاغ المسجل:**\n\n"
        f"• **Incident No:** {data.get('incident_no')}\n"
        f"• **Priority:** {data.get('priority')}\n"
        f"• **Location:** {data.get('location')}\n"
        f"• **Gate/System:** {data.get('gate')}\n"
        f"• **Reported Issue:** {data.get('reported_issue')}\n"
        f"• **Time:** {data.get('time_incident')}\n"
        f"• **R/C:** {data.get('rc')}\n"
        f"• **Status:** {data.get('status')}\n"
        f"• **TCC Report:** {data.get('tcc_report')}\n"
        f"• **Time Closed:** {data.get('time_closed')}\n"
        f"• **Solution:** {data.get('solution')}\n"
        f"• **Associated Ticket:** {data.get('associated_ticket')}\n"
        f"• **Remarks:** {data.get('remarks')}\n"
    )
    
    await update.message.reply_text(summary, parse_mode="Markdown")
    await update.message.reply_text("تم تسجيل البلاغ بنجاح! للبدء من جديد أرسل /start")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "تم إلغاء عملية التسجيل.", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

# -------------------------------------------------------------
# 5. تشغيل البوت (Main Function)
# -------------------------------------------------------------
def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("لم يتم العثور على TELEGRAM_BOT_TOKEN في متغيرات البيئة!")
        return

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            INCIDENT_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_incident_no)],
            PRIORITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_priority)],
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_location)],
            GATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_gate)],
            REPORTED_ISSUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_reported_issue)],
            TIME_INCIDENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time_incident)],
            RC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rc)],
            STATUS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_status)],
            TCC_REPORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tcc_report)],
            TIME_CLOSED: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_time_closed)],
            SOLUTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_solution)],
            ASSOCIATED_TICKET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_associated_ticket)],
            REMARKS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_remarks)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    
    logger.info("جاري تشغيل البوت...")
    application.run_polling()

if __name__ == "__main__":
    main()
