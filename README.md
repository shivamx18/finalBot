# Codeforces Discord Bot

A feature-rich Discord bot for competitive programming communities built with `discord.py`, MongoDB, and the Codeforces public API.

---

## Project Structure

```
cf_bot/
├── main.py                  # Entry point — loads all cogs and starts the bot
│
├── config/
│   ├── settings.py          # Environment variables, constants, rank data
│   └── database.py          # MongoDB client + shared collection handles
│
├── utils/
│   ├── cf_api.py            # All Codeforces API calls (async)
│   ├── charts.py            # Matplotlib/Seaborn graph generators
│   ├── discord_helpers.py   # Shared Discord utilities (role assignment, checks)
│   └── scheduler.py         # APScheduler wrapper + task-loop launcher
│
├── cogs/
│   ├── admin.py             # Guild setup commands (admin-only)
│   ├── verify.py            # CF handle verification & user management
│   ├── duel.py              # 1v1 CF duel system
│   ├── stats.py             # CF stats, graphs, heatmaps, recommendations
│   ├── contests.py          # Contest reminders & /nextround
│   └── community.py         # /thank and /suggestions
│
├── .env.example             # Environment variable template
└── requirements.txt
```

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd cf_bot
pip install -r requirements.txt
```

### 2. Set up environment variables

```bash
cp .env.example .env
# Edit .env and fill in TOKEN and MONGO_URI
```

### 3. Run the bot

```bash
python main.py
```

---

## Features

### Admin Setup
| Command | Description |
|---|---|
| `/setcommandchannel` | Restrict bot commands to a Discord category |
| `/setcfcelebrationchannel` | Set the rank-up announcement channel |
| `/setduelchannel` | Set the category for duels |
| `/setreminderchannel` | Configure contest reminders (channel + role + platforms) |
| `/setmodchannel` | Set the mod/feedback channel |
| `/enablereminder` | Re-enable reminders for cf / cc / lc |
| `/disablereminder` | Disable reminders for cf / cc / lc |

### Verification
| Command | Description |
|---|---|
| `/verify <cfid>` | Link your Codeforces handle via first-name code verification |
| `/unverify <user>` | Admin: remove a user's verification |
| `/verified` | List all verified users in the server |
| `/cfid <user>` | Look up a Discord user's CF handle |
| `/discordid <cfid>` | Look up the Discord user linked to a CF handle |

### Duels
| Command | Description |
|---|---|
| `/duel <user> <min> <max>` | Challenge someone to a 1v1 CF duel |
| `/duelleaderboard` | Top 10 duelists in the server |
| `/myduelpoints` | Your current duel points |
| `/myduelhistory` | Your duel point progression graph |
| `/resetduel <user>` | Admin: reset a user's duel stats |
| `/resetduelall` | Admin: reset all duel stats in the server |
| `/clearduelleaderboard` | Admin: wipe all duel fields |

### Stats & Graphs
| Command | Description |
|---|---|
| `/statscf <handle>` | CF profile + rating history graph |
| `/comparecf <h1> <h2>` | Compare two CF handles |
| `/comparediscord <u1> <u2>` | Compare two verified Discord users |
| `/comparemulti <handles>` | Compare 2–5 handles |
| `/cfheatmap` | Your GitHub-style AC heatmap (365 days) |
| `/trainingplan` | 5 problems in a rating/tag range |
| `/recommendcf` | 5 problems recommended for your current rating |

### Contests
| Command | Description |
|---|---|
| `/nextround` | Next 5 upcoming contests (CF, CC, LC) |

> Automated reminders are sent every 30 minutes for contests starting within 24 hours.

### Community
| Command | Description |
|---|---|
| `/thank <user> <reason>` | Publicly thank a community member |
| `/suggestions <message>` | Send feedback to the mod team |

---

## Adding a New Feature Module

1. Create `cogs/your_feature.py` with a `Cog` class and a `setup(bot)` function.
2. Add `"cogs.your_feature"` to the `COGS` list in `main.py`.
3. Add new constants to `config/settings.py`.
4. Add new DB collections to `config/database.py`.
5. Add new API helpers to `utils/cf_api.py`.

---

## MongoDB Collections

| Collection | Purpose |
|---|---|
| `users` | Verified users: discord_id, cfid, rating, rank, duel data |
| `guilds` | Per-guild config: channels, roles, reminder settings |
| `hunts` | Problem hunt entries |
| `hunt_claims` | Hunt claim records |
