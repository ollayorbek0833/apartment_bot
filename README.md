ApartmentMate 🏠🤖  
Telegram Apartment Duty Management Bot

ApartmentMate is a production-ready Telegram bot designed to manage shared apartment duties in a fair, transparent, and deterministic way.  
It helps roommates avoid conflicts, forgotten tasks, and unfair workloads — all inside a Telegram group.

Bot username on Telegram: **@apartment\_mate\_bot**

This project focuses on real-world backend logic, long-running service design, and clean state management, rather than demo-level features.

* * *

💡 The Problem

In shared apartments:

-   Tasks are often forgotten ❌
    
-   The same people end up doing the work 😕
    
-   There is no clear or fair responsibility system 📉
    

ApartmentMate solves this by automating duty management with strict, predictable rules.

* * *

✨ Core Features

✅ Multiple duties (cooking, bathroom, rooms, etc.)  
✅ Each duty has its own team  
✅ Fixed rotation order (never breaks)  
✅ Skip-credit system for volunteering 🎫  
✅ One-command interaction per task  
✅ Anti-abuse cooldown per task ⏳  
✅ Admin-controlled configuration  
✅ Read-only simulations and inspections  
✅ Automatic history cleanup (rolling 30 days)  
✅ Cloud deployment (AWS EC2)

* * *

⚙️ How It Works (Logic Overview)

Each duty has:

-   🔁 A fixed rotation queue
    
-   🎫 A skip-credit balance per user
    

When a user interacts with a task:

-   If it is their turn, the task is completed ✅
    
-   If it is not their turn, they volunteer and earn a skip credit 🎫
    
-   Repeating the same task action within 2 hours is ignored ⏳
    

When determining responsibility:

-   Users with skip credits are skipped silently
    
-   Skip credits are consumed fairly
    
-   Rotation order is never destroyed
    

The system is fully deterministic — no randomness, no manual intervention.

* * *

📊 Activity Tracking & Transparency

ApartmentMate keeps an audit-friendly activity log:

-   Task completions
    
-   Volunteering actions
    

History is stored for 30 days on a rolling basis and can be exported by admins as an Excel-compatible CSV file for transparency and analysis.

* * *

🧰 Technology Stack

🐍 Python  
🤖 python-telegram-bot  
🗄 SQLite  
⏱ APScheduler  
🐧 Linux (Ubuntu)  
☁️ AWS EC2 (12-month Free Tier)  
⚙️ systemd

* * *

🚀 Deployment

ApartmentMate runs 24/7 on an AWS EC2 instance using the AWS Free Tier.  
It is managed as a systemd service and automatically restarts on crashes or reboots, ensuring continuous availability.

Configuration lives in two places. `bot/config.py` is gitignored and must define `BOT_TOKEN`
and `OWNER_TELEGRAM_ID`. Everything else is an environment variable:

| variable | default | why you would set it |
|---|---|---|
| `BOT_DB_PATH` | `bot.db` next to the working directory | Pin the database to an absolute path. Started from the wrong directory the bot creates a new empty database instead of finding the real one. |
| `BOT_TIMEZONE` | `Asia/Tashkent` | Timezone the daily announcement fires in and history is displayed in. The server clock is UTC; this is not. |
| `ANNOUNCE_HOUR` | `9` | Hour of the daily announcement, in `BOT_TIMEZONE`. |

* * *

🧪 Tests

    cd bot
    python3 -m tests.test_rotation
    python3 -m tests.test_wiring

No network and no bot token required. `test_rotation` covers rotation order, skip credits,
removal and reactivation, undo, the 30-day sweep and the cursor migration. `test_wiring`
dispatches real updates through python-telegram-bot to cover handler ordering, duty-name
validation and the scheduler's timezone.

* * *

🎯 Why This Project Matters

This project demonstrates:

-   Real backend problem solving 🧠
    
-   Deterministic state management 🔁
    
-   Clean separation of logic and infrastructure 🧩
    
-   Long-running service design ⏳
    
-   Cloud deployment experience ☁️
    

ApartmentMate is not a toy bot — it is built for daily, real-world use.

* * *

🔗 GitHub Repository

[https://github.com/ollayorbek0833/apartment\_bot](https://github.com/ollayorbek0833/apartment_bot)

* * *

👨‍💻 Author

Ollayorbek Masharipov  
Software Engineering Student  
Flutter & Backend Developer
