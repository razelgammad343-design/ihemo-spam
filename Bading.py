import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
from flask import Flask
from threading import Thread
import time
import sqlite3
import asyncio

# =========================================================
# FLASK SERVER FOR RENDER
# =========================================================
app = Flask(__name__)

@app.route("/")
def home():
    return "Spam Bot is online!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    thread = Thread(target=run_flask)
    thread.daemon = True
    thread.start()

# =========================================================
# SPAM CONFIGURATION
# =========================================================
OWNER_USER_IDS = {
    923096413934616596,
    760023911764197396,
}

SPAM_CHANNEL_ID = 1548670456385765426
SPAM_DATABASE_FILE = "spam_bot.db"

TWO_HOURS = 2 * 60 * 60 + 10 * 60  # 2 hours 10 minutes
SIX_HOURS = 6 * 60 * 60

SPAM_SHORT_LABEL = "2H 10M"

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix=None,
    intents=intents
)

spam_lock = asyncio.Lock()

# =========================================================
# SPAM DATABASE
# =========================================================
def get_spam_db():
    conn = sqlite3.connect(
        SPAM_DATABASE_FILE,
        timeout=30
    )
    conn.row_factory = sqlite3.Row
    return conn

def initialize_spam_database():
    conn = get_spam_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spam_worlds (
            world TEXT PRIMARY KEY,
            end_time_2h REAL,
            end_time_6h REAL,
            added_by INTEGER NOT NULL
        )
    """)

    # Add timer columns when using an older spam database.
    cursor.execute("PRAGMA table_info(spam_worlds)")
    columns = {row[1] for row in cursor.fetchall()}

    if "end_time_2h" not in columns:
        cursor.execute("""
            ALTER TABLE spam_worlds
            ADD COLUMN end_time_2h REAL
        """)

    if "end_time_6h" not in columns:
        cursor.execute("""
            ALTER TABLE spam_worlds
            ADD COLUMN end_time_6h REAL
        """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spam_panel (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER,
            panel_message_id INTEGER
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO spam_panel
        (id, owner_id, panel_message_id)
        VALUES (1, NULL, NULL)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spam_active_ping (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            message_id INTEGER
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO spam_active_ping
        (id, message_id)
        VALUES (1, NULL)
    """)

    conn.commit()
    conn.close()
    print("✅ Spam database initialized.")

def normalize_world(world):
    return world.strip().upper()
def add_spam_world(
    world,
    user_id
):
    world = normalize_world(world)
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO spam_worlds
        (
            world,
            end_time_2h,
            end_time_6h,
            added_by
        )
        VALUES (
            ?,
            NULL,
            NULL,
            ?
        )
    """, (
        world,
        user_id
    ))
    conn.commit()
    conn.close()
def remove_spam_world(world):
    world = normalize_world(world)
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM spam_worlds
        WHERE world = ?
    """, (
        world,
    ))
    removed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return removed
def get_spam_world(world):
    world = normalize_world(world)
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM spam_worlds
        WHERE world = ?
    """, (
        world,
    ))
    row = cursor.fetchone()
    conn.close()
    return row
def get_all_spam_worlds():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM spam_worlds
        ORDER BY world ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows
def start_spam_timer(
    world,
    duration_hours
):
    world = normalize_world(world)
    if duration_hours == 2:
        end_time = (
            time.time()
            + TWO_HOURS
        )
    elif duration_hours == 6:
        end_time = (
            time.time()
            + SIX_HOURS
        )
    else:
        return
    conn = get_spam_db()
    cursor = conn.cursor()
    if duration_hours == 2:
        cursor.execute("""
            UPDATE spam_worlds
            SET end_time_2h = ?
            WHERE world = ?
        """, (
            end_time,
            world
        ))
    elif duration_hours == 6:
        cursor.execute("""
            UPDATE spam_worlds
            SET end_time_6h = ?
            WHERE world = ?
        """, (
            end_time,
            world
        ))
    conn.commit()
    conn.close()
def clear_spam_timer(
    world,
    duration_hours
):
    world = normalize_world(world)
    conn = get_spam_db()
    cursor = conn.cursor()
    if duration_hours == 2:
        cursor.execute("""
            UPDATE spam_worlds
            SET end_time_2h = NULL
            WHERE world = ?
        """, (
            world,
        ))
    elif duration_hours == 6:
        cursor.execute("""
            UPDATE spam_worlds
            SET end_time_6h = NULL
            WHERE world = ?
        """, (
            world,
        ))
    conn.commit()
    conn.close()
def reset_all_spam_timers():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE spam_worlds
        SET
            end_time_2h = NULL,
            end_time_6h = NULL
    """)
    conn.commit()
    conn.close()
def get_spam_active_ping_id():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT message_id
        FROM spam_active_ping
        WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return row[0]

def set_spam_active_ping_id(message_id):
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE spam_active_ping
        SET message_id = ?
        WHERE id = 1
    """, (message_id,))
    conn.commit()
    conn.close()

def clear_spam_active_ping_id():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE spam_active_ping
        SET message_id = NULL
        WHERE id = 1
    """)
    conn.commit()
    conn.close()

async def delete_old_spam_ping(channel):
    old_message_id = get_spam_active_ping_id()
    if not old_message_id:
        return
    try:
        old_message = await channel.fetch_message(old_message_id)
        await old_message.delete()
        print(f"🗑️ Deleted previous Spam ready ping ({old_message_id})")
    except discord.NotFound:
        print("ℹ️ Previous Spam ready ping was already deleted.")
    except discord.Forbidden:
        print("❌ Bot does not have permission to delete the previous Spam ping.")
    except Exception as e:
        print(f"❌ Error deleting old Spam ping: {e}")
    finally:
        clear_spam_active_ping_id()

async def send_spam_ready_ping(channel, world, owner_id, duration):
    await delete_old_spam_ping(channel)
    label = SPAM_SHORT_LABEL if duration == 2 else "6 HOURS"
    try:
        message = await channel.send(
            f"🔔 <@{owner_id}> "
            f"**{world}** — "
            f"**{label}** timer is ready!"
        )
        set_spam_active_ping_id(message.id)
        print(f"🔔 New Spam ready ping sent for {world} ({label})")
        print(f"🆔 Spam ping message ID: {message.id}")
    except Exception as e:
        print(f"❌ Error sending Spam ready ping: {e}")

def get_spam_panel():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT *
        FROM spam_panel
        WHERE id = 1
    """)
    row = cursor.fetchone()
    conn.close()
    return row
def save_spam_panel(
    owner_id,
    message_id
):
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE spam_panel
        SET
            owner_id = ?,
            panel_message_id = ?
        WHERE id = 1
    """, (
        owner_id,
        message_id
    ))
    conn.commit()
    conn.close()
def clear_spam_panel_message():
    conn = get_spam_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE spam_panel
        SET panel_message_id = NULL
        WHERE id = 1
    """)
    conn.commit()
    conn.close()
def is_allowed_spam_channel(channel):
    if channel is None:
        return False
    return channel.id == SPAM_CHANNEL_ID
def format_spam_countdown(end_time):
    if end_time is None:
        return "🟢 **READY**"
    remaining = end_time - time.time()
    if remaining <= 0:
        return "🟢 **READY**"
    # Exactly the same countdown style used by the Farm/Tackle system.
    return f"⏳ `{format_time(remaining)}`"
def spam_embed():
    embed = discord.Embed(
        title="📢 SPAM TIMER",
        description=(
            "Select a world below to manage its timers.\n\n"
            "🌎 **World Owner**\n"
            "The user who added the world controls its timers.\n\n"
            "⏱️ **Independent Timers**\n"
            "The 2H 10M and 6-hour timers can run "
            "at the same time."
        ),
        color=discord.Color.blurple()
    )

    worlds = get_all_spam_worlds()
    if not worlds:
        embed.add_field(
            name="🌎 WORLDS",
            value="No worlds have been added yet.",
            inline=False
        )
        embed.set_footer(
            text="Use /spamadd to add a world"
        )
        return embed

    description = ""
    for row in worlds:
        world = row["world"]
        owner = f"<@{row['added_by']}>"
        description += (
            f"🌎 **{world}** — {owner}\n"
            f"⏱️ **2H 10M** → {format_spam_countdown(row['end_time_2h'])}\n"
            f"⏱️ **6H** → {format_spam_countdown(row['end_time_6h'])}\n\n"
        )

    description = description.rstrip()
    if len(description) > 4096:
        description = description[:4090] + "..."

    embed.description = description
    embed.set_footer(
        text="Use /spamadd to add a world"
    )
    return embed

class TimerChoiceView(
    discord.ui.View
):
    def __init__(
        self,
        world,
        owner_id
    ):
        super().__init__(
            timeout=300
        )
        self.world = world
        self.owner_id = owner_id
    async def interaction_check(
        self,
        interaction
    ):
        if interaction.channel_id != SPAM_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ You cannot use this panel here.",
                ephemeral=True
            )
            return False
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                (
                    "❌ Only the person who added "
                    "this world can start its timers."
                ),
                ephemeral=True
            )
            return False
        return True
    @discord.ui.button(
        label="2H 10M",
        emoji="⏱️",
        style=discord.ButtonStyle.success
    )
    async def two_hours(
        self,
        interaction,
        button
    ):
        await start_spam_world_timer(
            interaction,
            self.world,
            self.owner_id,
            2
        )
    @discord.ui.button(
        label="6 HOURS",
        emoji="⏱️",
        style=discord.ButtonStyle.primary
    )
    async def six_hours(
        self,
        interaction,
        button
    ):
        await start_spam_world_timer(
            interaction,
            self.world,
            self.owner_id,
            6
        )
async def start_spam_world_timer(
    interaction,
    world,
    owner_id,
    duration_hours
):
    world = normalize_world(world)
    try:
        await interaction.response.defer(
            ephemeral=True
        )
    except discord.InteractionResponded:
        pass
    row = get_spam_world(world)
    if row is None:
        await interaction.edit_original_response(
            content="❌ This world no longer exists."
        )
        return
    if row["added_by"] != interaction.user.id:
        await interaction.edit_original_response(
            content=(
                "❌ Only the person who added "
                "this world can start its timer."
            )
        )
        return
    if owner_id != interaction.user.id:
        await interaction.edit_original_response(
            content=(
                "❌ You are not the owner "
                "of this world."
            )
        )
        return
    if duration_hours == 2:
        current_end = row["end_time_2h"]
    else:
        current_end = row["end_time_6h"]
    if current_end is not None:
        remaining = (
            current_end
            - time.time()
        )
        if remaining > 0:
            await interaction.edit_original_response(
                content=(
                    f"⏳ **{world} — "
                    f"{SPAM_SHORT_LABEL if duration_hours == 2 else '6 HOURS'}** "
                    "is already running.\n\n"
                    f"Time remaining: "
                    f"**{format_time(remaining)}**\n\n"
                    "You can still use the other timer."
                )
            )
            return
        clear_spam_timer(
            world,
            duration_hours
        )
    start_spam_timer(
        world,
        duration_hours
    )
    await interaction.edit_original_response(
        content=(
            f"✅ **{world}** started for "
            f"**{SPAM_SHORT_LABEL if duration_hours == 2 else '6 hours'}**.\n\n"
            "⏱️ This timer is running independently.\n"
            "You can still start the other timer."
        )
    )
    await update_spam_panel()
class WorldSelect(
    discord.ui.Select
):
    def __init__(self):
        worlds = get_all_spam_worlds()
        options = []
        for row in worlds[:25]:
            options.append(
                discord.SelectOption(
                    label=row["world"][:100],
                    description=(
                        f"Owner: User "
                        f"{row['added_by']}"
                    )[:100],
                    value=row["world"]
                )
            )
        if not options:
            options.append(
                discord.SelectOption(
                    label="No worlds available",
                    description=(
                        "Use /spamadd first."
                    ),
                    value="__none__"
                )
            )
        super().__init__(
            placeholder="🌎 Select a world...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="spam_world_select"
        )
    async def callback(
        self,
        interaction
    ):
        if interaction.channel_id != SPAM_CHANNEL_ID:
            await interaction.response.send_message(
                "❌ You cannot use this panel here.",
                ephemeral=True
            )
            return
        await interaction.response.defer(
            ephemeral=True
        )
        world = normalize_world(
            self.values[0]
        )
        if world == "__NONE__":
            await interaction.edit_original_response(
                content=(
                    "❌ No worlds have been added yet."
                )
            )
            return
        row = get_spam_world(world)
        if row is None:
            await interaction.edit_original_response(
                content=(
                    "❌ This world no longer exists."
                )
            )
            return
        owner_id = row["added_by"]
        if interaction.user.id == owner_id:
            content = (
                f"🌎 **{world}**\n\n"
                "Choose a timer.\n\n"
                f"⏱️ **{SPAM_SHORT_LABEL}** and **6 HOURS** "
                "are independent.\n\n"
                "You can run both at the same time."
            )
        else:
            content = (
                f"🌎 **{world}**\n\n"
                f"👤 Owner: <@{owner_id}>\n\n"
                "You can view the timer options, "
                "but only the owner can start them."
            )
        await interaction.edit_original_response(
            content=content,
            view=TimerChoiceView(
                world,
                owner_id
            )
        )
class SpamView(
    discord.ui.View
):
    def __init__(self):
        super().__init__(
            timeout=None
        )
        self.add_item(
            WorldSelect()
        )
async def update_spam_panel():
    panel = get_spam_panel()
    if panel is None:
        return
    message_id = panel[
        "panel_message_id"
    ]
    if not message_id:
        return
    channel = bot.get_channel(
        SPAM_CHANNEL_ID
    )
    if channel is None:
        try:
            channel = await bot.fetch_channel(
                SPAM_CHANNEL_ID
            )
        except Exception as e:
            print(
                f"❌ Error fetching Spam channel: {e}"
            )
            return
    try:
        message = await channel.fetch_message(
            message_id
        )
    except discord.NotFound:
        clear_spam_panel_message()
        return
    except Exception as e:
        print(
            f"❌ Error fetching Spam panel: {e}"
        )
        return
    try:
        await message.edit(
            embed=spam_embed(),
            view=SpamView()
        )
    except Exception as e:
        print(
            f"❌ Error updating Spam panel: {e}"
        )
@bot.tree.command(
    name="spamsetup",
    description="Create or update the Spam Timer panel"
)
async def spamsetup(
    interaction: discord.Interaction
):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message(
            "❌ You are not allowed to use this command.",
            ephemeral=True
        )
        return
    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ Use `/spamsetup` in the configured Spam channel.",
            ephemeral=True
        )
        return
    await interaction.response.defer(
        ephemeral=True
    )
    panel = get_spam_panel()
    message_id = panel[
        "panel_message_id"
    ]
    if message_id:
        try:
            message = await interaction.channel.fetch_message(
                message_id
            )
            await message.edit(
                embed=spam_embed(),
                view=SpamView()
            )
            await interaction.edit_original_response(
                content="✅ Existing Spam panel updated."
            )
            return
        except discord.NotFound:
            clear_spam_panel_message()
        except Exception as e:
            print(
                f"❌ Panel error: {e}"
            )
    message = await interaction.channel.send(
        embed=spam_embed(),
        view=SpamView()
    )
    save_spam_panel(
        interaction.user.id,
        message.id
    )
    await interaction.edit_original_response(
        content="✅ Spam panel created."
    )
@bot.tree.command(
    name="spamadd",
    description="Add a Spam world"
)
@app_commands.describe(
    world="The world name to add"
)
async def spamadd(
    interaction: discord.Interaction,
    world: str
):
    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ Use `/spamadd` in the configured Spam channel.",
            ephemeral=True
        )
        return
    world = normalize_world(world)
    if len(world) > 100:
        await interaction.response.send_message(
            "❌ World name is too long.",
            ephemeral=True
        )
        return
    existing = get_spam_world(world)
    if existing:
        if existing["added_by"] == interaction.user.id:
            await interaction.response.send_message(
                f"❌ You already added **{world}**.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"❌ **{world}** was already added by another user.",
                ephemeral=True
            )
        return
    add_spam_world(
        world,
        interaction.user.id
    )
    await interaction.response.send_message(
        f"✅ **{world}** has been added.\n"
        f"👤 Owner: {interaction.user.mention}\n\n"
        "You can now use both the 2H 10M and 6-hour timers.",
        ephemeral=True
    )
    await update_spam_panel()
@bot.tree.command(
    name="spamremove",
    description="Remove a Spam world"
)
@app_commands.describe(
    world="The world to remove"
)
async def spamremove(
    interaction: discord.Interaction,
    world: str
):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message(
            "❌ Only the bot owner can remove worlds.",
            ephemeral=True
        )
        return
    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ Use `/spamremove` in the configured Spam channel.",
            ephemeral=True
        )
        return
    world = normalize_world(world)
    if not remove_spam_world(world):
        await interaction.response.send_message(
            f"❌ **{world}** does not exist.",
            ephemeral=True
        )
        return
    await interaction.response.send_message(
        f"✅ **{world}** has been removed.",
        ephemeral=True
    )
    await update_spam_panel()
@bot.tree.command(
    name="spamreset",
    description="Reset a world's timers"
)
@app_commands.describe(
    world="World name, or 'all' for every world"
)
async def spamreset(
    interaction: discord.Interaction,
    world: str
):
    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ Use `/spamreset` in the configured Spam channel.",
            ephemeral=True
        )
        return
    world = normalize_world(world)
    if world == "ALL":
        if interaction.user.id not in OWNER_USER_IDS:
            await interaction.response.send_message(
                "❌ Only the bot owner can reset all worlds.",
                ephemeral=True
            )
            return
        reset_all_spam_timers()
        await interaction.response.send_message(
            "✅ Both timers for all worlds have been reset.",
            ephemeral=True
        )
        await update_spam_panel()
        return
    row = get_spam_world(world)
    if row is None:
        await interaction.response.send_message(
            f"❌ **{world}** does not exist.",
            ephemeral=True
        )
        return
    world_owner_id = row["added_by"]
    if interaction.user.id in OWNER_USER_IDS:
        allowed = True
    elif interaction.user.id == world_owner_id:
        allowed = True
    else:
        allowed = False
    if not allowed:
        await interaction.response.send_message(
            "❌ You can only reset a world that you added.",
            ephemeral=True
        )
        return
    clear_spam_timer(
        world,
        2
    )
    clear_spam_timer(
        world,
        6
    )
    await interaction.response.send_message(
        f"✅ Both timers for **{world}** have been reset.",
        ephemeral=True
    )
    await update_spam_panel()
@bot.tree.command(
    name="spamstatus",
    description="Show Spam Timer status"
)
async def spamstatus(
    interaction: discord.Interaction
):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message(
            "❌ Only the bot owner can use this command.",
            ephemeral=True
        )
        return
    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ Use `/spamstatus` in the configured Spam channel.",
            ephemeral=True
        )
        return
    worlds = get_all_spam_worlds()
    now = time.time()
    total = len(worlds)
    running_2h = 0
    running_6h = 0
    lines = []
    for row in worlds:
        world = row["world"]
        end_2h = row["end_time_2h"]
        if end_2h is not None:
            remaining_2h = (
                end_2h - now
            )
            if remaining_2h > 0:
                running_2h += 1
                lines.append(
                    f"⏱️ **{world}** — "
                    f"{SPAM_SHORT_LABEL}: {format_time(remaining_2h)}"
                )
        end_6h = row["end_time_6h"]
        if end_6h is not None:
            remaining_6h = (
                end_6h - now
            )
            if remaining_6h > 0:
                running_6h += 1
                lines.append(
                    f"⏱️ **{world}** — "
                    f"6H: {format_time(remaining_6h)}"
                )
    embed = discord.Embed(
        title="📊 SPAM STATUS",
        color=discord.Color.blurple()
    )
    embed.add_field(
        name="🌎 Worlds",
        value=str(total),
        inline=True
    )
    embed.add_field(
        name=f"⏱️ {SPAM_SHORT_LABEL} Running",
        value=str(running_2h),
        inline=True
    )
    embed.add_field(
        name="⏱️ 6H Running",
        value=str(running_6h),
        inline=True
    )
    if lines:
        text = "\n".join(lines)
        if len(text) > 1024:
            text = text[:1020] + "..."
        embed.add_field(
            name="Currently Running",
            value=text,
            inline=False
        )
    else:
        embed.add_field(
            name="Currently Running",
            value="No timers are running.",
            inline=False
        )
    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )
@bot.tree.command(
    name="spamtimer",
    description="Set the current timer for a Spam world."
)
@app_commands.describe(
    world="The Spam world",
    hours="How many hours the current timer should have"
)
async def spamtimer(
    interaction: discord.Interaction,
    world: str,
    hours: float
):
    if interaction.user.id not in OWNER_USER_IDS:
        await interaction.response.send_message(
            "❌ You don't have permission to use this command.",
            ephemeral=True
        )
        return

    if not is_allowed_spam_channel(
        interaction.channel
    ):
        await interaction.response.send_message(
            "❌ This command can only be used in the configured Spam channel.",
            ephemeral=True
        )
        return

    world = normalize_world(world)

    if hours <= 0:
        await interaction.response.send_message(
            "❌ The number of hours must be greater than 0.",
            ephemeral=True
        )
        return

    row = get_spam_world(world)

    if row is None:
        await interaction.response.send_message(
            f"❌ **{world}** does not exist.",
            ephemeral=True
        )
        return

    seconds = int(hours * 60 * 60)
    end_time = time.time() + seconds

    conn = sqlite3.connect(
        SPAM_DATABASE_FILE
    )
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE spam_worlds
        SET end_time_2h = ?,
            end_time_6h = NULL
        WHERE world = ?
        """,
        (
            end_time,
            world
        )
    )

    conn.commit()
    conn.close()

    await update_spam_panel()

    await interaction.response.send_message(
        f"✅ **{world}** timer set to **{format_time(seconds)}**.\n\n"
        f"⏱️ This only changes the **current cycle**.",
        ephemeral=True
    )

@tasks.loop(seconds=10)
async def spam_timer_loop():
    try:
        worlds = get_all_spam_worlds()
        now = time.time()
        expired = []
        for row in worlds:
            world = row["world"]
            owner_id = row["added_by"]
            end_2h = row["end_time_2h"]
            if (
                end_2h is not None
                and
                end_2h <= now
            ):
                expired.append(
                    (
                        world,
                        owner_id,
                        2
                    )
                )
            end_6h = row["end_time_6h"]
            if (
                end_6h is not None
                and
                end_6h <= now
            ):
                expired.append(
                    (
                        world,
                        owner_id,
                        6
                    )
                )
        for (
            world,
            owner_id,
            duration
        ) in expired:
            clear_spam_timer(
                world,
                duration
            )
            channel = bot.get_channel(
                SPAM_CHANNEL_ID
            )
            if channel is None:
                try:
                    channel = await bot.fetch_channel(
                        SPAM_CHANNEL_ID
                    )
                except Exception as e:
                    print(
                        f"❌ Could not fetch Spam channel: {e}"
                    )
                    continue
            await send_spam_ready_ping(
                channel,
                world,
                owner_id,
                duration
            )
        # Keep the Spam panel countdown updated even when no timer expires.
        # This makes the displayed countdown decrease every loop (10 seconds).
        await update_spam_panel()
    except Exception as e:
        print(
            f"❌ Spam timer loop error: {e}"
        )
@spam_timer_loop.before_loop
async def before_spam_timer_loop():
    await bot.wait_until_ready()

@bot.event
async def on_ready():
    print("===================================")
    print(f"Logged in as {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print("===================================")

    initialize_spam_database()

    if not hasattr(bot, "_spam_view_registered"):
        bot.add_view(SpamView())
        bot._spam_view_registered = True
        print("Persistent Spam panel registered.")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} spam slash commands.")
    except Exception as e:
        print(f"Slash command sync error: {e}")

    # Start the Spam loop only.
    if not spam_timer_loop.is_running():
        spam_timer_loop.start()
        print("Spam timer loop started.")

    await update_spam_panel()

    print("📢 Spam system is running!")
    print("⏱️ Spam: independent 2H 10M / 6H timers")
    print("===================================")

# =========================================================
# RUN
# =========================================================
if __name__ == "__main__":
    token = os.getenv("TOKEN")
    if not token:
        raise RuntimeError("TOKEN environment variable is missing.")
    keep_alive()
    bot.run(token)

