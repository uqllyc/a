```python
import os
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands


print("================================")
print("discord.py version:", discord.__version__)
print("================================")


# ==========================================
# 基本設定
# ==========================================

JST = timezone(timedelta(hours=9))

TOKEN = os.environ.get("DISCORD_TOKEN")

BOARD_CHANNEL_ID = 1543324852612505600
LOG_CHANNEL_ID = 1543053996950945844


# ==========================================
# Flask
# ==========================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )


def keep_alive():

    thread = threading.Thread(
        target=run_web,
        daemon=True
    )

    thread.start()


# ==========================================
# Bot
# ==========================================

intents = discord.Intents.default()

intents.message_content = True


class CustomBot(commands.Bot):

    async def setup_hook(self):

        self.add_view(
            PanelView()
        )


bot = CustomBot(
    command_prefix="!",
    intents=intents
)


# ==========================================
# パネル
# ==========================================

class PanelView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )


    @discord.ui.button(
        label="匿名",
        style=discord.ButtonStyle.primary,
        custom_id="panel_anonymous"
    )
    async def anonymous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TextPostModal(
                is_anonymous=True
            )
        )


    @discord.ui.button(
        label="非匿名",
        style=discord.ButtonStyle.primary,
        custom_id="panel_named"
    )
    async def named(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TextPostModal(
                is_anonymous=False
            )
        )


# ==========================================
# 投稿モーダル
# ==========================================

class TextPostModal(discord.ui.Modal):

    def __init__(
        self,
        is_anonymous: bool
    ):

        self.is_anonymous = is_anonymous

        super().__init__(
            title=(
                "匿名投稿"
                if is_anonymous
                else "非匿名投稿"
            )
        )


        self.content_input = discord.ui.TextInput(
            label="メッセージ",
            style=discord.TextStyle.paragraph,
            placeholder="メッセージを入力してください...",
            required=False,
            max_length=2000
        )

        self.add_item(
            self.content_input
        )


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        content = (
            str(
                self.content_input.value
                or ""
            )
            .strip()
        )


        if not content:

            await interaction.response.send_message(
                "本文を入力してください。",
                ephemeral=True
            )

            return


        await interaction.response.send_message(
            "投稿を受け付けました！",
            ephemeral=True
        )


# ==========================================
# Bot起動
# ==========================================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}"
    )


    try:

        synced = await bot.tree.sync()

        print(
            f"Synced {len(synced)} command(s)"
        )

    except Exception as e:

        print(
            f"Failed to sync commands: {e}"
        )


# ==========================================
# 起動
# ==========================================

if __name__ == "__main__":

    if not TOKEN:

        print(
            "ERROR: DISCORD_TOKEN が設定されていません。"
        )

    else:

        keep_alive()

        bot.run(
            TOKEN
        )
```
