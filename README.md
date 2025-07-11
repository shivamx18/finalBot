# 🤖 Codeforces Companion Discord Bot

A powerful, feature-rich Discord bot tailored for **competitive programmers**, built to help users grow, compete, and collaborate — directly within your server.

![Banner](https://codeforces.org/s/12345/banner.png)

---

## ✨ Features Overview

| Category             | Commands / Features                             | Description                                                           |
|----------------------|--------------------------------------------------|-----------------------------------------------------------------------|
| ✅ Verification       | `/verify`                                        | Verifies users with their Codeforces handle and assigns rank roles   |
| ⚔️ Duels              | `/duel`, `/duelleaderboard`, `/myduelpoints`    | Challenge users to 1v1 duels with live updates & duel tracking       |
| 📊 Compare            | `/comparecf`, `/comparediscord`, `/comparemulti`| Compare user rating graphs and contest history                       |
| 📅 Reminders          | `/setreminderchannel`, `/disablecontestsite`    | Contest reminders for CF, CC, LC — auto-sent 5hrs before contests    |
| 🧩 POTD               | `/setpotd1week`, `/viewpotd`, `/editpotd`       | Set and auto-send Problem of the Day (Level 1 & 2) with role mention |
| 📈 Stats & Tracking   | `/cfheatmap`, `/cfaccuracy`, `/progresscf`      | View accuracy, streaks, daily activity, and rating progress          |
| 🎯 Recommendations    | `/recommendcf`, `/trainingplan`                 | Personalized practice suggestions based on skill level & preferences |
| 🧠 Gamification       | `/solvehunt`                                     | Weekly leaderboard challenge — solve first, earn “Hunt Champion”     |
| 🫶 Community Tools    | `/thank`, `/suggestion`, `/setmodchannel`       | Suggestion box & karma-based recognition                             |

---

## 🛠 Setup Instructions

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/codeforces-discord-bot.git
cd codeforces-discord-bot
2. Install Requirements
bash
Copy
Edit
pip install -r requirements.txt
3. Configure Environment
Create a .env file and fill in your credentials:

env
Copy
Edit
DISCORD_TOKEN=your_discord_bot_token
MONGO_URI=your_mongodb_uri
🧩 MongoDB Structure
The bot uses MongoDB to store:

User verifications and duel history

POTD problems for each guild

Reminder preferences per server

SolveHunt tracking and roles

✅ No data leaks — only relevant guild data is stored!

🔔 Scheduled Jobs
Task	Schedule	Function
Contest Reminder	5 hrs before start	Sends contest alerts to configured reminder channels
POTD Posting	Daily at 00:00 IST	Posts problems for the day to respective channels
SolveHunt Weekly	Monday 00:05 IST	Resets role, posts weekly challenge
POTD Admin Reminder	Sunday 20:00 IST	DM admins to update next week’s POTD

📸 Sample Screens
🔐 Verification

📈 Compare Ratings

🎯 Duel Result

🔥 Heatmap

🙋 Credits & Contributions
Made with ❤️ by @YourName

Pull requests, issues, and ideas are welcome. If you’d like to contribute:

bash
Copy
Edit
git checkout -b your-feature
📜 License
This project is licensed under the MIT License.
Feel free to use it for personal or educational projects!

yaml
Copy
Edit

---

Would you like me to generate this as a downloadable `README.md` file for you?
