import os
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask

import discord
from discord import app_commands
from discord.ext import commands


# ==========================================
# 基本設定
# ==========================================

JST = timezone(timedelta(hours=9))

post_count = 0

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
    port = int(os.environ.get("PORT", 10000))

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
        self.add_view(PanelView())


bot = CustomBot(
    command_prefix="!",
    intents=intents
)


# ==========================================
# 投稿モーダル
# ==========================================

class TextPostModal(discord.ui.Modal):

    def __init__(
        self,
        is_anonymous: bool,
        reply_target=None
    ):

        self.is_anonymous = is_anonymous
        self.reply_target = reply_target

        if reply_target:
            title = (
                "匿名返信"
                if is_anonymous
                else "非匿名返信"
            )
        else:
            title = (
                "匿名投稿"
                if is_anonymous
                else "非匿名投稿"
            )

        super().__init__(
            title=title
        )

        # 本文
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

        # ファイル
        self.file_upload = discord.ui.FileUpload(
            min_values=0,
            max_values=4,
            required=False
        )

        self.add_item(
            self.file_upload
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

        attachments = list(
            self.file_upload.values
        )

        if not content and not attachments:

            await interaction.response.send_message(
                "❌ 本文または画像・動画を選択してください。",
                ephemeral=True
            )

            return

        await send_board_post(
            interaction=interaction,
            content=content,
            is_anonymous=self.is_anonymous,
            reply_target=self.reply_target,
            attachments=attachments
        )


# ==========================================
# 通報モーダル
# ==========================================

class ReportModal(discord.ui.Modal):

    def __init__(
        self,
        target_post=None
    ):

        self.target_post = target_post

        super().__init__(
            title="🚨 通報"
        )

        self.reason = discord.ui.TextInput(
            label="通報理由",
            style=discord.TextStyle.paragraph,
            placeholder="理由を入力してください...",
            required=True,
            max_length=1000
        )

        self.add_item(
            self.reason
        )


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        log_channel = bot.get_channel(
            LOG_CHANNEL_ID
        )

        if not log_channel:

            await interaction.response.send_message(
                "❌ ログチャンネルが見つかりません。",
                ephemeral=True
            )

            return

        now_jst = datetime.now(
            JST
        ).strftime(
            "%Y/%m/%d %H:%M"
        )

        embed = discord.Embed(
            title="🚨【通報】",
            description=self.reason.value,
            color=0xff0000
        )

        embed.add_field(
            name="通報者",
            value=(
                f"{interaction.user.mention}\n"
                f"名前: {interaction.user.name}\n"
                f"ID: `{interaction.user.id}`"
            ),
            inline=False
        )

        embed.add_field(
            name="日時",
            value=now_jst,
            inline=True
        )

        if self.target_post:

            embed.add_field(
                name="対象投稿",
                value=self.target_post,
                inline=True
            )

        await log_channel.send(
            embed=embed
        )

        await interaction.response.send_message(
            "✅ 通報を送信しました。",
            ephemeral=True
        )


# ==========================================
# メインパネル
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
# 投稿後のボタン
# ==========================================

class PostItemView(discord.ui.View):

    def __init__(
        self,
        post_num: int
    ):

        super().__init__(
            timeout=None
        )

        self.post_num = post_num


    @discord.ui.button(
        label="匿名返信",
        style=discord.ButtonStyle.secondary,
        custom_id="post_reply_anonymous"
    )
    async def reply_anonymous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TextPostModal(
                is_anonymous=True,
                reply_target=f"#{self.post_num}"
            )
        )


    @discord.ui.button(
        label="非匿名返信",
        style=discord.ButtonStyle.secondary,
        custom_id="post_reply_named"
    )
    async def reply_named(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            TextPostModal(
                is_anonymous=False,
                reply_target=f"#{self.post_num}"
            )
        )


    @discord.ui.button(
        label="通報",
        style=discord.ButtonStyle.danger,
        custom_id="post_report"
    )
    async def report(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_modal(
            ReportModal(
                target_post=f"#{self.post_num}"
            )
        )


# ==========================================
# Discordへ投稿
# ==========================================

async def send_board_post(
    interaction: discord.Interaction,
    content: str,
    is_anonymous: bool,
    reply_target=None,
    attachments=None
):

    global post_count

    if attachments is None:
        attachments = []


    board_channel = bot.get_channel(
        BOARD_CHANNEL_ID
    )

    log_channel = bot.get_channel(
        LOG_CHANNEL_ID
    )

    if not board_channel:

        await interaction.response.send_message(
            "❌ 掲示板チャンネルが見つかりません。",
            ephemeral=True
        )

        return


    post_count += 1


    now_jst = datetime.now(
        JST
    ).strftime(
        "%Y/%m/%d %H:%M"
    )


    if is_anonymous:

        author_name = "匿名"

    else:

        author_name = (
            interaction.user.display_name
        )


    if reply_target:

        body = (
            f"> **{reply_target} への返信**\n"
            f"{content}"
        )

    else:

        body = content


    if not body:

        body = "（本文なし）"


    embed = discord.Embed(
        description=body,
        color=0x000000
    )


    header = (
        f"#{post_count} | "
        f"{author_name} | "
        f"{now_jst}"
    )


    if is_anonymous:

        embed.set_author(
            name=header
        )

    else:

        embed.set_author(
            name=header,
            icon_url=interaction.user.display_avatar.url
        )


    # ======================================
    # 添付ファイル
    # ======================================

    discord_files = []


    for attachment in attachments:

        try:

            discord_file = await attachment.to_file()

            discord_files.append(
                discord_file
            )

        except Exception as e:

            print(
                "ファイル変換エラー:",
                repr(e)
            )


    # ======================================
    # 投稿
    # ======================================

    if discord_files:

        sent_message = await board_channel.send(
            embed=embed,
            files=discord_files,
            view=PostItemView(
                post_num=post_count
            )
        )

    else:

        sent_message = await board_channel.send(
            embed=embed,
            view=PostItemView(
                post_num=post_count
            )
        )


    # ======================================
    # ログ
    # ======================================

    if log_channel:

        log_embed = discord.Embed(
            title=f"📋【投稿ログ #{post_count}】",
            description=content or "（本文なし）",
            color=0x2b2d31
        )

        log_embed.add_field(
            name="👤 投稿者（本人）",
            value=(
                f"{interaction.user.mention}\n"
                f"名前: {interaction.user.name}\n"
                f"ID: `{interaction.user.id}`"
            ),
            inline=False
        )

        log_embed.add_field(
            name="👁️ 表示形式",
            value=(
                "匿名"
                if is_anonymous
                else "非匿名"
            ),
            inline=True
        )

        log_embed.add_field(
            name="⏰ 投稿時間",
            value=now_jst,
            inline=True
        )

        if reply_target:

            log_embed.add_field(
                name="💬 返信先",
                value=reply_target,
                inline=True
            )

        if attachments:

            names = "\n".join(
                f"📎 {a.filename}"
                for a in attachments
            )

            log_embed.add_field(
                name="📎 添付ファイル",
                value=names[:1024],
                inline=False
            )

        log_embed.add_field(
            name="🔗 メッセージリンク",
            value=sent_message.jump_url,
            inline=False
        )

        await log_channel.send(
            embed=log_embed
        )


    await interaction.response.send_message(
        f"✅ 投稿しました！ #{post_count}",
        ephemeral=True
    )


# ==========================================
# 掲示板への直接投稿を削除
# ==========================================

@bot.event
async def on_message(
    message: discord.Message
):

    if message.author.bot:
        return


    if message.channel.id == BOARD_CHANNEL_ID:

        try:

            await message.delete()

        except Exception:

            pass

        return


    await bot.process_commands(
        message
    )


# ==========================================
# Bot起動
# ==========================================

@bot.event
async def on_ready():

    print(
        f"Logged in as {bot.user}"
    )

    print(
        "discord.py version:",
        discord.__version__
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
# setup_panel
# ==========================================

@bot.tree.command(
    name="setup_panel",
    description="掲示板パネルを設置します"
)
async def setup_panel(
    interaction: discord.Interaction
):

    embed = discord.Embed(
        title="📝 掲示板",
        description=(
            "匿名または非匿名で投稿できます。\n"
            "下のボタンから投稿してください。"
        ),
        color=0x000000
    )

    await interaction.channel.send(
        embed=embed,
        view=PanelView()
    )

    await interaction.response.send_message(
        "✅ パネルを設置しました。",
        ephemeral=True
    )


# ==========================================
# nuke
# ==========================================

@bot.tree.command(
    name="nuke",
    description="このチャンネルをリセットします"
)
@app_commands.checks.has_permissions(
    administrator=True
)
async def nuke(
    interaction: discord.Interaction
):

    channel = interaction.channel
    position = channel.position

    await interaction.response.send_message(
        "💣 チャンネルをリセットしています...",
        ephemeral=True
    )

    new_channel = await channel.clone(
        reason="Nuke command executed"
    )

    await new_channel.edit(
        position=position
    )

    await channel.delete(
        reason="Nuke command executed"
    )

    await new_channel.send(
        embed=discord.Embed(
            title="💥 Nuke 完了",
            description="このチャンネルの全メッセージが消去されました。",
            color=0xff0000
        )
    )


@nuke.error
async def nuke_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "❌ 管理者権限が必要です。",
                ephemeral=True
            )


# ==========================================
# 起動
# ==========================================

if __name__ == "__main__":

    if not TOKEN:

        print(
            "❌ DISCORD_TOKEN が設定されていません。"
        )

    else:

        keep_alive()

        bot.run(
            TOKEN
        )
