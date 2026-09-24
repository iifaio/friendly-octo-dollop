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

def build_gate_keyboard(max_gates):
    keyboard, row = [], []
    for i in range(1, max_gates + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=str(i)))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
    return keyboard

# -------------------------------------------------------------
# Error Handler & Helper
# -------------------------------------------------------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ حدث خطأ داخلي في البوت، يرجى كتابة /cancel ثم /start للمعاودة.")

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
    context.user_data['incident_no'] = update.message.text
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
        msg_target = update.callback_query.message
    else:
        context.user_data['priority'] = update.message.text.strip().upper()
        msg_target = update.message

    keyboard = [
        [InlineKeyboardButton("Departure", callback_data="Departure")],
        [InlineKeyboardButton("Arrival", callback_data="Arrival")],
        [InlineKeyboardButton("Departure Altanfithi", callback_data="Departure Altanfithi")],
        [InlineKeyboardButton("Arrival Altanfeethi", callback_data="Arrival Altanfeethi")]
    ]
    await msg_target.reply_text("Select Location:", reply_markup=InlineKeyboardMarkup(keyboard))
    return LOCATION

async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        selected_location = update.callback_query.data
        msg_target = update.callback_query.message
    else:
        selected_location = update.message.text
        msg_target = update.message

    context.user_data['location'] = selected_location
    max_gates = LOCATION_GATES.get(selected_location, 0)
    keyboard = build_gate_keyboard(max_gates)

    await msg_target.reply_text(f"Select Services / System (Gate Number for {selected_location}):", reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None)
    return SERVICES_SYSTEM

async def services_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['services'] = update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['services'] = update.message.text
        msg_target = update.message

    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service", callback_data="Out of Service")])

    await msg_target.reply_text("Select or type Incident Description Reported:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DESC_REPORTED

async def desc_reported_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['desc_reported'] = update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['desc_reported'] = update.message.text
        msg_target = update.message

    await msg_target.reply_text("Enter Incident Received Time (e.g., 8:35PM):")
    return RECEIVED_TIME

async def received_time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['received_time'] = format_time_uppercase(update.message.text)
    keyboard = [
        [InlineKeyboardButton("SW", callback_data="SW"), InlineKeyboardButton("HW", callback_data="HW")],
        [InlineKeyboardButton("N/A", callback_data="N/A")]
    ]
    await update.message.reply_text("Select or type R/C:", reply_markup=InlineKeyboardMarkup(keyboard))
    return RC

async def rc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['rc'] = update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['rc'] = update.message.text
        msg_target = update.message

    keyboard = [
        [InlineKeyboardButton("Solved", callback_data="Solved"), InlineKeyboardButton("Closed", callback_data="Closed")],
        [InlineKeyboardButton("Pending", callback_data="Pending")]
    ]
    await update.message.reply_text("Select Status:", reply_markup=InlineKeyboardMarkup(keyboard))
    return STATUS

async def status_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['status'] = update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['status'] = update.message.text
        msg_target = update.message

    reported_issue = context.user_data.get('desc_reported', 'N/A')
    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service", callback_data="Out of Service")])

    await msg_target.reply_text(f"Reported Issue previously selected: {reported_issue}\n\nSelect or type Incident Description TCC report:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DESC_TCC

async def desc_tcc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        selected_desc = update.callback_query.data
        if selected_desc == "Out of Service":
            keyboard = [[InlineKeyboardButton(f"Out of Service - {issue}", callback_data=f"Out of Service - {issue}")] for issue in ISSUES_AND_SOLUTIONS.keys()]
            await update.callback_query.message.reply_text("Out of Service selected. Select specific issue:", reply_markup=InlineKeyboardMarkup(keyboard))
            return DESC_TCC
        context.user_data['desc_tcc'] = selected_desc
        msg_target = update.callback_query.message
    else:
        context.user_data['desc_tcc'] = update.message.text
        msg_target = update.message

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await msg_target.reply_text("Enter Time closed (e.g., 8:49PM) or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return TIME_CLOSED

async def time_closed_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        raw_val = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        msg_target = update.callback_query.message
    else:
        raw_val = update.message.text if update.message.text != '/skip' else ""
        msg_target = update.message

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

    await msg_target.reply_text(f"TCC Report Issue: {desc_tcc}\n\nSelect or type Solution:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SOLUTION

async def solution_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['solution'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['solution'] = update.message.text if update.message.text != '/skip' else ""
        msg_target = update.message

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await msg_target.reply_text("Enter Associated ticket or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ASSOCIATED_TICKET

async def associated_ticket_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['associated_ticket'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
        msg_target = update.callback_query.message
    else:
        context.user_data['associated_ticket'] = update.message.text if update.message.text != '/skip' else ""
        msg_target = update.message

    keyboard = [[InlineKeyboardButton("Skip >>", callback_data="SKIP")]]
    await msg_target.reply_text("Enter Remarks or press Skip:", reply_markup=InlineKeyboardMarkup(keyboard))
    return REMARKS

async def remarks_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        context.user_data['remarks'] = "" if update.callback_query.data == "SKIP" else update.callback_query.data
    else:
        context.user_data['remarks'] = update.message.text if update.message.text != '/skip' else ""

    data = context.user_data
    today_date = datetime.now().strftime("%d/%m/%Y")

    daily_incidents.append({
        "Area": data.get('location', ''),
        "Gate": data.get('services', ''),
        "Ticket number": data.get('incident_no', ''),
        "Open Time": data.get('received_time', ''),
        "Open Date": today_date,
        "Issue": data.get('desc_tcc', '') or data.get('desc_reported', ''),
        "Resolution": data.get('solution', ''),
        "Close time": data.get('time_closed', ''),
        "Close Date": today_date if data.get('time_closed') else '',
        "Status": data.get('status', ''),
        "Comments": data.get('remarks', '')
    })

    # تنسيق بالنجمة الواحدة لتسليم النتيجة بنسق عريض (Bold) للواتساب:
    output = (
        f"*Incident No:* {data.get('incident_no', '')}\n"
        f"*Incident priority:* {data.get('priority', '')}\n"
        f"*Services / System:* {data.get('services', '')}\n"
        f"*Location:* {data.get('location', '')}\n"
        f"*Incident Description Reported:* {data.get('desc_reported', '')}\n"
        f"*Incident Received Time:* {data.get('received_time', '')}\n\n"
        f"*R/C:* {data.get('rc', '')}\n"
        f"*Status:* {data.get('status', '')}\n"
        f"*Incident Description TCC report:* {data.get('desc_tcc', '')}\n"
        f"*Time closed:* {data.get('time_closed', '')}\n"
        f"*Solution:* {data.get('solution', '')}\n"
        f"*Associated ticket:* {data.get('associated_ticket', '')}\n"
        f"*Remarks:* {data.get('remarks', '')}"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(output)
    else:
        await update.message.reply_text(output)
        
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
