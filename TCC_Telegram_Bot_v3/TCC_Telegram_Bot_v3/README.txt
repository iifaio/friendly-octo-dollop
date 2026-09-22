TCC Telegram Bot v2

NEW:
- Interactive buttons instead of pipe-separated input.
- Fault list with buttons.
- Time selection buttons + exact manual time.
- Departure/Arrival selection.
- Dynamic gate selection: D1-D38 and A1-A26.
- Gate 2 is NOT hard-coded; D2 and A2 are selectable separately.
- Final TCC message is English.
- Services / System is the gate number, e.g. 2.
- Location contains only "Departure" or "Arrival".
- Avoids APScheduler by disabling JobQueue, fixing the Python 3.13 issue shown in the terminal.

Setup:
1. Put your NEW BotFather token in .env:
   BOT_TOKEN=YOUR_TOKEN
2. Install:
   py -m pip install -r requirements.txt
3. Run:
   py bot.py

Use:
/incident
