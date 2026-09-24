import logging
import os
import re
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

# -------------------------------------------------------------
# 1. Dummy HTTP Server for Render
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# -------------------------------------------------------------
# 2. Setup Logging
# -------------------------------------------------------------
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# قائمة تخزين البلاغات
daily_incidents = []

(
    INCIDENT_NO, PRIORITY, LOCATION, SERVICES_SYSTEM,
    DESC_REPORTED, RECEIVED_TIME, RC, STATUS,
    DESC_TCC, TIME_CLOSED, SOLUTION, ASSOCIATED_TICKET, REMARKS
) = range(13)

LOCATION_GATES = {
    "Departure": 38,
    "Arrival": 26,
    "Departure Altanfithi": 3,
    "Arrival Altanfeethi": 3
}

ISSUES_AND_SOLUTIONS = {
    "White Screen": "Restart Application",
    "Reader Issue": "Restart Reader",
    "Gate Hanging": "Restart Gate",
    "Camera Issue": "Restart Camera",
    "PC Hanging": "Restart PC",
    "Door Issue": "Restart/Refresh Door System",
    "Sensor Issue": "Align Sensor",
    "Object Blocked Sensor": "Remove Object"
}

def format_time_uppercase(text: str) -> str:
    if not text: return ""
    text = re.sub(r'am', 'AM', text, flags=re.IGNORECASE)
    text = re.sub(r'pm', 'PM', text, flags=re.IGNORECASE)
    return text

def build_gate_keyboard(max_gates, selected_gates):
    """إنشاء لوحة مفاتيح للبوابات تتيح الاختيار المتعدد"""
    keyboard, row = [], []
    for i in range(1, max_gates + 1):
        gate_str = str(i)
        # إضافة علامة صح للبوابة المختارة
        display_text = f"✔️ {gate_str}" if gate_str in selected_gates else gate_str
        row.append(InlineKeyboardButton(display_text, callback_data=f"GATE_{gate_str}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    
    # إضافة زر التأكيد
    keyboard.append([InlineKeyboardButton("Done ✅", callback_data="GATES_DONE")])
    return keyboard

async def delete_previous_message(update: Update):
    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except Exception:
            pass

# -------------------------------------------------------------
# Error Handler & Helper
# -------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ حدث خطأ داخلي، يرجى كتابة /cancel ثم /start للمعاودة.")

async def fallback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer("⚠️ انتهت جلسة هذا الزر، أرسل /start للبدء من جديد.", show_alert=True)

# -------------------------------------------------------------
# Handlers
# -------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Welcome! Let's log a new incident report.\n\nPlease enter the Incident No (or /cancel to stop):")
    return INCIDENT_NO

async def incident_no_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['incident_no'] = update.message.text.strip()
    keyboard = [[
        InlineKeyboardButton("H (High)", callback_data="H"),
        InlineKeyboardButton("M (Medium)", callback_data="M"),
        InlineKeyboardButton("L (Low)", callback_data="L")
    ]]
    await update.message.reply_text("Select Incident priority:", reply_markup=InlineKeyboardMarkup(keyboard))
    return PRIORITY

async def priority_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['priority'] = update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['priority'] = update.message.text.strip().upper()

    keyboard = [
        [InlineKeyboardButton("Departure", callback_data="Departure")],
        [InlineKeyboardButton("Arrival", callback_data="Arrival")],
        [InlineKeyboardButton("Departure Altanfithi", callback_data="Departure Altanfithi")],
        [InlineKeyboardButton("Arrival Altanfeethi", callback_data="Arrival Altanfeethi")]
    ]
    await update.effective_chat.send_message("Select Location:", reply_markup=InlineKeyboardMarkup(keyboard))
    return LOCATION

async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        selected_location = update.callback_query.data
        await delete_previous_message(update)
    else:
        selected_location = update.message.text.strip()

    context.user_data['location'] = selected_location
    context.user_data['selected_gates'] = [] # تهيئة مصفوفة الاختيارات المتعددة

    max_gates = LOCATION_GATES.get(selected_location, 0)
    keyboard = build_gate_keyboard(max_gates, context.user_data['selected_gates'])

    await update.effective_chat.send_message(
        f"Select Services / System (Gate Numbers for {selected_location}):\n(You can select multiple gates, then press Done ✅)",
        reply_markup=InlineKeyboardMarkup(keyboard) if max_gates > 0 else None
    )
    return SERVICES_SYSTEM

async def services_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        cb_data = update.callback_query.data
        
        # عند الضغط على أحد أزرار البوابات
        if cb_data.startswith("GATE_"):
            gate_num = cb_data.split("_")[1]
            selected = context.user_data.get('selected_gates', [])
            if gate_num in selected:
                selected.remove(gate_num)
            else:
                selected.append(gate_num)
            context.user_data['selected_gates'] = selected

            # تحديث لوحة المفاتيح لتوضيح المكتمل/الملغى بدون حذف الرسالة
            max_gates = LOCATION_GATES.get(context.user_data.get('location'), 0)
            new_keyboard = build_gate_keyboard(max_gates, selected)
            await update.callback_query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(new_keyboard))
            return SERVICES_SYSTEM

        # عند الانتهاء وتأكيد الاختيار
        elif cb_data == "GATES_DONE":
            selected = context.user_data.get('selected_gates', [])
            if not selected:
                await update.callback_query.answer("⚠️ Please select at least one gate!", show_alert=True)
                return SERVICES_SYSTEM
            
            context.user_data['services'] = ", ".join(sorted(selected, key=lambda x: int(x) if x.isdigit() else x))
            await delete_previous_message(update)
    else:
        context.user_data['services'] = update.message.text.strip()

    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service", callback_data="Out of Service")])

    await update.effective_chat.send_message("Select or type Incident Description Reported:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DESC_REPORTED

async def desc_reported_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['desc_reported'] = update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['desc_reported'] = update.message.text.strip()

    await update.effective_chat.send_message("Enter Incident Received Time (e.g., 8:35PM):")
    return RECEIVED_TIME

async def received_time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['received_time'] = format_time_uppercase(update.message.text.strip())
    keyboard = [
        [InlineKeyboardButton("SW", callback_data="SW"), InlineKeyboardButton("HW", callback_data="HW")],
        [InlineKeyboardButton("Other", callback_data="Other"), InlineKeyboardButton("N/A", callback_data="N/A")]
    ]
    await update.message.reply_text("Select or type R/C:", reply_markup=InlineKeyboardMarkup(keyboard))
    return RC

async def rc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['rc'] = update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['rc'] = update.message.text.strip()

    keyboard = [
        [InlineKeyboardButton("Solved", callback_data="Solved"), InlineKeyboardButton("Closed", callback_data="Closed")],
        [InlineKeyboardButton("Pending", callback_data="Pending")]
    ]
    await update.effective_chat.send_message("Select Status:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STATUS

async def status_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['status'] = update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['status'] = update.message.text.strip()

    reported_issue = context.user_data.get('desc_reported', 'N/A')
    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service", callback_data="Out of Service")])

    await update.effective_chat.send_message(f"Reported Issue previously selected: {reported_issue}\n\nSelect or type Incident Description TCC report:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DESC_TCC

async def desc_tcc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        selected_desc = update.callback_query.data
        await delete_previous_message(update)
        if selected_desc == "Out of Service":
            keyboard = [[InlineKeyboardButton(f"Out of Service - {issue}", callback_data=f"Out of Service - {issue}")] for issue in ISSUES_AND_SOLUTIONS.keys()]
            await update.effective_chat.send_message("Out of Service selected. Select specific issue:", reply_markup=InlineKeyboardMarkup(keyboard))
            return DESC_TCC
        context.user_data['desc_tcc'] = selected_desc
    else:
        context.user_data['desc_tcc'] = update.message.text.strip()

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await update.effective_chat.send_message("Enter Time closed (e.g., 8:49PM) or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TIME_CLOSED

async def time_closed_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        raw_val = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        await delete_previous_message(update)
    else:
        raw_val = update.message.text.strip() if update.message.text != '/skip' else ""

    context.user_data['time_closed'] = format_time_uppercase(raw_val)
    desc_tcc = context.user_data.get('desc_tcc', '')
    suggested_sol = None
    
    for issue, solution in ISSUES_AND_SOLUTIONS.items():
        if issue.lower() in desc_tcc.lower():
            suggested_sol = solution
            break

    keyboard = []
    if suggested_sol:
        keyboard.append([InlineKeyboardButton(f"Suggested: {suggested_sol}", callback_data=suggested_sol)])
    
    for sol in ISSUES_AND_SOLUTIONS.values():
        if sol != suggested_sol:
            keyboard.append([InlineKeyboardButton(sol, callback_data=sol)])
    
    keyboard.append([InlineKeyboardButton("Skip >>", callback_data="SKIP")])

    await update.effective_chat.send_message(f"TCC Report Issue: {desc_tcc}\n\nSelect or type Solution:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SOLUTION

async def solution_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['solution'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['solution'] = update.message.text.strip() if update.message.text != '/skip' else ""

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await update.effective_chat.send_message("Enter Associated ticket or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASSOCIATED_TICKET

async def associated_ticket_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['associated_ticket'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['associated_ticket'] = update.message.text.strip() if update.message.text != '/skip' else ""

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await update.effective_chat.send_message("Enter Remarks or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return REMARKS

async def remarks_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['remarks'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        await delete_previous_message(update)
    else:
        context.user_data['remarks'] = update.message.text.strip() if update.message.text != '/skip' else ""

    data = context.user_data
    today_date = datetime.now().strftime("%d/%m/%Y")

    # حفظ البلاغ الحالي
    new_entry = {
        "incident_no": data.get('incident_no', ''),
        "priority": data.get('priority', ''),
        "services": data.get('services', ''),
        "location": data.get('location', ''),
        "desc_reported": data.get('desc_reported', ''),
        "received_time": data.get('received_time', ''),
        "rc": data.get('rc', ''),
        "status": data.get('status', ''),
        "desc_tcc": data.get('desc_tcc', ''),
        "time_closed": data.get('time_closed', ''),
        "solution": data.get('solution', ''),
        "associated_ticket": data.get('associated_ticket', ''),
        "remarks": data.get('remarks', ''),
        "date": today_date
    }
    
    daily_incidents.append(new_entry)

    # جلب جميع البلاغات المسجلة بنفس رقم التكت لجمعها معاً
    target_inc_no = data.get('incident_no', '')
    matching_incidents = [inc for inc in daily_incidents if inc.get('incident_no') == target_inc_no]

    # بناء نص التقرير للجميع
    reports = []
    for inc in matching_incidents:
        single_report = (
            f"*Incident No:* {inc.get('incident_no', '')}\n"
            f"*Incident priority:* {inc.get('priority', '')}\n"
            f"*Services / System:* {inc.get('services', '')}\n"
            f"*Location:* {inc.get('location', '')}\n"
            f"*Incident Description Reported:* {inc.get('desc_reported', '')}\n"
            f"*Incident Received Time:* {inc.get('received_time', '')}\n\n"
            f"*R/C:* {inc.get('rc', '')}\n"
            f"*Status:* {inc.get('status', '')}\n"
            f"*Incident Description TCC report:* {inc.get('desc_tcc', '')}\n"
            f"*Time closed:* {inc.get('time_closed', '')}\n"
            f"*Solution:* {inc.get('solution', '')}\n"
            f"*Associated ticket:* {inc.get('associated_ticket', '')}\n"
            f"*Remarks:* {inc.get('remarks', '')}"
        )
        reports.append(single_report)

    # دمج التظليلات بفاصل الخطين (----)
    final_output = "\n\n—-\n\n".join(reports)

    await update.effective_chat.send_message(final_output)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Cancelled.')
    return ConversationHandler.END

def main():
    TOKEN ="8834717500:AAGgBsyFFjY3bRjTikV10TRbbpxpGOlkR8A"
    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INCIDENT_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, incident_no_chosen)],
            PRIORITY: [CallbackQueryHandler(priority_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, priority_chosen)],
            LOCATION: [CallbackQueryHandler(location_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, location_chosen)],
            SERVICES_SYSTEM: [CallbackQueryHandler(services_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, services_chosen)],
            DESC_REPORTED: [CallbackQueryHandler(desc_reported_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, desc_reported_chosen)],
            RECEIVED_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_time_chosen)],
            RC: [CallbackQueryHandler(rc_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, rc_chosen)],
            STATUS: [CallbackQueryHandler(status_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, status_chosen)],
            DESC_TCC: [CallbackQueryHandler(desc_tcc_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, desc_tcc_chosen)],
            TIME_CLOSED: [CallbackQueryHandler(time_closed_chosen), CommandHandler('skip', time_closed_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, time_closed_chosen)],
            SOLUTION: [CallbackQueryHandler(solution_chosen), CommandHandler('skip', solution_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, solution_chosen)],
            ASSOCIATED_TICKET: [CallbackQueryHandler(associated_ticket_chosen), CommandHandler('skip', associated_ticket_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, associated_ticket_chosen)],
            REMARKS: [CallbackQueryHandler(remarks_chosen), CommandHandler('skip', remarks_chosen), MessageHandler(filters.TEXT & ~filters.COMMAND, remarks_chosen)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(fallback_callback))
    application.add_error_handler(error_handler)

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
