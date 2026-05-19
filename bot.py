import telebot
from telebot import util  
import random
import time
import threading
import sqlite3
import os
import json
from datetime import date

# ⚠️ 設定你的 Bot 憑證與用戶名
TOKEN = "8447034432:AAFOW7PmFbBaY3p70dKAchGCUqKlH_ii9XI"
BOT_USERNAME = "@Gapjaibot"

# 🚀 啟用多線程 ThreadPool
bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=4)

# 🔒 定義每日簽到安全鎖 (防並發連擊)
daily_lock = threading.Lock()

# 🐿️ 基礎 NPC 固定鼠隻名單與其專屬圖標
BASE_NPC_HORSES = [
    ("奧雲狗狗", "⚡"), ("黑旋風", "🌪"), ("戰槌巨人", "⭐"), ("火麒麟", "🔥"), 
    ("疾風", "💨"), ("黃金戰鼠", "🏅"), ("海嘯", "🌊"), ("傲空", "🦅")
]

# 🔢 名次對應的數字 Emoji 對照表
RANK_EMOJIS = {
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
}

# 🐾 可供隨機抽取的動物 Emoji 清單
RANDOM_ANIMAL_EMOJIS = [
    "🦁", "🐼", "🦊", "🐭", "🐨", "🐯", "🐸", "🐷", "🐻", "🐰", 
    "🐵", "🐔", "🐧", "🐦", "🦆", "🦅", "🦉", "🦇", "🐺", "🐗"
]

# 📋 清單 A：下注排位表顯示的外觀狀態 (共 20 句)
BETTING_SURFACE_STATUSES = [
    "鼠神加持🤩高光時刻", "外星物種👽高深莫測", "科技外掛🤖液態金屬", "剛吃興奮劑💊眼神清澈", 
    "昨晚拜神🙏獲得神秘力量", "祖先托夢👑這局穩贏", "賽道车神🏎️自帶BGM", "氣勢如虹😤單眼單挑", 
    "氪金玩家💰全身發光", "不可一世😎王者風範",
    "天生扁平足🦶跑動困難", "沉迷股票📉痛失家產心慌慌", "剛剛小兒麻痺症發作🤒", "霉運當頭🌀烏雲蓋頂", 
    "體重超標🐷走路都喘氣", "出局邊緣🥀毫無鬥志", "四肢無力🥵缺乏維他命", "中暑邊緣☀️頭暈身熱", 
    "靈魂出竅👻呆若木雞", "忘記帶大腦🧠全憑本能"
]

# 🎬 清單 B：開局5秒狀態通報
RACE_START_STATUSES = [
    "朋友最多轉圈哈姆共你🐹",             
    "趕住返屋企瀨屎💩",                   
    "昨晚拜過黃大仙🙏獲得神祕力量加持",   
    "尋晚飲咗過期維他奶🥛個肚好滾",       
    "出門口踩到舊大狗屎💩霉運當頭", 
    "尋晚拉咗十二次斯🚽對腳發軟",
    "倒瀉咗杯凍檸茶走甜熱辣辣🍹", 
    "以為自己係比卡超⚡自帶十萬伏特", 
    "突然叮噹大長篇上身🎒要拯救地球",
    "阿嬤覺得佢餓👵嫌餵到變咗個波", 
    "智商突然下線🧠全憑生物本能前進", 
    "食咗誠實豆沙包💊個人好清醒",
    "氪金玩家💰全身閃爍住人民幣嘅光芒", 
    "眼神充滿殺氣🔪覺得自己係黎明", 
    "自帶背景音樂BGM🎵氣勢如虹",
    "跛咗隻腳🧑嫌推輪椅代步跑", 
    "成晚通宵打機🎮條黑眼圈去到下巴", 
    "飲咗兩啖假酒🥴左右不分亂打打",
    "失戀萬念毀滅💔打算跑完去跳海", 
    "高山反應🏔️呼吸困難行得好辛苦"
]

# 💾 資料庫持久化路徑設定
DB_FILE = '/data/race.db'
HORSE_PRICE = 3000  

# ================== 💾 資料庫管理 ==================
def init_db():
    try: os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    except: pass
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            chips INTEGER DEFAULT 1000,
            last_daily TEXT,
            has_horse INTEGER DEFAULT 0,
            horse_name TEXT DEFAULT NULL,
            horse_first INTEGER DEFAULT 0,
            horse_second INTEGER DEFAULT 0,
            horse_third INTEGER DEFAULT 0,
            horse_losses INTEGER DEFAULT 0,
            last_luck_date TEXT DEFAULT NULL
        );
        ''')
        
        c.execute('''
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        ''')
        
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if "horse_first" not in columns: c.execute("ALTER TABLE users ADD COLUMN horse_first INTEGER DEFAULT 0")
        if "horse_second" not in columns: c.execute("ALTER TABLE users ADD COLUMN horse_second INTEGER DEFAULT 0")
        if "horse_third" not in columns: c.execute("ALTER TABLE users ADD COLUMN horse_third INTEGER DEFAULT 0")
        if "horse_losses" not in columns: c.execute("ALTER TABLE users ADD COLUMN horse_losses INTEGER DEFAULT 0")
        if "last_luck_date" not in columns: c.execute("ALTER TABLE users ADD COLUMN last_luck_date TEXT DEFAULT NULL")
        conn.commit()

def get_chips(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT chips FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if not row:
            c.execute("INSERT INTO users (user_id, chips) VALUES (?, 1000)", (user_id,))
            conn.commit()
            return 1000
        return row[0]

def update_chips(user_id, amount):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET chips = chips + ? WHERE user_id=?", (amount, user_id))
        conn.commit()

def get_user_horse(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT has_horse, horse_name, horse_first, horse_second, horse_third, horse_losses FROM users WHERE user_id=?", (user_id,))
        row = c.fetchone()
        if row: 
            return {"has_horse": row[0], "horse_name": row[1], "first": row[2], "second": row[3], "third": row[4], "losses": row[5]}
        return {"has_horse": 0, "horse_name": None, "first": 0, "second": 0, "third": 0, "losses": 0}

def get_owner_by_horse_name(horse_name):
    clean_name = horse_name
    if "." in clean_name: clean_name = clean_name.split(".", 1)[1]
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE horse_name=?", (clean_name,))
        row = c.fetchone()
        return row[0] if row else None

def get_all_registered_horses():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, horse_name FROM users WHERE has_horse=1 AND horse_name IS NOT NULL")
        return c.fetchall()

def get_all_users_for_luck():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username, has_horse, horse_name, last_luck_date FROM users")
        return c.fetchall()

def update_luck_date(user_id, today_str):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET last_luck_date=? WHERE user_id=?", (today_str, user_id))
        conn.commit()

def sync_username(user_id, username):
    if not username: return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET username=? WHERE user_id=?", (username.lower(), user_id))
        conn.commit()

def record_detailed_result(user_id, rank_type):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        if rank_type == 1: c.execute("UPDATE users SET horse_first = horse_first + 1 WHERE user_id=?", (user_id,))
        elif rank_type == 2: c.execute("UPDATE users SET horse_second = horse_second + 1 WHERE user_id=?", (user_id,))
        elif rank_type == 3: c.execute("UPDATE users SET horse_third = horse_third + 1 WHERE user_id=?", (user_id,))
        else: c.execute("UPDATE users SET horse_losses = horse_losses + 1 WHERE user_id=?", (user_id,))
        conn.commit()

# ================== 💾 保底機制核心管理 ==================
def get_system_race_count():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM system_config WHERE key='total_races'")
        row = c.fetchone()
        if row: return int(row[0])
        c.execute("INSERT INTO system_config (key, value) VALUES ('total_races', '0')")
        conn.commit()
        return 0

def increment_system_race_count():
    current = get_system_race_count()
    new_count = current + 1
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE system_config SET value=? WHERE key='total_races'", (str(new_count),))
        conn.commit()
    return new_count

def get_guarantee_plan():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM system_config WHERE key='guarantee_plan'")
        row = c.fetchone()
        if row: return json.loads(row[0])
        
        g_races = random.sample(range(1, 11), 2)
        plan = {
            str(g_races[0]): random.choice([1, 2]),
            str(g_races[1]): random.choice([1, 2])
        }
        c.execute("INSERT INTO system_config (key, value) VALUES ('guarantee_plan', ?)", (json.dumps(plan),))
        conn.commit()
        return plan

def refresh_guarantee_plan():
    g_races = random.sample(range(1, 11), 2)
    plan = {
        str(g_races[0]): random.choice([1, 2]),
        str(g_races[1]): random.choice([1, 2])
    }
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE system_config SET value=? WHERE key='guarantee_plan'", (json.dumps(plan),))
        conn.commit()
    return plan

init_db()

# ================== 賽事與氣運全域變數 ==================
current_race = None    
race_id = None
race_bets = {}   
race_odds = {}  
current_horses = []   
horse_statuses = {}  
scheduled_disasters = {}  
active_horse_luck = {}

user_bet_count = {}     
user_refund_count = {}  
user_actual_deduct = {} 

# ================== 💸 轉帳系統 ==================
@bot.message_handler(commands=['pay'])
def pay_chips(message):
    try:
        from_user_id = message.from_user.id
        sync_username(from_user_id, message.from_user.username)
        to_user_id = None
        to_username = "神祕玩家"
        pay_amount = 0

        text_clean = message.text
        if f"{BOT_USERNAME}" in text_clean: text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
        elif f"@run1234567bot" in text_clean.lower(): text_clean = text_clean.lower().replace("@run1234567bot", "")

        cmd = text_clean.split()
        if len(cmd) < 2:
            bot.reply_to(message, "❌ **格式錯誤**\n👉 回覆他人訊息轉帳：`/pay 金額`\n👉 直接標記名字轉帳：`/pay @玩家標記 金額`", parse_mode='Markdown')
            return

        if len(cmd) >= 3 and cmd[1].startswith('@'):
            target_username = cmd[1].replace('@', '').strip().lower()
            raw_amount = cmd[2].strip()
            with sqlite3.connect(DB_FILE) as conn:
                c = conn.cursor()
                c.execute("SELECT user_id, username FROM users WHERE username=?", (target_username,))
                row = c.fetchone()
                if row:
                    to_user_id = row[0]
                    to_username = row[1] if row[1] else target_username
                else:
                    bot.reply_to(message, f"❌ **轉帳失敗**：找不到玩家 `@{target_username}`。", parse_mode='Markdown')
                    return
        elif message.reply_to_message:
            if message.reply_to_message.from_user:
                to_user_id = message.reply_to_message.from_user.id
                to_username = message.reply_to_message.from_user.first_name
                sync_username(to_user_id, message.reply_to_message.from_user.username)
            else:
                bot.reply_to(message, "❌ **轉帳失敗**：無法讀取該訊息發送者隱私。", parse_mode='Markdown')
                return
            raw_amount = cmd[1].strip()
        else:
            bot.reply_to(message, "❌ **轉帳失敗！**", parse_mode='Markdown')
            return

        try:
            pay_amount = int(raw_amount)
            if pay_amount <= 0: return
        except ValueError: return

        if from_user_id == to_user_id: return
        from_user_chips = get_chips(from_user_id) 
        if from_user_chips < pay_amount: return

        get_chips(to_user_id) 
        update_chips(from_user_id, -pay_amount) 
        update_chips(to_user_id, pay_amount)   

        from_username = message.from_user.first_name if message.from_user.first_name else "神祕玩家"
        success_text = f"💸 **【金幣轉讓成功】** 💸\n🤝 轉出人：{from_username}\n🎁 接收人：{to_username}\n💰 轉讓金額：<b>{pay_amount:,}</b> 金幣"
        bot.send_message(message.chat.id, success_text, parse_mode='HTML')
    except: pass

# ================== 🎰 開局排位 + 🔮 氣運系統 ==================
@bot.message_handler(commands=['startrun'])
def startrun(message):
    global current_race, race_id, race_odds, user_bet_count, user_refund_count, user_actual_deduct, current_horses, horse_statuses, scheduled_disasters, active_horse_luck
    if current_race:
        bot.reply_to(message, "⚠️ 已有賽事進行中！")
        return

    current_race = "betting"  
    
    total_races = increment_system_race_count()
    cycle_index = total_races % 10
    if cycle_index == 0: cycle_index = 10
    
    race_id = f"R{int(time.time())}"
    race_bets[race_id] = {}
    race_odds = {}
    horse_statuses = {}
    scheduled_disasters = {} 
    active_horse_luck = {}
    user_bet_count = {}
    user_refund_count = {}
    user_actual_deduct = {}
    
    plan = get_guarantee_plan()
    is_guarantee_round = str(cycle_index) in plan
    guarantee_count = plan.get(str(cycle_index), 0) if is_guarantee_round else 0

    sync_username(message.from_user.id, message.from_user.username)
    all_registered = get_all_registered_horses()
    final_8_horses = []  
    
    if len(all_registered) == 0:
        for npc_name, npc_icon in BASE_NPC_HORSES:
            final_8_horses.append((None, npc_name, npc_icon))
    else:
        random.shuffle(all_registered)
        selected_players = all_registered[:8]
        for uid, h_name in selected_players:
            final_8_horses.append((uid, h_name, "👑"))
        if len(final_8_horses) < 8:
            shortage = 8 - len(final_8_horses)
            available_npcs = BASE_NPC_HORSES.copy()
            random.shuffle(available_npcs)
            for i in range(shortage):
                npc_name, npc_icon = available_npcs[i]
                final_8_horses.append((None, npc_name, npc_icon))

    random.shuffle(final_8_horses)
    chosen_horses_pool = []
    for idx, (uid, h_name, icon) in enumerate(final_8_horses):
        lane_num = idx + 1
        chosen_horses_pool.append(f"{icon}{lane_num}.{h_name}")
    current_horses = chosen_horses_pool

    luck_announcements = []
    all_users = get_all_users_for_luck()
    today_str = date.today().isoformat()
    
    for u_id, u_name, has_h, h_name, last_luck_date in all_users:
        if last_luck_date == today_str:
            continue

        roll = random.random()
        if roll < 0.005:  
            update_luck_date(u_id, today_str) 
            try: nickname = bot.get_chat_member(message.chat.id, u_id).user.first_name
            except: nickname = f"@{u_name}" if u_name else f"玩家({u_id})"
            
            matching_horse = next((h for h in current_horses if h_name and h_name in h), None)
            if matching_horse and random.random() < 0.50:
                active_horse_luck[matching_horse] = "good"
                luck_announcements.append(f"🍀 <b>【氣運爆發 • 今日好運】</b>\n鼠主 <b>{nickname}</b> 獲得愛鼠之神眷顧！本局參賽愛鼠 <b>{matching_horse}</b> 獲得<b>【幸運值 +5% 跑速與暴走加成】</b>！🚀 (每日限一次)")
            else:
                update_chips(u_id, 3000)
                luck_announcements.append(f"🍀 <b>【氣運爆發 • 今日好運】</b>\n愛鼠之人 <b>{nickname}</b> 突發好運！獲得 <b>+3,000</b> 金幣已存入餘額！💰 (每日限一次)")

        elif roll >= 0.005 and roll < 0.010:  
            update_luck_date(u_id, today_str) 
            try: nickname = bot.get_chat_member(message.chat.id, u_id).user.first_name
            except: nickname = f"@{u_name}" if u_name else f"玩家({u_id})"
            
            matching_horse = next((h for h in current_horses if h_name and h_name in h), None)
            if matching_horse and random.random() < 0.50:
                active_horse_luck[matching_horse] = "bad"
                luck_announcements.append(f"💀 <b>【霉運當頭 • 今日歹運】</b>\n鼠主 <b>{nickname}</b> 驚逢黑仔期！本局參賽愛鼠 <b>{matching_horse}</b> 遭遇<b>【Debuff/死亡意外率 +5%】</b>！⚠️ (每日限一次)")
            else:
                update_chips(u_id, -3000)
                luck_announcements.append(f"💀 <b>【霉運當頭 • 今日歹運】</b>\n玩家 <b>{nickname}</b> 在街上遇到食環署執法！因隨地亂倒鼠糧被<b>罰款 $3,000</b>，已從餘額扣除！💸 (每日限一次)")

    if random.random() < 0.04:
        disaster_count = random.choice([1, 2])
        unlucky_horses = random.sample(current_horses, disaster_count)
        for uh in unlucky_horses:
            trigger_point = random.uniform(0.0, 99.0)
            reason = random.choice(["🐱【被貓吃掉❌】", "🪤【踩到鼠夾❌】"])
            scheduled_disasters[uh] = {"trigger_at": trigger_point, "reason": reason}

    for h in current_horses:
        if active_horse_luck.get(h) == "bad" and h not in scheduled_disasters:
            if random.random() < 0.05:
                trigger_point = random.uniform(5.0, 85.0)
                reason = random.choice(["🐱【黑仔遇到野貓吃掉❌】", "🪤【歹運踩中特大鼠夾❌】"])
                scheduled_disasters[h] = {"trigger_at": trigger_point, "reason": reason}

    available_statuses = BETTING_SURFACE_STATUSES.copy()
    random.shuffle(available_statuses)
    round_statuses = available_statuses[:7]
    if random.random() < 0.50: round_statuses.append(random.choice(round_statuses))  
    else: round_statuses.append(available_statuses[7]) 
    random.shuffle(round_statuses)  

    guaranteed_cold_horses = []
    detected_cold_horses = []
    for idx, h in enumerate(current_horses):
        surface_txt = round_statuses[idx]
        is_cold = any(keyword in surface_txt for keyword in ["小兒麻痺", "出局邊緣", "沉迷股票", "體重超標"])
        if is_cold:
            detected_cold_horses.append(h)

    if is_guarantee_round and detected_cold_horses:
        actual_guarantee_count = min(guarantee_count, len(detected_cold_horses))
        guaranteed_cold_horses = random.sample(detected_cold_horses, actual_guarantee_count)

    text = f"賽鼠 **【賽鼠會 - 第 {total_races} 場】** 🐿️\n🏆 本場盃賽：【鼠王爭霸戰】\n"
    if is_guarantee_round:
        text += f"✨ _本場為本週期第 {cycle_index} 場暗號保底局_\n\n"
    else:
        text += f"📊 週期進度：第 {cycle_index}/10 場\n\n"
    
    # 🎲 事前抽出 8 個不重複嘅隨機動物 Emoji 供本場排位表使用
    round_animal_emojis = random.sample(RANDOM_ANIMAL_EMOJIS, 8)

    for idx, h in enumerate(current_horses):
        lane_num = idx + 1
        surface_txt = round_statuses[idx] 

        is_hot = any(keyword in surface_txt for keyword in ["鼠神", "外星", "科技", "拜神", "賽道", "氪金", "不可一世"])
        is_cold = h in detected_cold_horses
        has_surface_buff = (not is_cold) and any(keyword in surface_txt for keyword in ["鼠神加持🤩高光時刻", "外星物種👽高深莫測"])

        is_cold_debuffed = False
        if is_cold:
            if h in guaranteed_cold_horses:
                is_cold_debuffed = False  
            else:
                is_cold_debuffed = (random.random() < 0.05)  

        horse_statuses[h] = {
            "betting_text": surface_txt,      
            "start_text": "",                 
            "target_time": 50.0,  
            "dead_reason": None,
            "freeze_steps": 0,       
            "freeze_reason": "",
            "is_buff_carrier": has_surface_buff,  
            "is_debuff_carrier": is_cold_debuffed,            
            "buff_active": False,
            "debuff_active": False,
            "is_guaranteed": (h in guaranteed_cold_horses) 
        }

        if is_cold: 
            win_odds = round(random.uniform(13.0, 20.0), 1)
            class_icon = "💀"
        elif is_hot: 
            win_odds = round(random.uniform(2.5, 3.6), 1)
            class_icon = "🔥"
        else: 
            win_odds = round(random.uniform(4.0, 8.5), 1)
            class_icon = "🎲"

        place_odds = round(win_odds * 0.4, 1)
        if place_odds < 1.1: place_odds = 1.1  
        race_odds[h] = win_odds  
        
        icon = h[0]
        name_part = h.split('.', 1)[1]
        
        luck_tag = " 🍀[好運加成]" if active_horse_luck.get(h) == "good" else " 💀[歹運纏身]" if active_horse_luck.get(h) == "bad" else ""
        if h in guaranteed_cold_horses:
            luck_tag += " ✨[暗影爆發]"

        # 🔧 核心修改：原本嘅 🎪 直接換成隨機動物 Emoji
        animal_emoji = round_animal_emojis[idx]
        text += f"{lane_num} {name_part}{icon}{luck_tag} {animal_emoji} {surface_txt}\n"
        text += f"    {class_icon} 獨贏: {win_odds}倍 | 位置: {place_odds}倍\n"

    text += "\n" + "—" * 20 + "\n"
    text += "💰 **【下注方式】** /win 號碼 金額 | /pla 號碼 金額 | /ww 號碼1 號碼2 金額\n"
    
    if luck_announcements:
        bot.send_message(message.chat.id, "🔮 <b>【每局天星氣運星象通報】</b> 🔮\n" + "‾"*25 + "\n" + "\n\n".join(luck_announcements), parse_mode='HTML')
        time.sleep(1)

    bot.reply_to(message, text, parse_mode='Markdown')
    
    if cycle_index == 10:
        refresh_guarantee_plan()

    threading.Timer(60, lambda: run_race(message.chat.id)).start()

# ================== 直播與戰績結算 ==================
def run_race(chat_id):
    global current_race, race_id, race_odds, race_bets, current_horses, horse_statuses, scheduled_disasters, active_horse_luck
    
    if current_race != "betting": return
    current_race = "running" 
    
    status_intro = f"📋 **賽前選手狀態通報** 📋\n" + "‾" * 25 + "\n"
    for h in current_horses:
        start_txt = random.choice(RACE_START_STATUSES)
        
        if horse_statuses[h]["is_debuff_carrier"]:
            start_txt = "❌ 突然舊患復發！全身發軟手震震"
            
        horse_statuses[h]["start_text"] = start_txt  
        
        luck_desc = ""
        if active_horse_luck.get(h) == "good": luck_desc = " 🍀(今日幸運加速)"
        elif active_horse_luck.get(h) == "bad": luck_desc = " 💀(今日意外率提升)"
        
        status_intro += f"{h} ➡️ **{start_txt}**{luck_desc}\n"

        if horse_statuses[h].get("is_guaranteed", False):
            base_time_range = (22.0, 26.0) 
        else:
            if start_txt in ["朋友最多轉圈哈姆共你🐹", "趕住返屋企瀨屎💩", "昨晚拜過黃大仙🙏獲得神祕力量加持"]:
                if random.random() < 0.60: base_time_range = (27.0, 35.0) 
                else: base_time_range = (40.0, 55.0) 
            elif horse_statuses[h]["is_debuff_carrier"]:
                base_time_range = (120.0, 180.0) 
            else:
                status_score = random.randint(1, 10)
                if status_score >= 9: base_time_range = (28.0, 38.0)  
                elif status_score >= 4: base_time_range = (42.0, 58.0)  
                else: base_time_range = (62.0, 80.0)
                
        final_target_time = random.uniform(*base_time_range)
        if active_horse_luck.get(h) == "good":
            final_target_time *= 0.95 
            
        horse_statuses[h]["target_time"] = final_target_time

    status_intro += "\n⏱ _狀態展示中，比賽將於 5 秒後正式鳴槍！_"
    
    race_msg = bot.send_message(chat_id, status_intro, parse_mode='Markdown')
    time.sleep(5)  
    
    TOTAL_DISTANCE = 100.0  
    DISPLAY_LENGTH = 15     
    
    speeds = {h: TOTAL_DISTANCE / horse_statuses[h]["target_time"] for h in current_horses}
    current_distance = {h: 0.0 for h in current_horses}
    
    finished_horses = []   
    dead_horses = []       
    
    start_time = time.time()
    last_refresh_time = start_time
    
    while (len(finished_horses) < 3) and (len(finished_horses) + len(dead_horses) < len(current_horses)):
        time.sleep(1.0)  
        now = time.time()
        current_second_reports = {}
        
        for h in current_horses:
            if horse_statuses[h]["dead_reason"] is not None:
                current_second_reports[h] = f"❌ {horse_statuses[h]['dead_reason']}"
                continue

            if current_distance[h] >= TOTAL_DISTANCE:
                r = finished_horses.index(h) + 1
                current_second_reports[h] = f"🏁 已衝線 (第 {r} 名)"
                continue

            if h in scheduled_disasters and current_distance[h] >= scheduled_disasters[h]["trigger_at"]:
                if horse_statuses[h].get("is_guaranteed", False):
                    pass
                else:
                    disaster_reason = scheduled_disasters[h]["reason"]
                    horse_statuses[h]["dead_reason"] = disaster_reason
                    dead_horses.append(h)
                    current_second_reports[h] = f"❌ {disaster_reason}"
                    continue
            
            if horse_statuses[h]["freeze_steps"] > 0:
                reason = horse_statuses[h]["freeze_reason"]
                sec_left = horse_statuses[h]["freeze_steps"]
                current_second_reports[h] = f"⚠️ {reason} (剩餘 {sec_left} 秒) 🕒"
                horse_statuses[h]["freeze_steps"] -= 1 
                continue 
            
            if random.random() < 0.005 and not horse_statuses[h].get("is_guaranteed", False):
                freeze_sec = random.randint(3, 5) 
                freeze_type = random.choice(["發呆停止步行 💤", "地上撿到芝士吃兩口 🧀"])
                horse_statuses[h]["freeze_steps"] = freeze_sec
                horse_statuses[h]["freeze_reason"] = freeze_type
                current_second_reports[h] = f"⚠️ {freeze_type} (剩餘 {freeze_sec} 秒) 🕒"
                horse_statuses[h]["freeze_steps"] -= 1 
                continue

            buff_check_chance = 0.055 if active_horse_luck.get(h) == "good" else 0.005
            if (horse_statuses[h]["is_buff_carrier"] or active_horse_luck.get(h) == "good") and not horse_statuses[h]["buff_active"]:
                if random.random() < buff_check_chance: horse_statuses[h]["buff_active"] = True

            if horse_statuses[h]["is_debuff_carrier"]:
                step_modifier = 0.1 
                action_text = "⚠️ 狀態大下滑！腳軟慢跑中... 🐢"
            elif horse_statuses[h].get("is_guaranteed", False):
                step_modifier = 1.3 
                action_text = "✨ 🚀 隱藏潛能突發暴走！全速大躍進！！"
            elif horse_statuses[h]["buff_active"]:
                step_modifier = 3.5  
                action_text = "✨ 🚀 隱藏潛能突發暴走！全速大躍進！！"
                horse_statuses[h]["buff_active"] = False 
            else:
                move_roll = random.randint(1, 10)
                if move_roll >= 9: step_modifier = 2.0; action_text = "⚡ 快步推進"
                elif move_roll >= 4: step_modifier = 1.0; action_text = "✨ 穩步向前"
                else: step_modifier = 0.5; action_text = "💤 慢步推進"
                
            current_distance[h] += (speeds[h] * 1.0) * step_modifier + random.uniform(-0.2, 0.2)
            if current_distance[h] < 0: current_distance[h] = 0
            
            if current_distance[h] >= TOTAL_DISTANCE:
                current_distance[h] = TOTAL_DISTANCE
                if h not in finished_horses: finished_horses.append(h)
                current_second_reports[h] = f"🏁 剛剛衝線了！(第 {finished_horses.index(h) + 1} 名)"
            else:
                current_second_reports[h] = action_text
                        
        if now - last_refresh_time >= 3.0 or (len(finished_horses) >= 3) or (len(finished_horses) + len(dead_horses) == len(current_horses)):
            last_refresh_time = now
            dynamic_text = f"🐿️ **現場直播** 🏁\n" + "‾" * 25 + "\n"
            
            for h in current_horses:
                if horse_statuses[h]["dead_reason"] is not None:
                    dynamic_text += f"{h} ➡️ {horse_statuses[h]['dead_reason']}\n\n"
                else:
                    progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
                    progress = min(max(progress, 0), DISPLAY_LENGTH)
                    track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + "🐿️" + "_" * progress
                    status = ""
                    if h in finished_horses:
                        r = finished_horses.index(h) + 1
                        status = " 🥇【冠軍】" if r==1 else " 🥈【亞軍】" if r==2 else " 🥉【季軍】"
                    dynamic_text += f"{h}{status}\n`{track_str}`\n\n"
            
            action_reports = []
            for h in current_horses:
                msg_status = current_second_reports.get(h, "未知")
                if horse_statuses[h]["dead_reason"] is not None: rank_str = "淘汰"
                elif h in finished_horses: rank_str = f"第 {finished_horses.index(h) + 1} 名"
                else:
                    higher_count = sum(1 for comp in current_horses if comp != h and horse_statuses[comp]["dead_reason"] is None and comp not in finished_horses and current_distance[comp] > current_distance[h])
                    current_rank = len(finished_horses) + 1 + higher_count
                    rank_str = f"第 {current_rank} 名"
                action_reports.append(f"🏃 [{rank_str}] {h} ➡️ `[{msg_status}]`")
            
            dynamic_text += "—" * 15 + "\n"
            dynamic_text += "📊 **【即時動態戰況提示】**\n" + "\n".join(action_reports)
            
            try: bot.edit_message_text(dynamic_text, chat_id, race_msg.message_id, parse_mode='Markdown')
            except: pass

    alive_remaining = [h for h in current_horses if h not in finished_horses and h not in dead_horses]
    alive_remaining.sort(key=lambda h: current_distance[h], reverse=True)
    all_ranks = finished_horses + alive_remaining + dead_horses
    
    final_text = f"🐿️ **直播結束（定格名次）** 🏁\n" + "‾" * 25 + "\n"
    for h in current_horses:
        if horse_statuses[h]["dead_reason"] is not None:
            final_text += f"{h} ➡️ {horse_statuses[h]['dead_reason']} (取消資格)\n\n"
        else:
            final_rank = all_ranks.index(h) + 1
            rank_emoji = RANK_EMOJIS.get(final_rank, "🐿️") 
            progress = int((current_distance[h] / TOTAL_DISTANCE) * DISPLAY_LENGTH)
            progress = min(max(progress, 0), DISPLAY_LENGTH)
            track_str = "🏁 " + "_" * (DISPLAY_LENGTH - progress) + rank_emoji + "_" * progress
            status = " 🥇【冠軍】" if final_rank==1 else " 🥈【亞軍】" if final_rank==2 else " 🥉【季軍】" if final_rank==3 else ""
            final_text += f"{h}{status}\n`{track_str}`\n\n"
    
    final_text += "—" * 15 + "\n🏁 比賽結束！正在計算最終名次與分紅..."
    try: bot.edit_message_text(final_text, chat_id, race_msg.message_id, parse_mode='Markdown')
    except: pass
                
    winner, second = all_ranks[0] if len(finished_horses) > 0 else None, all_ranks[1] if len(finished_horses) > 1 else None
    
    result = "🏆 **最終賽果名次結果** 🏆\n\n"
    for i, h in enumerate(all_ranks, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🏁"
        if horse_statuses[h]["dead_reason"] is not None:
            result += f"❌ 未完賽：{h} -> {horse_statuses[h]['dead_reason']} (全輸)\n"
        else:
            result += f"{medal} 第 {i} 名：{h} (獨贏 {race_odds[h]}x)\n"
    bot.send_message(chat_id, result, parse_mode='Markdown')
    
    if race_id in race_bets and len(finished_horses) > 0:
        payout_message = "🎉 **派彩結果** 🎉\n\n"
        has_winner = False
        for uid, bets in race_bets[race_id].items():
            win_amount = 0
            for b_type, horses, amt in bets:
                if b_type == "win" and winner and horses == winner: win_amount += int(amt * race_odds[winner])
                elif b_type == "pla" and horses in finished_horses[:3]: win_amount += int(amt * (race_odds[horses] * 0.4)) 
                elif b_type == "ww" and winner and second and isinstance(horses, list) and set(horses) == set([winner, second]):
                    win_amount += int(amt * (race_odds[winner] * race_odds[second]))
            if win_amount > 0:
                update_chips(uid, win_amount)
                try: p_name = bot.get_chat_member(chat_id, uid).user.first_name
                except: p_name = f"玩家({uid})"
                payout_message += f"✅ 玩家 <b>{p_name}</b> 贏得 <b>{win_amount:,}</b> 金幣\n"
                has_winner = True
        if has_winner: bot.send_message(chat_id, payout_message, parse_mode='HTML')
        else: bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")
    else:
        bot.send_message(chat_id, "壓注全空！本局沒有人中獎 💸")

    for h in current_horses:
        if "👑" in h: 
            owner_id = get_owner_by_horse_name(h)
            if owner_id:
                owner_id = int(owner_id)
                rank_idx = all_ranks.index(h)
                if horse_statuses[h]["dead_reason"] is None and rank_idx < 3:
                    record_detailed_result(owner_id, rank_type=(rank_idx + 1))
                else:
                    record_detailed_result(owner_id, rank_type=4)

    owner_text = "✨ <b>【本局鼠主專利分紅】</b> ✨\n"
    has_owner_bonus = False
    consolation_owners = [] 

    for rank_idx in range(min(3, len(finished_horses))):
        target_horse = finished_horses[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id:
                owner_id = int(owner_id)
                rank_num = rank_idx + 1
                try: owner_name = bot.get_chat_member(chat_id, owner_id).user.first_name
                except: owner_name = f"鼠主({owner_id})"
                
                if rank_num == 1: bonus_chips = random.randint(10000, 20000); t_title = "🥇 冠軍"
                elif rank_num == 2: bonus_chips = random.randint(6000, 7500); t_title = "🥈 亞軍"
                else: bonus_chips = random.randint(1000, 2000); t_title = "🥉 季軍"
                
                update_chips(owner_id, bonus_chips)
                owner_text += f"恭喜專屬鼠 <b>{target_horse}</b> 榮獲{t_title}！\n鼠主 <b>{owner_name}</b> 獲得分紅大獎 <b>+{bonus_chips:,}</b> 金幣 💰\n"
                has_owner_bonus = True

    for rank_idx in range(3, len(all_ranks)):
        target_horse = all_ranks[rank_idx]
        if "👑" in target_horse:
            owner_id = get_owner_by_horse_name(target_horse)
            if owner_id: consolation_owners.append(int(owner_id))

    if consolation_owners:
        consolation_mentions = []
        for c_owner in consolation_owners:
            lucky_comfort_bonus = random.randint(300, 500)
            update_chips(c_owner, lucky_comfort_bonus)
            try: c_name = bot.get_chat_member(chat_id, c_owner).user.first_name
            except: c_name = f"鼠主({c_owner})"
            consolation_mentions.append(f"<b>{c_name}</b> (<b>+{lucky_comfort_bonus:,}</b>)")
        owner_text += f"\n🎁 <b>【鼠主同慶安慰獎】</b>\n本局遺憾落敗（或不幸罹難）的鼠主： " + "、".join(consolation_mentions) + f" 獲得安慰分紅！\n"
        has_owner_bonus = True

    if has_owner_bonus: bot.send_message(chat_id, owner_text, parse_mode='HTML')
    
    current_race, race_odds, horse_statuses, scheduled_disasters, active_horse_luck = None, {}, {}, {}, {}
    if race_id in race_bets: del race_bets[race_id]

# ================== 📊 排行榜功能 ==================
@bot.message_handler(commands=['rk'])
def show_leaderboard(message):
    try:
        sync_username(message.from_user.id, message.from_user.username)
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT username, horse_name, horse_first, horse_second, horse_third, horse_losses, user_id 
                FROM users WHERE has_horse = 1 AND horse_name IS NOT NULL
            """)
            rows = c.fetchall()
            
        if not rows:
            bot.reply_to(message, "📊 **【賽鼠戰績風雲榜】**\n目前還沒有任何專屬賽鼠的比賽記錄！", parse_mode='Markdown')
            return

        def get_sort_key(row): return (row[2], row[3], row[4])
        sorted_rows = sorted(rows, key=get_sort_key, reverse=True)

        leaderboard_text = "📊 <b>【賽鼠殿堂 - 官方戰績榮譽榜】</b> 📊\n"
        leaderboard_text += "‾" * 30 + "\n"
        leaderboard_text += "💡 <i>(排序規律：依據老鼠【冠軍數】由高至低進行排名)</i>\n\n"

        for idx, row in enumerate(sorted_rows, 1):
            uname, h_name, firsts, seconds, thirds, losses, uid = row
            total_races = firsts + seconds + thirds + losses
            medal = "👑 🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"[{idx}]"
            try: nickname = bot.get_chat_member(message.chat.id, uid).user.first_name
            except: nickname = f"@{uname}" if uname else f"玩家({uid})"

            leaderboard_text += f"{medal} <b>{h_name}</b> (鼠主: {nickname})\n"
            leaderboard_text += f"    🏆 榮譽：🥇<code>{firsts} 冠</code> | 🥈<code>{seconds} 亞</code> | 🥉<code>{thirds} 季</code>\n"
            leaderboard_text += f"    📉 損益：❌<code>{losses} 輸</code> (總出賽次數: {total_races} 場)\n\n"

        bot.send_message(message.chat.id, leaderboard_text, parse_mode='HTML')
    except Exception as e: print(f"排行榜出錯: {e}")

# ================== 投注與退款邏輯 ==================
@bot.message_handler(commands=['win', 'pla', 'ww'])
def place_bet(message):
    global current_race, race_id, race_odds, user_bet_count, user_actual_deduct, current_horses
    
    error_help_text = "❌ **投注格式錯誤！**\n👉 獨贏：`/win [編號] [金額]`\n👉 位置：`/pla [編號] [金額]`\n👉 連贏：`/ww [A] [B] [金額]`"
    
    if current_race != "betting":
        bot.reply_to(message, "❌ 目前非投注時間！")
        return

    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    if user_bet_count.get(user_id, 0) >= 1:
        bot.reply_to(message, "❌ 您本場已投注過！更改請先輸入 /refund 退款。")
        return

    text_clean = message.text
    if f"{BOT_USERNAME}" in text_clean: 
        text_clean = text_clean.replace(f"{BOT_USERNAME}", "")
    elif f"@run1234567bot" in text_clean.lower(): 
        text_clean = text_clean.lower().replace("@run1234567bot", "")

    cmd = text_clean.split()
    if len(cmd) < 2:
        bot.reply_to(message, error_help_text, parse_mode='Markdown')
        return

    bet_type = cmd[0][1:].lower()  
    chips = get_chips(user_id)

    try:
        if bet_type in ["win", "pla"]:
            if len(cmd) < 3:
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
            
            horse_num = int(cmd[1])
            amount_str = cmd[2]
            
            if horse_num < 1 or horse_num > len(current_horses):
                bot.reply_to(message, f"❌ 找不到該號碼！本局只有 1 至 {len(current_horses)} 號賽鼠。", parse_mode='Markdown')
                return
                
            selected_horse_full = current_horses[horse_num-1]
            horse_name_clean = selected_horse_full.split('.', 1)[1] if '.' in selected_horse_full else selected_horse_full
            horse_display = f"（{horse_num}號）（{horse_name_clean}）"
            odds_val = race_odds[selected_horse_full] if bet_type == "win" else round(race_odds[selected_horse_full] * 0.4, 1)

        elif bet_type == "ww":
            if len(cmd) < 4:
                bot.reply_to(message, error_help_text, parse_mode='Markdown')
                return
                
            h1, h2 = int(cmd[1]), int(cmd[2])
            amount_str = cmd[3]
            
            if h1 == h2 or min(h1, h2) < 1 or max(h1, h2) > len(current_horses):
                bot.reply_to(message, f"❌ 號碼選擇不合法！請選擇兩個不同的編號 (1-{len(current_horses)})。", parse_mode='Markdown')
                return
                
            selected_horse_full = [current_horses[h1-1], current_horses[h2-1]]
            h1_clean = selected_horse_full[0].split('.', 1)[1] if '.' in selected_horse_full[0] else selected_horse_full[0]
            h2_clean = selected_horse_full[1].split('.', 1)[1] if '.' in selected_horse_full[1] else selected_horse_full[1]
            horse_display = f"（{h1},{h2}號）（{h1_clean} & {h2_clean}）"
            odds_val = round(race_odds[selected_horse_full[0]] * race_odds[selected_horse_full[1]], 1)
        else:
            return 

        if "%" in amount_str:
            pct = int(amount_str.replace("%", ""))
            bet_amount = int(chips * pct / 100)
        else:
            bet_amount = int(amount_str)

        if bet_amount <= 0:
            bot.reply_to(message, "❌ 投注金額必須大於 0 金幣！", parse_mode='Markdown')
            return

        credit = 100
        actual_deduct = max(0, bet_amount - credit)
        if actual_deduct > chips:
            bot.reply_to(message, f"❌ 金幣餘額不足！你目前只有 `{chips:,}` 金幣。", parse_mode='Markdown')
            return

        update_chips(user_id, -actual_deduct)
        user_actual_deduct[user_id] = actual_deduct 
        user_bet_count[user_id] = 1

        if user_id not in race_bets[race_id]: 
            race_bets[race_id][user_id] = []
        race_bets[race_id][user_id].append((bet_type, selected_horse_full, bet_amount))

        type_title = "獨贏" if bet_type == "win" else "位置" if bet_type == "pla" else "連贏"
        potential_win = int(bet_amount * odds_val)

        success_msg = f"（{type_title}）成功 🎊 {horse_display}\n投注幾錢：{bet_amount:,} 金幣\n幾多倍：{odds_val} 倍\n贏出總數可以收幾多：{potential_win:,} 金幣"
        bot.reply_to(message, success_msg, parse_mode='Markdown')

    except (ValueError, IndexError):
        bot.reply_to(message, error_help_text, parse_mode='Markdown')
    except Exception as e:
        print(f"投注未知系統錯誤: {e}")

@bot.message_handler(commands=['refund'])
def refund_bet(message):
    global current_race, race_id, race_bets, user_bet_count, user_refund_count, user_actual_deduct
    if current_race != "betting": return
    user_id = message.from_user.id
    if user_bet_count.get(user_id, 0) == 0 or user_refund_count.get(user_id, 0) >= 1: return
    refund_amount = user_actual_deduct.get(user_id, 0)
    update_chips(user_id, refund_amount) 
    if race_id in race_bets and user_id in race_bets[race_id]: del race_bets[race_id][user_id]
    user_bet_count[user_id] = 0
    user_refund_count[user_id] = 1
    bot.reply_to(message, f"✅ 退款成功！實退錢包金額：`{refund_amount:,}` 金幣", parse_mode='Markdown')

# ================== 每日福利 ==================
@bot.message_handler(commands=['daily'])
def daily(message):
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    today = date.today().isoformat()  
    
    with daily_lock:
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("SELECT last_daily FROM users WHERE user_id=?", (user_id,))
            last = c.fetchone()
            if last and last[0] == today:
                bot.reply_to(message, "❌ 你今天已經領過每日獎勵！明天再來吧。")
                return
            c.execute("UPDATE users SET last_daily=? WHERE user_id=?", (today, user_id))
            conn.commit()
            
        update_chips(user_id, 3000)
        bot.reply_to(message, "✅ **每日簽到成功！** +3000 金幣 💰")

# ================== 其他功能指令 ==================
@bot.message_handler(commands=['buy'])
def buy_horse(message):
    if message.chat.type != "private":
        bot.reply_to(message, f"❌ 限私訊使用！請點擊： {BOT_USERNAME}")
        return
    user_id = message.from_user.id
    sync_username(user_id, message.from_user.username)
    chips = get_chips(user_id)
    horse_info = get_user_horse(user_id)

    if horse_info["has_horse"] == 1:
        bot.reply_to(message, f"🐿️ 您已擁有一隻愛鼠：**{horse_info['horse_name']}**\n📊 目前戰績：`🥇{horse_info['first']} 冠 | 🥈{horse_info['second']} 亞 | 🥉{horse_info['third']} 季 | ❌{horse_info['losses']} 輸`", parse_mode='Markdown')
        return

    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2:
        bot.reply_to(message, f"🛒 **【專屬鼠隻拍賣所】**\n💰 售價：**{HORSE_PRICE:,}** 金幣\n👉 輸入：`/buy 你的鼠名`", parse_mode='Markdown')
        return

    h_name = cmd[1].strip()
    if len(h_name) < 1 or len(h_name) > 15 or chips < HORSE_PRICE: return

    update_chips(user_id, -HORSE_PRICE)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET has_horse=1, horse_name=?, horse_first=0, horse_second=0, horse_third=0, horse_losses=0 WHERE user_id=?", (h_name, user_id))
        conn.commit()
    bot.reply_to(message, f"🎉 專屬愛鼠 **「{h_name}」** 登記成功！戰績已初始化。")

@bot.message_handler(commands=['rename'])
def rename_horse(message):
    if message.chat.type != "private": return
    user_id = message.from_user.id
    horse_info = get_user_horse(user_id)
    if horse_info["has_horse"] == 0: return
    cmd = message.text.split(maxsplit=1)
    if len(cmd) < 2: return
    new_name = cmd[1].strip()
    if len(new_name) < 1 or len(new_name) > 15: return
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET horse_name=? WHERE user_id=?", (new_name, user_id))
        conn.commit()
    bot.reply_to(message, f"✨ 愛鼠已更名為：**「{new_name}」** 🐿️")

@bot.message_handler(commands=['money'])
def money(message):
    sync_username(message.from_user.id, message.from_user.username)
    chips = get_chips(message.from_user.id)
    bot.reply_to(message, f"💰 你的餘額：**{chips:,}** 金幣", parse_mode='Markdown')

@bot.message_handler(commands=['start'])
def start(message):
    sync_username(message.from_user.id, message.from_user.username)
    bot.reply_to(message, f"🐿️ **虛擬賽鼠 Bot 已就緒**\n輸入 /help 查看完整指令列表。")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    text = f"""🐿️ **指令列表**
/startrun - 開始新賽事
/money   - 查詢目前金幣
/refund    - 開賽前退款當局投注
/daily     - 領取每日福利 (+3000 金幣，每日限一次)
/pay - <b>【回覆訊息】</b>轉讓金幣
/buy       - <b>【私訊】</b>購買專屬鼠隻 ({HORSE_PRICE:,} 金幣)
/rename    - <b>【私訊】</b>自訂愛鼠修改名字
/rk        - <b>查看賽鼠官方勝負戰績風雲榜 📊</b>

【投注方式】/win 號碼 金額 | /pla 號碼 金額 | /ww 號碼1 號碼2 金幣
"""
    bot.reply_to(message, text, parse_mode='HTML')

# ================== 啟動服務 ==================
print(f"🐿️ {BOT_USERNAME} 【最新冷門保底隨機數量版】啟動！")
bot.infinity_polling(timeout=20, long_polling_timeout=10)
