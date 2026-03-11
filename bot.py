import sqlite3
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import random
import os

# -----------------------------
# CONFIG
# -----------------------------
ADMIN_ROLE_NAME = "mod"
DATABASE_NAME = "horses.db"
TOKEN = os.getenv("TOKEN")
UPDATES_CHANNEL_ID = 1470476262383423661
ALLOWED_GUILD_ID = 1416472620353847452

MAX_ENERGY = 100
ENERGY_REGEN_PER_HOUR = 80 / 24  # 80 energy every 24 hours

INTERACTIONS = {
    "pet": {
        "cooldown_hours": 1,
        "affinity_gain": 10,
        "energy_change": 10,
    },
    "brush": {
        "cooldown_hours": 2,
        "affinity_gain": 20,
        "energy_change": 20,
    },
    "treat": {
        "cooldown_hours": 3,
        "affinity_gain": 30,
        "energy_change": 10,
    },
    "ride": {
        "cooldown_hours": 24,
        "affinity_gain": 100,
        "energy_change": -80,
    },
    "lunge": {
        "cooldown_hours": 12,
        "affinity_gain": 50,
        "energy_change": -40,
    },
}

SELF_EDITABLE_PERSON_FIELDS = {
    "name",
    "age",
    "pronouns",
}

OWNER_EDITABLE_HORSE_FIELDS = {
    "show_name",
    "breed",
    "age",
    "color",
    "height",
    "discipline",
    "personality",
    "notes",
    "gender",
}

# -----------------------------
# BOT SETUP
# -----------------------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command("help")


# -----------------------------
# TIME HELPERS
# -----------------------------
def now_iso():
    return datetime.utcnow().isoformat()


def parse_iso(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def human_remaining(td):
    total_seconds = int(td.total_seconds())
    if total_seconds < 0:
        total_seconds = 0

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours}h {minutes}m"
    if minutes > 0:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


# -----------------------------
# DATABASE SETUP
# -----------------------------
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS people (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        age INTEGER,
        pronouns TEXT,
        is_boarder INTEGER NOT NULL DEFAULT 0,
        is_staff INTEGER NOT NULL DEFAULT 0,
        is_show_team INTEGER NOT NULL DEFAULT 0,
        is_leaser INTEGER NOT NULL DEFAULT 0,
        discord_user_id TEXT UNIQUE,
        discord_name TEXT,
        image_url TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        show_name TEXT,
        category TEXT NOT NULL,
        breed TEXT,
        age INTEGER,
        color TEXT,
        height TEXT,
        discipline TEXT,
        personality TEXT,
        notes TEXT,
        image_url TEXT,
        energy REAL NOT NULL DEFAULT 100,
        last_energy_update TEXT,
        gender TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horse_owners (
        horse_id INTEGER NOT NULL,
        person_id INTEGER NOT NULL,
        PRIMARY KEY (horse_id, person_id),
        FOREIGN KEY (horse_id) REFERENCES horses(id) ON DELETE CASCADE,
        FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horse_leasers (
        horse_id INTEGER NOT NULL,
        person_id INTEGER NOT NULL,
        PRIMARY KEY (horse_id, person_id),
        FOREIGN KEY (horse_id) REFERENCES horses(id) ON DELETE CASCADE,
        FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS horse_affinity (
        horse_id INTEGER NOT NULL,
        person_id INTEGER NOT NULL,
        affinity INTEGER NOT NULL DEFAULT 0,
        stable_points_earned INTEGER NOT NULL DEFAULT 0,
        last_pet TEXT,
        last_brush TEXT,
        last_treat TEXT,
        last_ride TEXT,
        last_lunge TEXT,
        PRIMARY KEY (horse_id, person_id),
        FOREIGN KEY (horse_id) REFERENCES horses(id) ON DELETE CASCADE,
        FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS random_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        message TEXT NOT NULL
    )
    """)

    try:
        cursor.execute("ALTER TABLE horses ADD COLUMN gender TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE people ADD COLUMN is_leaser INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# -----------------------------
# RANDOM UPDATE MESSAGE FUNCTIONS
# -----------------------------
def add_random_update_message(message):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO random_updates (message) VALUES (?)", (message,))
    conn.commit()
    conn.close()


def get_all_random_update_messages():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, message FROM random_updates ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return rows


def delete_random_update_message(message_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM random_updates WHERE id = ?", (message_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_random_update_message():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message FROM random_updates ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# -----------------------------
# PEOPLE DATABASE FUNCTIONS
# -----------------------------
def add_person_to_db(name, age, pronouns, is_boarder, is_staff, is_show_team, is_leaser, discord_user_id=None, discord_name=None):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO people (
        name, age, pronouns, is_boarder, is_staff, is_show_team, is_leaser, discord_user_id, discord_name, image_url
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        age,
        pronouns,
        int(is_boarder),
        int(is_staff),
        int(is_show_team),
        int(is_leaser),
        str(discord_user_id) if discord_user_id else None,
        discord_name,
        None
    ))

    conn.commit()
    conn.close()


def get_person_by_name(name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, name, age, pronouns, is_boarder, is_staff, is_show_team, is_leaser, discord_user_id, discord_name, image_url
    FROM people
    WHERE LOWER(name) = LOWER(?)
    """, (name,))
    result = cursor.fetchone()

    conn.close()
    return result


def get_person_by_discord_id(discord_user_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT id, name, age, pronouns, is_boarder, is_staff, is_show_team, is_leaser, discord_user_id, discord_name, image_url
    FROM people
    WHERE discord_user_id = ?
    """, (str(discord_user_id),))
    result = cursor.fetchone()

    conn.close()
    return result


def get_all_people():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, is_boarder, is_staff, is_show_team, is_leaser
    FROM people
    ORDER BY name
    """)
    results = cursor.fetchall()

    conn.close()
    return results


def get_horses_for_person(person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT h.name, h.show_name
    FROM horses h
    INNER JOIN horse_owners ho ON h.id = ho.horse_id
    INNER JOIN people p ON p.id = ho.person_id
    WHERE LOWER(p.name) = LOWER(?)
    ORDER BY h.name
    """, (person_name,))
    results = cursor.fetchall()

    conn.close()
    return results


def get_leased_horses_for_person(person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT h.name, h.show_name
    FROM horses h
    INNER JOIN horse_leasers hl ON h.id = hl.horse_id
    INNER JOIN people p ON p.id = hl.person_id
    WHERE LOWER(p.name) = LOWER(?)
    ORDER BY h.name
    """, (person_name,))
    results = cursor.fetchall()

    conn.close()
    return results


def update_person_field(name, field, value):
    allowed_fields = {
        "name",
        "age",
        "pronouns",
        "is_boarder",
        "is_staff",
        "is_show_team",
        "is_leaser",
        "discord_user_id",
        "discord_name",
        "image_url"
    }

    if field not in allowed_fields:
        return False, "That field cannot be edited."

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    query = f"UPDATE people SET {field} = ? WHERE LOWER(name) = LOWER(?)"
    cursor.execute(query, (value, name))

    updated_count = cursor.rowcount
    conn.commit()
    conn.close()

    if updated_count == 0:
        return False, "Person not found."

    return True, f"{name}'s {field} was updated."


def delete_person(name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT COUNT(*)
    FROM horse_owners ho
    INNER JOIN people p ON p.id = ho.person_id
    WHERE LOWER(p.name) = LOWER(?)
    """, (name,))
    owned_count = cursor.fetchone()[0]

    cursor.execute("""
    SELECT COUNT(*)
    FROM horse_leasers hl
    INNER JOIN people p ON p.id = hl.person_id
    WHERE LOWER(p.name) = LOWER(?)
    """, (name,))
    leased_count = cursor.fetchone()[0]

    if owned_count > 0 or leased_count > 0:
        conn.close()
        return False, "That person is still linked to one or more horses. Remove those links first."

    cursor.execute("""
    DELETE FROM people
    WHERE LOWER(name) = LOWER(?)
    """, (name,))
    deleted_count = cursor.rowcount

    conn.commit()
    conn.close()

    if deleted_count == 0:
        return False, "Person not found."

    return True, f"{name} was removed."


# -----------------------------
# HORSE DATABASE FUNCTIONS
# -----------------------------
def add_horse_to_db(name, show_name, category, age):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO horses (
        name, show_name, category, breed, age, color,
        height, discipline, personality, notes, image_url,
        energy, last_energy_update, gender
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name,
        show_name,
        category,
        "N/A",
        age,
        "N/A",
        "N/A",
        "N/A",
        "N/A",
        "N/A",
        None,
        100,
        now_iso(),
        "N/A"
    ))

    conn.commit()
    conn.close()


def get_horse_owners(horse_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT p.name, p.discord_name
    FROM people p
    INNER JOIN horse_owners ho ON p.id = ho.person_id
    WHERE ho.horse_id = ?
    ORDER BY p.name
    """, (horse_id,))
    results = cursor.fetchall()

    conn.close()
    return results


def get_horse_leasers(horse_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT p.name, p.discord_name
    FROM people p
    INNER JOIN horse_leasers hl ON p.id = hl.person_id
    WHERE hl.horse_id = ?
    ORDER BY p.name
    """, (horse_id,))
    results = cursor.fetchall()

    conn.close()
    return results


def get_horse_from_db(name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        name,
        show_name,
        category,
        breed,
        age,
        color,
        height,
        discipline,
        personality,
        notes,
        image_url,
        energy,
        last_energy_update,
        gender
    FROM horses
    WHERE LOWER(name) = LOWER(?)
    """, (name,))
    result = cursor.fetchone()

    conn.close()
    return result


def get_all_horses():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, show_name, category
    FROM horses
    ORDER BY name
    """)
    results = cursor.fetchall()

    conn.close()
    return results


def get_horses_by_category(category):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT name, show_name
    FROM horses
    WHERE LOWER(category) = LOWER(?)
    ORDER BY name
    """, (category,))
    results = cursor.fetchall()

    conn.close()
    return results


def delete_horse_from_db(name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    DELETE FROM horses
    WHERE LOWER(name) = LOWER(?)
    """, (name,))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count


def update_horse_field(name, field, value):
    allowed_fields = {
        "show_name",
        "category",
        "breed",
        "age",
        "color",
        "height",
        "discipline",
        "personality",
        "notes",
        "image_url",
        "gender"
    }

    if field not in allowed_fields:
        return False, "That field cannot be edited."

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    query = f"UPDATE horses SET {field} = ? WHERE LOWER(name) = LOWER(?)"
    cursor.execute(query, (value, name))

    updated_count = cursor.rowcount
    conn.commit()
    conn.close()

    if updated_count == 0:
        return False, "Horse not found."

    return True, f"{name}'s {field} was updated."


def add_owner_to_horse(horse_name, person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM horses WHERE LOWER(name) = LOWER(?)", (horse_name,))
    horse = cursor.fetchone()

    if not horse:
        conn.close()
        return False, "Horse not found."

    cursor.execute("SELECT id FROM people WHERE LOWER(name) = LOWER(?)", (person_name,))
    person = cursor.fetchone()

    if not person:
        conn.close()
        return False, "That person does not exist in the database."

    horse_id = horse[0]
    person_id = person[0]

    try:
        cursor.execute("""
        INSERT INTO horse_owners (horse_id, person_id)
        VALUES (?, ?)
        """, (horse_id, person_id))

        cursor.execute("""
        INSERT OR IGNORE INTO horse_affinity (
            horse_id, person_id, affinity, stable_points_earned,
            last_pet, last_brush, last_treat, last_ride, last_lunge
        )
        VALUES (?, ?, 0, 0, NULL, NULL, NULL, NULL, NULL)
        """, (horse_id, person_id))

        conn.commit()
        conn.close()
        return True, f"{person_name} was added as an owner of {horse_name}."
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"{person_name} is already listed as an owner of {horse_name}."


def remove_owner_from_horse(horse_name, person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM horses WHERE LOWER(name) = LOWER(?)", (horse_name,))
    horse = cursor.fetchone()

    cursor.execute("SELECT id FROM people WHERE LOWER(name) = LOWER(?)", (person_name,))
    person = cursor.fetchone()

    if not horse or not person:
        conn.close()
        return False, "Horse or person not found."

    horse_id = horse[0]
    person_id = person[0]

    cursor.execute("""
    DELETE FROM horse_owners
    WHERE horse_id = ? AND person_id = ?
    """, (horse_id, person_id))

    deleted_count = cursor.rowcount

    cursor.execute("""
    DELETE FROM horse_affinity
    WHERE horse_id = ? AND person_id = ?
    """, (horse_id, person_id))

    conn.commit()
    conn.close()

    if deleted_count == 0:
        return False, "That owner link was not found."

    return True, f"{person_name} was removed as an owner of {horse_name}."


def add_leaser_to_horse(horse_name, person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM horses WHERE LOWER(name) = LOWER(?)", (horse_name,))
    horse = cursor.fetchone()

    if not horse:
        conn.close()
        return False, "Horse not found."

    cursor.execute("SELECT id FROM people WHERE LOWER(name) = LOWER(?)", (person_name,))
    person = cursor.fetchone()

    if not person:
        conn.close()
        return False, "That person does not exist in the database."

    horse_id = horse[0]
    person_id = person[0]

    try:
        cursor.execute("""
        INSERT INTO horse_leasers (horse_id, person_id)
        VALUES (?, ?)
        """, (horse_id, person_id))

        cursor.execute("""
        INSERT OR IGNORE INTO horse_affinity (
            horse_id, person_id, affinity, stable_points_earned,
            last_pet, last_brush, last_treat, last_ride, last_lunge
        )
        VALUES (?, ?, 0, 0, NULL, NULL, NULL, NULL, NULL)
        """, (horse_id, person_id))

        conn.commit()
        conn.close()
        return True, f"{person_name} was added as a leaser of {horse_name}."
    except sqlite3.IntegrityError:
        conn.close()
        return False, f"{person_name} is already listed as a leaser of {horse_name}."


def remove_leaser_from_horse(horse_name, person_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM horses WHERE LOWER(name) = LOWER(?)", (horse_name,))
    horse = cursor.fetchone()

    cursor.execute("SELECT id FROM people WHERE LOWER(name) = LOWER(?)", (person_name,))
    person = cursor.fetchone()

    if not horse or not person:
        conn.close()
        return False, "Horse or person not found."

    horse_id = horse[0]
    person_id = person[0]

    cursor.execute("""
    DELETE FROM horse_leasers
    WHERE horse_id = ? AND person_id = ?
    """, (horse_id, person_id))

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_count == 0:
        return False, "That lease link was not found."

    return True, f"{person_name} was removed as a leaser of {horse_name}."


# -----------------------------
# AFFINITY / ENERGY FUNCTIONS
# -----------------------------
def get_or_create_affinity_row(horse_id, person_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT OR IGNORE INTO horse_affinity (
        horse_id, person_id, affinity, stable_points_earned,
        last_pet, last_brush, last_treat, last_ride, last_lunge
    )
    VALUES (?, ?, 0, 0, NULL, NULL, NULL, NULL, NULL)
    """, (horse_id, person_id))

    cursor.execute("""
    SELECT horse_id, person_id, affinity, stable_points_earned,
           last_pet, last_brush, last_treat, last_ride, last_lunge
    FROM horse_affinity
    WHERE horse_id = ? AND person_id = ?
    """, (horse_id, person_id))

    row = cursor.fetchone()
    conn.commit()
    conn.close()
    return row


def update_horse_energy(horse_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT energy, last_energy_update
    FROM horses
    WHERE id = ?
    """, (horse_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return None

    current_energy, last_update_str = result
    current_energy = float(current_energy)
    last_update = parse_iso(last_update_str) if last_update_str else datetime.utcnow()
    now = datetime.utcnow()

    elapsed_hours = max(0, (now - last_update).total_seconds() / 3600)
    regenerated = elapsed_hours * ENERGY_REGEN_PER_HOUR
    new_energy = min(MAX_ENERGY, current_energy + regenerated)

    cursor.execute("""
    UPDATE horses
    SET energy = ?, last_energy_update = ?
    WHERE id = ?
    """, (new_energy, now_iso(), horse_id))

    conn.commit()
    conn.close()
    return new_energy


def get_horse_energy(horse_id):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT energy FROM horses WHERE id = ?", (horse_id,))
    row = cursor.fetchone()
    conn.close()
    return float(row[0]) if row else None


def set_horse_energy(horse_id, new_energy):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE horses
    SET energy = ?, last_energy_update = ?
    WHERE id = ?
    """, (max(0, min(MAX_ENERGY, new_energy)), now_iso(), horse_id))
    conn.commit()
    conn.close()


def get_person_owned_horse(person_id, horse_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT h.id, h.name
    FROM horses h
    INNER JOIN horse_owners ho ON ho.horse_id = h.id
    WHERE ho.person_id = ? AND LOWER(h.name) = LOWER(?)
    """, (person_id, horse_name))
    row = cursor.fetchone()

    conn.close()
    return row


def get_person_leased_horse(person_id, horse_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT h.id, h.name
    FROM horses h
    INNER JOIN horse_leasers hl ON hl.horse_id = h.id
    WHERE hl.person_id = ? AND LOWER(h.name) = LOWER(?)
    """, (person_id, horse_name))
    row = cursor.fetchone()

    conn.close()
    return row


def perform_interaction(person_id, person_name, horse_name, interaction_key):
    if interaction_key not in INTERACTIONS:
        return False, "Invalid interaction."

    horse_row = get_person_owned_horse(person_id, horse_name)

    if not horse_row:
        horse_row = get_person_leased_horse(person_id, horse_name)

    if not horse_row:
        return False, "You do not own or lease that horse, or the horse does not exist."

    horse_id, real_horse_name = horse_row

    affinity_row = get_or_create_affinity_row(horse_id, person_id)
    _, _, affinity, stable_points_earned, last_pet, last_brush, last_treat, last_ride, last_lunge = affinity_row

    last_map = {
        "pet": last_pet,
        "brush": last_brush,
        "treat": last_treat,
        "ride": last_ride,
        "lunge": last_lunge,
    }

    config = INTERACTIONS[interaction_key]
    cooldown = timedelta(hours=config["cooldown_hours"])
    last_used = parse_iso(last_map[interaction_key])

    now = datetime.utcnow()
    if last_used:
        remaining = (last_used + cooldown) - now
        if remaining.total_seconds() > 0:
            return False, f"You can't {interaction_key} {real_horse_name} yet. Cooldown remaining: {human_remaining(remaining)}."

    current_energy = update_horse_energy(horse_id)
    energy_change = config["energy_change"]

    if energy_change < 0 and current_energy < abs(energy_change):
        return False, f"{real_horse_name} does not have enough energy for that. Current energy: {current_energy:.1f}/{MAX_ENERGY}."

    new_energy = max(0, min(MAX_ENERGY, current_energy + energy_change))
    set_horse_energy(horse_id, new_energy)

    new_affinity = affinity + config["affinity_gain"]
    old_thresholds = affinity // 100
    new_thresholds = new_affinity // 100
    thresholds_gained = new_thresholds - old_thresholds
    points_to_add = thresholds_gained * 20
    new_stable_points = stable_points_earned + points_to_add

    last_field = f"last_{interaction_key}"

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute(f"""
    UPDATE horse_affinity
    SET affinity = ?, stable_points_earned = ?, {last_field} = ?
    WHERE horse_id = ? AND person_id = ?
    """, (new_affinity, new_stable_points, now_iso(), horse_id, person_id))
    conn.commit()
    conn.close()

    points_text = f"\nYou earned **{points_to_add} stable points**." if points_to_add > 0 else ""

    return True, (
        f"You used **{interaction_key}** on **{real_horse_name}**.\n"
        f"Affinity: **{new_affinity}**\n"
        f"Horse energy: **{new_energy:.1f}/{MAX_ENERGY}**{points_text}"
    )


def get_affinity_data(person_id, horse_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT h.id, h.name
    FROM horses h
    INNER JOIN horse_owners ho ON ho.horse_id = h.id
    WHERE ho.person_id = ? AND LOWER(h.name) = LOWER(?)
    """, (person_id, horse_name))
    horse = cursor.fetchone()

    if not horse:
        cursor.execute("""
        SELECT h.id, h.name
        FROM horses h
        INNER JOIN horse_leasers hl ON hl.horse_id = h.id
        WHERE hl.person_id = ? AND LOWER(h.name) = LOWER(?)
        """, (person_id, horse_name))
        horse = cursor.fetchone()

    if not horse:
        conn.close()
        return None

    horse_id, real_horse_name = horse

    cursor.execute("""
    INSERT OR IGNORE INTO horse_affinity (
        horse_id, person_id, affinity, stable_points_earned,
        last_pet, last_brush, last_treat, last_ride, last_lunge
    )
    VALUES (?, ?, 0, 0, NULL, NULL, NULL, NULL, NULL)
    """, (horse_id, person_id))

    cursor.execute("""
    SELECT affinity, stable_points_earned, last_pet, last_brush, last_treat, last_ride, last_lunge
    FROM horse_affinity
    WHERE horse_id = ? AND person_id = ?
    """, (horse_id, person_id))
    data = cursor.fetchone()

    conn.commit()
    conn.close()

    update_horse_energy(horse_id)
    current_energy = get_horse_energy(horse_id)

    return real_horse_name, current_energy, data


# -----------------------------
# HELPERS
# -----------------------------
def is_admin():
    async def predicate(ctx):
        return any(role.name.lower() == ADMIN_ROLE_NAME.lower() for role in ctx.author.roles)
    return commands.check(predicate)


def yes_no_to_bool(value: str):
    value = value.lower()
    if value in ["yes", "y", "true", "1"]:
        return True
    if value in ["no", "n", "false", "0"]:
        return False
    raise ValueError("Please use yes or no.")


def format_horse_name(name, show_name):
    if show_name and show_name.strip() and show_name.strip().lower() != "n/a":
        return f"**{name}** — *{show_name}*"
    return f"**{name}**"


async def send_update_message(text):
    channel = bot.get_channel(UPDATES_CHANNEL_ID)
    if channel is not None:
        await channel.send(text)

def in_allowed_guild():
    async def predicate(ctx):
        return ctx.guild is not None and ctx.guild.id == ALLOWED_GUILD_ID
    return commands.check(predicate)


def create_horse_embed(horse_data):
    (
        horse_id,
        name,
        show_name,
        category,
        breed,
        age,
        color,
        height,
        discipline,
        personality,
        notes,
        image_url,
        energy,
        last_energy_update,
        gender
    ) = horse_data

    current_energy = update_horse_energy(horse_id)
    owners = get_horse_owners(horse_id)
    leasers = get_horse_leasers(horse_id)

    if owners:
        owner_lines = []
        for owner_name, owner_discord_name in owners:
            if owner_discord_name:
                owner_lines.append(f"{owner_name} ({owner_discord_name})")
            else:
                owner_lines.append(owner_name)
        owner_display = "\n".join(owner_lines)
    else:
        owner_display = "N/A"

    if leasers:
        leaser_lines = []
        for leaser_name, leaser_discord_name in leasers:
            if leaser_discord_name:
                leaser_lines.append(f"{leaser_name} ({leaser_discord_name})")
            else:
                leaser_lines.append(leaser_name)
        leaser_display = "\n".join(leaser_lines)
    else:
        leaser_display = "N/A"

    embed = discord.Embed(
        title=name,
        description=f"Horse profile for **{name}**",
        color=discord.Color.teal()
    )

    embed.add_field(name="Barn Name", value=name or "N/A", inline=True)
    embed.add_field(name="Show Name", value=show_name or "N/A", inline=True)
    embed.add_field(name="Gender", value=gender or "N/A", inline=True)
    embed.add_field(name="Category", value=category.title() if category else "N/A", inline=True)
    embed.add_field(name="Owners", value=owner_display, inline=False)
    embed.add_field(name="Leasers", value=leaser_display, inline=False)
    embed.add_field(name="Energy", value=f"{current_energy:.1f}/{MAX_ENERGY}", inline=True)
    embed.add_field(name="Breed", value=breed or "N/A", inline=True)
    embed.add_field(name="Age", value=str(age) if age is not None else "N/A", inline=True)
    embed.add_field(name="Color", value=color or "N/A", inline=True)
    embed.add_field(name="Height", value=height or "N/A", inline=True)
    embed.add_field(name="Discipline", value=discipline or "N/A", inline=False)
    embed.add_field(name="Personality", value=personality or "N/A", inline=False)
    embed.add_field(name="Notes", value=notes or "N/A", inline=False)

    if image_url:
        embed.set_image(url=image_url)

    return embed


def create_person_embed(person_data):
    person_id, name, age, pronouns, is_boarder, is_staff, is_show_team, is_leaser, discord_user_id, discord_name, image_url = person_data

    roles = []
    if is_boarder:
        roles.append("Boarder")
    if is_staff:
        roles.append("Staff")
    if is_show_team:
        roles.append("Show Team")
    if is_leaser:
        roles.append("Leaser")

    role_text = ", ".join(roles) if roles else "None"

    discord_text = discord_name if discord_name else "Not linked"
    if discord_user_id:
        discord_text += f"\nID: {discord_user_id}"

    owned_horses = get_horses_for_person(name)
    horse_text = "\n".join(format_horse_name(h_name, h_show) for h_name, h_show in owned_horses) if owned_horses else "None"

    leased_horses = get_leased_horses_for_person(name)
    leased_text = "\n".join(format_horse_name(h_name, h_show) for h_name, h_show in leased_horses) if leased_horses else "None"

    embed = discord.Embed(
        title=name,
        description=f"Person profile for **{name}**",
        color=discord.Color.blurple()
    )

    embed.add_field(name="Age", value=str(age) if age is not None else "N/A", inline=True)
    embed.add_field(name="Pronouns", value=pronouns or "N/A", inline=True)
    embed.add_field(name="Roles", value=role_text, inline=False)
    embed.add_field(name="Discord", value=discord_text, inline=False)
    embed.add_field(name="Owned Horses", value=horse_text, inline=False)
    embed.add_field(name="Leased Horses", value=leased_text, inline=False)

    if image_url:
        embed.set_thumbnail(url=image_url)

    return embed


# -----------------------------
# RANDOM BACKGROUND UPDATES
# -----------------------------
@tasks.loop(hours=1)
async def random_updates_loop():
    channel = bot.get_channel(UPDATES_CHANNEL_ID)
    if channel is None:
        return

    if random.random() < 0.25:
        message = get_random_update_message()
        if message:
            await channel.send(f"📣 {message}")


# -----------------------------
# EVENTS
# -----------------------------
@bot.event
async def on_ready():
    init_db()

    if not random_updates_loop.is_running():
        random_updates_loop.start()

    print(f"Logged in as {bot.user}")

@bot.check
async def globally_block_other_guilds(ctx):
    return ctx.guild is not None and ctx.guild.id == ALLOWED_GUILD_ID

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You do not have permission to use that command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You're missing required information for that command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("One of the values you entered is invalid.")
    elif isinstance(error, commands.CommandNotFound):
        return
    else:
        raise error


# -----------------------------
# PUBLIC COMMANDS
# -----------------------------
@bot.command()
async def horse(ctx, *, name):
    horse_data = get_horse_from_db(name)

    if not horse_data:
        await ctx.send("Horse not found.")
        return

    embed = create_horse_embed(horse_data)
    await ctx.send(embed=embed)


@bot.command()
async def horses(ctx):
    results = get_all_horses()

    if not results:
        await ctx.send("There are no horses in the database yet.")
        return

    lesson_horses = []
    boarder_horses = []
    lease_horses = []
    other_horses = []

    for name, show_name, category in results:
        formatted = format_horse_name(name, show_name)
        cat = category.lower()

        if cat == "lesson":
            lesson_horses.append(formatted)
        elif cat == "boarder":
            boarder_horses.append(formatted)
        elif cat == "lease":
            lease_horses.append(formatted)
        else:
            other_horses.append(formatted)

    embed = discord.Embed(title="Stable Horses", color=discord.Color.green())
    embed.add_field(name="Lesson Horses", value="\n".join(lesson_horses) if lesson_horses else "None", inline=False)
    embed.add_field(name="Boarder Horses", value="\n".join(boarder_horses) if boarder_horses else "None", inline=False)
    embed.add_field(name="Lease Horses", value="\n".join(lease_horses) if lease_horses else "None", inline=False)

    if other_horses:
        embed.add_field(name="Other", value="\n".join(other_horses), inline=False)

    await ctx.send(embed=embed)


@bot.command()
async def person(ctx, *, name):
    person_data = get_person_by_name(name)

    if not person_data:
        await ctx.send("Person not found.")
        return

    embed = create_person_embed(person_data)
    await ctx.send(embed=embed)


@bot.command()
async def people(ctx):
    results = get_all_people()

    if not results:
        await ctx.send("There are no people in the database yet.")
        return

    lines = []
    for name, is_boarder, is_staff, is_show_team, is_leaser in results:
        tags = []
        if is_boarder:
            tags.append("Boarder")
        if is_staff:
            tags.append("Staff")
        if is_show_team:
            tags.append("Show Team")
        if is_leaser:
            tags.append("Leaser")

        if tags:
            lines.append(f"**{name}** — {', '.join(tags)}")
        else:
            lines.append(f"**{name}**")

    embed = discord.Embed(
        title="People",
        description="\n".join(lines),
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)


@bot.command()
async def myhorsebond(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    person_id = linked_person[0]
    person_name = linked_person[1]

    result = get_affinity_data(person_id, horse_name)
    if not result:
        await ctx.send("You do not own or lease that horse, or the horse does not exist.")
        return

    real_horse_name, energy, data = result
    affinity, stable_points_earned, last_pet, last_brush, last_treat, last_ride, last_lunge = data

    embed = discord.Embed(
        title=f"{person_name} & {real_horse_name}",
        description="Your horse bond stats",
        color=discord.Color.magenta()
    )
    embed.add_field(name="Affinity", value=str(affinity), inline=True)
    embed.add_field(name="Stable Points Earned", value=str(stable_points_earned), inline=True)
    embed.add_field(name="Horse Energy", value=f"{energy:.1f}/{MAX_ENERGY}", inline=True)

    await ctx.send(embed=embed)


@bot.command()
async def pethorse(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    success, message = perform_interaction(linked_person[0], linked_person[1], horse_name, "pet")
    await ctx.send(message)


@bot.command()
async def brushhorse(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    success, message = perform_interaction(linked_person[0], linked_person[1], horse_name, "brush")
    await ctx.send(message)


@bot.command()
async def treathorse(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    success, message = perform_interaction(linked_person[0], linked_person[1], horse_name, "treat")
    await ctx.send(message)


@bot.command()
async def ridehorse(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    success, message = perform_interaction(linked_person[0], linked_person[1], horse_name, "ride")
    await ctx.send(message)


@bot.command()
async def lungehorse(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person in the database.")
        return

    success, message = perform_interaction(linked_person[0], linked_person[1], horse_name, "lunge")
    await ctx.send(message)


@bot.command()
async def myeditperson(ctx, field, *, value):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person profile.")
        return

    field = field.lower()

    if field not in SELF_EDITABLE_PERSON_FIELDS:
        await ctx.send("You are not allowed to edit that field on your own profile.")
        return

    person_name = linked_person[1]

    if field == "age":
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Age must be a number.")
            return

    success, message = update_person_field(person_name, field, value)
    await ctx.send(message)


@bot.command()
async def myedithorse(ctx, horse_name, field, *, value):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person profile.")
        return

    person_id = linked_person[0]
    field = field.lower()

    if field not in OWNER_EDITABLE_HORSE_FIELDS:
        await ctx.send("You are not allowed to edit that field on a horse profile.")
        return

    owned_horse = get_person_owned_horse(person_id, horse_name)
    if not owned_horse:
        await ctx.send("You do not own that horse, or the horse does not exist.")
        return

    real_horse_name = owned_horse[1]

    if field == "age":
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Age must be a number.")
            return

    success, message = update_horse_field(real_horse_name, field, value)
    await ctx.send(message)


@bot.command()
async def mysetpersonphoto(ctx):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person profile.")
        return

    if not ctx.message.attachments:
        await ctx.send("Please attach an image to the same message as the command.")
        return

    attachment = ctx.message.attachments[0]

    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        await ctx.send("That attachment is not an image.")
        return

    person_name = linked_person[1]
    image_url = attachment.url

    success, message = update_person_field(person_name, "image_url", image_url)
    await ctx.send(message)


@bot.command()
async def mysethorsephoto(ctx, *, horse_name):
    linked_person = get_person_by_discord_id(ctx.author.id)
    if not linked_person:
        await ctx.send("Your Discord account is not linked to a person profile.")
        return

    person_id = linked_person[0]
    owned_horse = get_person_owned_horse(person_id, horse_name)

    if not owned_horse:
        await ctx.send("You do not own that horse, or the horse does not exist.")
        return

    if not ctx.message.attachments:
        await ctx.send("Please attach an image to the same message as the command.")
        return

    attachment = ctx.message.attachments[0]

    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        await ctx.send("That attachment is not an image.")
        return

    real_horse_name = owned_horse[1]
    image_url = attachment.url

    success, message = update_horse_field(real_horse_name, "image_url", image_url)
    await ctx.send(message)


@bot.command()
async def stablehelp(ctx):
    embed = discord.Embed(title="Stable Bot Commands", color=discord.Color.purple())

    embed.add_field(
        name="Public Commands",
        value=(
            "`!horse <barn name>`\n"
            "`!horses`\n"
            "`!person <name>`\n"
            "`!people`\n"
            "`!myhorsebond <horse name>`\n"
            "`!pethorse <horse name>`\n"
            "`!brushhorse <horse name>`\n"
            "`!treathorse <horse name>`\n"
            "`!ridehorse <horse name>`\n"
            "`!lungehorse <horse name>`\n"
            "`!myeditperson <field> <value>`\n"
            "`!myedithorse <horse name> <field> <value>`\n"
            "`!mysetpersonphoto` + attach image\n"
            "`!mysethorsephoto <horse name>` + attach image\n"
            "`!stablehelp`"
        ),
        inline=False
    )

    embed.add_field(
        name="Admin Commands",
        value=(
            "`!addperson <name> <age> <pronouns> <boarder yes/no> <staff yes/no> <showteam yes/no> <leaser yes/no>`\n"
            "`!addpersonmention <@user> <age> <pronouns> <boarder yes/no> <staff yes/no> <showteam yes/no> <leaser yes/no>`\n"
            "`!linkpersondiscord <person_name> <@user>`\n"
            "`!unlinkpersondiscord <person_name>`\n"
            "`!editperson <name> <field> <value>`\n"
            "`!removeperson <name>`\n"
            "`!setpersonphoto <name>` + attach image\n"
            "`!removepersonphoto <name>`\n"
            "`!addhorse <barn_name> <category> <age>`\n"
            "`!edithorse <barn_name> <field> <value>`\n"
            "`!addowner <horse_name> <person_name>`\n"
            "`!removeowner <horse_name> <person_name>`\n"
            "`!addleaser <horse_name> <person_name>`\n"
            "`!removeleaser <horse_name> <person_name>`\n"
            "`!removehorse <barn_name>`\n"
            "`!sethorsephoto <barn_name>` + attach image\n"
            "`!removehorsephoto <barn_name>`\n"
            "`!stableupdate <message>`\n"
            "`!feedall`\n"
            "`!waterall`\n"
            "`!turnoutall`\n"
            "`!stallsdone`\n"
            "`!addupdatemessage <message>`\n"
            "`!listupdatemessages`\n"
            "`!removeupdatemessage <id>`"
        ),
        inline=False
    )

    await ctx.send(embed=embed)


# -----------------------------
# ADMIN COMMANDS - PEOPLE
# -----------------------------
@bot.command()
@is_admin()
async def addperson(ctx, name, age: int, pronouns, boarder, staff, showteam, leaser):
    try:
        is_boarder = yes_no_to_bool(boarder)
        is_staff = yes_no_to_bool(staff)
        is_show_team = yes_no_to_bool(showteam)
        is_leaser = yes_no_to_bool(leaser)
    except ValueError as e:
        await ctx.send(str(e))
        return

    try:
        add_person_to_db(
            name=name,
            age=age,
            pronouns=pronouns,
            is_boarder=is_boarder,
            is_staff=is_staff,
            is_show_team=is_show_team,
            is_leaser=is_leaser
        )
        await ctx.send(f"{name} was added to the people database.")
    except sqlite3.IntegrityError:
        await ctx.send("That person already exists, or the Discord account is already linked to someone else.")


@bot.command()
@is_admin()
async def addpersonmention(ctx, member: discord.Member, age: int, pronouns, boarder, staff, showteam, leaser):
    try:
        is_boarder = yes_no_to_bool(boarder)
        is_staff = yes_no_to_bool(staff)
        is_show_team = yes_no_to_bool(showteam)
        is_leaser = yes_no_to_bool(leaser)
    except ValueError as e:
        await ctx.send(str(e))
        return

    try:
        add_person_to_db(
            name=member.display_name,
            age=age,
            pronouns=pronouns,
            is_boarder=is_boarder,
            is_staff=is_staff,
            is_show_team=is_show_team,
            is_leaser=is_leaser,
            discord_user_id=member.id,
            discord_name=str(member)
        )
        await ctx.send(f"{member.display_name} was added and linked to {member.mention}.")
    except sqlite3.IntegrityError:
        await ctx.send("That person already exists, or that Discord account is already linked.")


@bot.command()
@is_admin()
async def linkpersondiscord(ctx, person_name, member: discord.Member):
    person_data = get_person_by_name(person_name)

    if not person_data:
        await ctx.send("Person not found.")
        return

    existing = get_person_by_discord_id(member.id)
    if existing and existing[1].lower() != person_name.lower():
        await ctx.send("That Discord account is already linked to another person.")
        return

    success1, _ = update_person_field(person_name, "discord_user_id", str(member.id))
    success2, _ = update_person_field(person_name, "discord_name", str(member))

    if success1 and success2:
        await ctx.send(f"{person_name} is now linked to {member.mention}.")
    else:
        await ctx.send("There was a problem linking that Discord account.")


@bot.command()
@is_admin()
async def unlinkpersondiscord(ctx, *, person_name):
    person_data = get_person_by_name(person_name)

    if not person_data:
        await ctx.send("Person not found.")
        return

    success1, _ = update_person_field(person_name, "discord_user_id", None)
    success2, _ = update_person_field(person_name, "discord_name", None)

    if success1 and success2:
        await ctx.send(f"{person_name} is no longer linked to a Discord account.")
    else:
        await ctx.send("There was a problem unlinking that Discord account.")


@bot.command()
@is_admin()
async def editperson(ctx, name, field, *, value):
    field = field.lower()

    if field == "age":
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Age must be a number.")
            return

    if field in ["is_boarder", "is_staff", "is_show_team", "is_leaser"]:
        try:
            value = int(yes_no_to_bool(value))
        except ValueError as e:
            await ctx.send(str(e))
            return

    success, message = update_person_field(name, field, value)
    await ctx.send(message)


@bot.command()
@is_admin()
async def removeperson(ctx, *, name):
    success, message = delete_person(name)
    await ctx.send(message)


@bot.command()
@is_admin()
async def setpersonphoto(ctx, *, person_name):
    person_data = get_person_by_name(person_name)

    if not person_data:
        await ctx.send("Person not found.")
        return

    if not ctx.message.attachments:
        await ctx.send("Please attach an image to the same message as the command.")
        return

    attachment = ctx.message.attachments[0]

    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        await ctx.send("That attachment is not an image.")
        return

    image_url = attachment.url
    success, message = update_person_field(person_name, "image_url", image_url)

    if success:
        await ctx.send(f"Photo added for {person_name}.")
    else:
        await ctx.send(message)


@bot.command()
@is_admin()
async def removepersonphoto(ctx, *, person_name):
    person_data = get_person_by_name(person_name)

    if not person_data:
        await ctx.send("Person not found.")
        return

    success, message = update_person_field(person_name, "image_url", None)

    if success:
        await ctx.send(f"Photo removed for {person_name}.")
    else:
        await ctx.send(message)


# -----------------------------
# ADMIN COMMANDS - HORSES
# -----------------------------
@bot.command()
@is_admin()
async def addhorse(ctx, name, category, age: int):
    category = category.lower()

    if category not in ["lesson", "boarder", "lease"]:
        await ctx.send("Category must be either `lesson`, `boarder`, or `lease`.")
        return

    try:
        add_horse_to_db(
            name=name,
            show_name="N/A",
            category=category,
            age=age
        )
        await ctx.send(f"{name} was added successfully.")
    except sqlite3.IntegrityError:
        await ctx.send("That horse already exists.")


@bot.command()
@is_admin()
async def edithorse(ctx, name, field, *, value):
    field = field.lower()

    if field == "age":
        try:
            value = int(value)
        except ValueError:
            await ctx.send("Age must be a number.")
            return

    if field == "category":
        value = value.lower()
        if value not in ["lesson", "boarder", "lease"]:
            await ctx.send("Category must be either `lesson`, `boarder`, or `lease`.")
            return

    success, message = update_horse_field(name, field, value)
    await ctx.send(message)


@bot.command()
@is_admin()
async def addowner(ctx, horse_name, *, person_name):
    success, message = add_owner_to_horse(horse_name, person_name)
    await ctx.send(message)


@bot.command()
@is_admin()
async def removeowner(ctx, horse_name, *, person_name):
    success, message = remove_owner_from_horse(horse_name, person_name)
    await ctx.send(message)


@bot.command()
@is_admin()
async def addleaser(ctx, horse_name, *, person_name):
    success, message = add_leaser_to_horse(horse_name, person_name)
    await ctx.send(message)


@bot.command()
@is_admin()
async def removeleaser(ctx, horse_name, *, person_name):
    success, message = remove_leaser_from_horse(horse_name, person_name)
    await ctx.send(message)


@bot.command()
@is_admin()
async def removehorse(ctx, *, name):
    deleted_count = delete_horse_from_db(name)

    if deleted_count == 0:
        await ctx.send("Horse not found.")
    else:
        await ctx.send(f"{name} was removed.")


@bot.command()
@is_admin()
async def sethorsephoto(ctx, horse_name):
    horse_data = get_horse_from_db(horse_name)

    if not horse_data:
        await ctx.send("Horse not found.")
        return

    if not ctx.message.attachments:
        await ctx.send("Please attach an image to the same message as the command.")
        return

    attachment = ctx.message.attachments[0]

    if not attachment.content_type or not attachment.content_type.startswith("image/"):
        await ctx.send("That attachment is not an image.")
        return

    image_url = attachment.url
    success, message = update_horse_field(horse_name, "image_url", image_url)

    if success:
        await ctx.send(f"Photo added for {horse_name}.")
    else:
        await ctx.send(message)


@bot.command()
@is_admin()
async def removehorsephoto(ctx, *, horse_name):
    horse_data = get_horse_from_db(horse_name)

    if not horse_data:
        await ctx.send("Horse not found.")
        return

    success, message = update_horse_field(horse_name, "image_url", None)

    if success:
        await ctx.send(f"Photo removed for {horse_name}.")
    else:
        await ctx.send(message)


# -----------------------------
# ADMIN COMMANDS - UPDATES
# -----------------------------
@bot.command()
@is_admin()
async def stableupdate(ctx, *, message):
    await send_update_message(f"📣 Stable update: {message}")
    await ctx.send("Update sent.")


@bot.command()
@is_admin()
async def feedall(ctx):
    await send_update_message("🌾 Stable update: All horses have been fed.")
    await ctx.send("Feeding update sent.")


@bot.command()
@is_admin()
async def waterall(ctx):
    await send_update_message("💧 Stable update: All horses have fresh water.")
    await ctx.send("Watering update sent.")


@bot.command()
@is_admin()
async def turnoutall(ctx):
    await send_update_message("🌿 Stable update: All horses have been turned out.")
    await ctx.send("Turnout update sent.")


@bot.command()
@is_admin()
async def stallsdone(ctx):
    await send_update_message("🧹 Stable update: All stalls have been cleaned.")
    await ctx.send("Stall cleaning update sent.")


@bot.command()
@is_admin()
async def addupdatemessage(ctx, *, message):
    add_random_update_message(message)
    await ctx.send("Random update message added.")


@bot.command()
@is_admin()
async def listupdatemessages(ctx):
    rows = get_all_random_update_messages()
    if not rows:
        await ctx.send("No random update messages saved.")
        return

    text = "\n".join([f"{msg_id}: {msg}" for msg_id, msg in rows])

    if len(text) > 1900:
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        for chunk in chunks:
            await ctx.send(f"```{chunk}```")
    else:
        await ctx.send(f"```{text}```")


@bot.command()
@is_admin()
async def removeupdatemessage(ctx, message_id: int):
    deleted = delete_random_update_message(message_id)
    if deleted:
        await ctx.send("Random update message removed.")
    else:
        await ctx.send("Message ID not found.")


# -----------------------------
# RUN BOT
# -----------------------------
bot.run(TOKEN)