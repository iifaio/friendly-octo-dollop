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
        # استخدام الفاصل Tab (\t) المباشر
        lines.append("\t".join(row_fields))

    tab_output = "\n".join(lines)

    await update.message.reply_text(
        "📊 **Daily Report Data**\n\n"
        "انسخ النص الموجود داخل المربع الرمادي أدناه، ثم الصقه في الخلية A372:\n\n"
        f"`{tab_output}`",
        parse_mode='Markdown'
    )
