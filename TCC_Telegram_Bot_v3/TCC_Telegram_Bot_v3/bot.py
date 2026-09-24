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
# 1. Health check server for Render (Keeps the service alive)
# -------------------------------------------------------------
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()

# -------------------------------------------------------------
# 2. Logging Setup
# -------------------------------------------------------------
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# -------------------------------------------------------------
# 3. Daily Incidents Database (In-Memory)
# -------------------------------------------------------------
daily_incidents = []

# حالات المحادثة
(
    INCIDENT_NO,
    PRIORITY,
    LOCATION,
    SERVICES_SYSTEM,
    DESC_REPORTED,
    RECEIVED_TIME,
    RC,
    STATUS,
    DESC_TCC,
    TIME_CLOSED,
    SOLUTION,
    ASSOCIATED_TICKET,
    REMARKS
) = range(13)

# أعداد البوابات لكل موقع
LOCATION_GATES = {
    "Departure": 38,
    "Arrival": 26,
    "Departure Altanfithi": 3,
    "Arrival Altanfeethi": 3
}

# قائمة الأعطال وحلولها المقترنة
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

# دالة مساعدة لتكبير am/pm في نصوص الوقت
def format_time_uppercase(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'am', 'AM', text, flags=re.IGNORECASE)
    text = re.sub(r'pm', 'PM', text, flags=re.IGNORECASE)
    return text

# دالة مساعدة لإنشاء أزرار البوابات (5 بوابات في كل صف)
def build_gate_keyboard(max_gates):
    keyboard = []
    row = []
    for i in range(1, max_gates + 1):
        row.append(InlineKeyboardButton(str(i), callback_data=str(i)))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return keyboard

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Welcome! Let's log a new incident report.\n\n"
        "Please enter the *Incident No* (or send /cancel to stop):",
        parse_mode='Markdown'
    )
    return INCIDENT_NO

async def incident_no_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['incident_no'] = update.message.text
    
    keyboard = [
        [
            InlineKeyboardButton("H (High)", callback_data="H"),
            InlineKeyboardButton("M (Medium)", callback_data="M"),
            InlineKeyboardButton("L (Low)", callback_data="L")
        ]
    ]
    await update.message.reply_text(
        "Select *Incident priority*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return PRIORITY

async def priority_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['priority'] = query.data

    keyboard = [
        [InlineKeyboardButton("Departure", callback_data="Departure")],
        [InlineKeyboardButton("Arrival", callback_data="Arrival")],
        [InlineKeyboardButton("Departure Altanfithi", callback_data="Departure Altanfithi")],
        [InlineKeyboardButton("Arrival Altanfeethi", callback_data="Arrival Altanfeethi")]
    ]
    await query.edit_message_text(
        "Select *Location*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return LOCATION

async def location_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    selected_location = query.data
    context.user_data['location'] = selected_location

    max_gates = LOCATION_GATES.get(selected_location, 0)
    keyboard = build_gate_keyboard(max_gates)

    await query.edit_message_text(
        f"Select *Services / System* (Gate Number for {selected_location}):",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SERVICES_SYSTEM

async def services_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['services'] = query.data
        msg_func = query.edit_message_text
    else:
        context.user_data['services'] = update.message.text
        msg_func = update.message.reply_text

    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service", callback_data="Out of Service")])

    await msg_func(
        "Select or type *Incident Description Reported*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return DESC_REPORTED

async def desc_reported_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['desc_reported'] = query.data
        msg_func = query.edit_message_text
    else:
        context.user_data['desc_reported'] = update.message.text
        msg_func = update.message.reply_text

    await msg_func(
        "Enter *Incident Received Time* (e.g., 8:35PM):",
        parse_mode='Markdown'
    )
    return RECEIVED_TIME

async def received_time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    formatted_time = format_time_uppercase(update.message.text)
    context.user_data['received_time'] = formatted_time
    
    keyboard = [
        [InlineKeyboardButton("SW", callback_data="SW"), InlineKeyboardButton("HW", callback_data="HW")],
        [InlineKeyboardButton("N/A", callback_data="N/A")]
    ]
    await update.message.reply_text(
        "Select or type *R/C*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return RC

async def rc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['rc'] = query.data
        msg_func = query.edit_message_text
    else:
        context.user_data['rc'] = update.message.text
        msg_func = update.message.reply_text

    keyboard = [
        [InlineKeyboardButton("Solved", callback_data="Solved"), InlineKeyboardButton("Closed", callback_data="Closed")],
        [InlineKeyboardButton("Pending", callback_data="Pending")]
    ]
    await msg_func(
        "Select *Status*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return STATUS

async def status_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data['status'] = query.data

    reported_issue = context.user_data.get('desc_reported', 'N/A')

    keyboard = [[InlineKeyboardButton(issue, callback_data=issue)] for issue in ISSUES_AND_SOLUTIONS.keys()]
    keyboard.append([InlineKeyboardButton("Out of Service ⚠️", callback_data="Out of Service")])

    await query.edit_message_text(
        f"📌 *Reported Issue previously selected:* `{reported_issue}`\n\n"
        f"Select or type *Incident Description TCC report*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return DESC_TCC

async def desc_tcc_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        selected_desc = query.data
        
        if selected_desc == "Out of Service":
            keyboard = [[InlineKeyboardButton(f"Out of Service - {issue}", callback_data=f"Out of Service - {issue}")] for issue in ISSUES_AND_SOLUTIONS.keys()]
            await query.edit_message_text(
                "⚠️ *Out of Service selected.* Please select the specific issue causing it:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            return DESC_TCC
        
        context.user_data['desc_tcc'] = selected_desc
        msg_func = query.edit_message_text
    else:
        context.user_data['desc_tcc'] = update.message.text
        msg_func = update.message.reply_text

    keyboard = [[InlineKeyboardButton("Skip ⏩", callback_data="SKIP")]]
    await msg_func(
        "Enter *Time closed* (e.g., 8:49PM) or press Skip:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return TIME_CLOSED

async def time_closed_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        raw_val = "" if query.data == "SKIP" else query.data
        context.user_data['time_closed'] = format_time_uppercase(raw_val)
        msg_func = query.edit_message_text
    else:
        raw_val = update.message.text if update.message.text != '/skip' else ""
        context.user_data['time_closed'] = format_time_uppercase(raw_val)
        msg_func = update.message.reply_text

    desc_tcc = context.user_data.get('desc_tcc', '')
    suggested_sol = None
    
    for issue, solution in ISSUES_AND_SOLUTIONS.items():
        if issue in desc_tcc:
            suggested_sol = solution
            break

    keyboard = []
    if suggested_sol:
        keyboard.append([InlineKeyboardButton(f"Suggested: {suggested_sol}", callback_data=suggested_sol)])
    
    for sol in ISSUES_AND_SOLUTIONS.values():
        if sol != suggested_sol:
            keyboard.append([InlineKeyboardButton(sol, callback_data=sol)])
    
    keyboard.append([InlineKeyboardButton("Skip ⏩", callback_data="SKIP")])

    await msg_func(
        f"📌 *TCC Report Issue:* `{desc_tcc}`\n\n"
        f"Select or type *Solution*:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SOLUTION

async def solution_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['solution'] = "" if query.data == "SKIP" else query.data
        msg_func = query.edit_message_text
    else:
        context.user_data['solution'] = update.message.text if update.message.text != '/skip' else ""
        msg_func = update.message.reply_text

    keyboard = [[InlineKeyboardButton("Skip ⏩", callback_data="SKIP")]]
    await msg_func(
        "Enter *Associated ticket* or press Skip:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return ASSOCIATED_TICKET

async def associated_ticket_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['associated_ticket'] = "" if query.data == "SKIP" else query.data
        msg_func = query.edit_message_text
    else:
        context.user_data['associated_ticket'] = update.message.text if update.message.text != '/skip' else ""
        msg_func = update.message.reply_text

    keyboard = [[InlineKeyboardButton("Skip ⏩", callback_data="SKIP")]]
    await msg_func(
        "Enter *Remarks* or press Skip:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return REMARKS

async def remarks_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        context.user_data['remarks'] = "" if query.data == "SKIP" else query.data
    else:
        context.user_data['remarks'] = update.message.text if update.message.text != '/skip' else ""

    return await send_final_report(update, context)

async def send_final_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    today_date = datetime.now().strftime("%d/%m/%Y")

    incident_record = {
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
    }
    daily_incidents.append(incident_record)

    # المخرج النهائي بالتنسيق الجديد (*العنوان* فقط بدون النقطتين وبدون النص المُدخل)
    output = (
        f"*Incident No*: {data.get('incident_no', '')}\n"
        f"*Incident priority*: {data.get('priority', '')}\n"
        f"*Services / System*: {data.get('services', '')}\n"
        f"*Location*: {data.get('location', '')}\n"
        f"*Incident Description Reported*: {data.get('desc_reported', '')}\n"
        f"*Incident Received Time*: {data.get('received_time', '')}\n\n"
        f"*R/C*: {data.get('rc', '')}\n"
        f"*Status*: {data.get('status', '')}\n"
        f"*Incident Description TCC report*: {data.get('desc_tcc', '')}\n"
        f"*Time closed*: {data.get('time_closed', '')}\n"
        f"*Solution*: {data.get('solution', '')}\n"
        f"*Associated ticket*: {data.get('associated_ticket', '')}\n"
        f"*Remarks*: {data.get('remarks', '')}"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(output, parse_mode='Markdown')
    else:
        await update.message.reply_text(output, parse_mode='Markdown')
        
    return ConversationHandler.END

# -------------------------------------------------------------
# 4. Direct Tab Export Generator (/report)
# -------------------------------------------------------------
async def export_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not daily_incidents:
        await update.message.reply_text("⚠️ No incidents recorded today yet.")
        return

    headers = [
        "Area",
        "Gate",
        "Ticket number",
        "Open Time",
        "Open Date",
        "Issue",
        "Resolution",
        "Close time",
        "Close Date",
        "Status",
        "Comments"
    ]

    lines = []
    for item in daily_incidents:
        row_fields = [str(item.get(h, "")) for h in headers]
        lines.append("\t".join(row_fields))

    tab_output = "\n".join(lines)

    await update.message.reply_text(
        "📊 **Daily Report Data**\n\n"
        "انسخ النص الموجود داخل المربع الرمادي أدناه، ثم الصقه مباشرة في خلية A372 في إكسل:\n\n"
        f"`{tab_output}`",
        parse_mode='Markdown'
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "ضع_التوكن_الخاص_بك_هنا")

    application = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            INCIDENT_NO: [MessageHandler(filters.TEXT & ~filters.COMMAND, incident_no_chosen)],
            PRIORITY: [CallbackQueryHandler(priority_chosen)],
            LOCATION: [CallbackQueryHandler(location_chosen)],
            SERVICES_SYSTEM: [
                CallbackQueryHandler(services_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, services_chosen)
            ],
            DESC_REPORTED: [
                CallbackQueryHandler(desc_reported_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_reported_chosen)
            ],
            RECEIVED_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, received_time_chosen)],
            RC: [
                CallbackQueryHandler(rc_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rc_chosen)
            ],
            STATUS: [CallbackQueryHandler(status_chosen)],
            DESC_TCC: [
                CallbackQueryHandler(desc_tcc_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_tcc_chosen)
            ],
            TIME_CLOSED: [
                CallbackQueryHandler(time_closed_chosen),
                CommandHandler('skip', time_closed_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, time_closed_chosen)
            ],
            SOLUTION: [
                CallbackQueryHandler(solution_chosen),
                CommandHandler('skip', solution_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, solution_chosen)
            ],
            ASSOCIATED_TICKET: [
                CallbackQueryHandler(associated_ticket_chosen),
                CommandHandler('skip', associated_ticket_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, associated_ticket_chosen)
            ],
            REMARKS: [
                CallbackQueryHandler(remarks_chosen),
                CommandHandler('skip', remarks_chosen),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remarks_chosen)
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('report', export_report))

    print("Bot is running...")
    application.run_polling()

if __name__ == '__main__':
    main()
