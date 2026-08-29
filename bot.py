import os
import threading
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, jsonify

import discord
from discord import app_commands
from discord.ext import commands


JST = timezone(timedelta(hours=+9))
post_count = 0


# ==========================================
# Webサーバー
# ==========================================

app = Flask(__name__)


@app.route('/')
def home():
    return "Bot is running!"


@app.route('/post')
def post_page():
    return render_template('post.html')


# ==========================================
# Web投稿API
# ==========================================

@app.route('/api/post', methods=['POST'])
def api_post():

    content = request.form.get(
        'content',
        ''
    ).strip()

    anonymous = (
        request.form.get(
            'anonymous',
            'true'
        ) == 'true'
    )

    file = request.files.get(
        'file'
    )


    if not content and not file:

        return jsonify({
            "error": "本文または画像・動画を入力してください。"
        }), 400


    print("================================")
    print("Web投稿を受信しました")
    print("本文:", content)
    print("匿名:", anonymous)


    if file:

        print(
            "ファイル:",
            file.filename
        )


    # Discord Botが起動していなければ投稿できない
    if not bot.is_ready():

        return jsonify({
            "error": "Botが起動していません。"
        }), 503


    # Discordへ投稿する処理
    try:

        future = asyncio.run_coroutine_threadsafe(
            send_web_post(
                content=content,
                anonymous=anonymous,
                file=file
            ),
            bot.loop
        )

        result = future.result(
            timeout=30
        )


        return jsonify({
            "message": "投稿しました！",
            "post_number": result
        })


    except Exception as e:

        print(
            "投稿エラー:",
            repr(e)
        )

        return jsonify({
            "error": "Discordへの投稿に失敗しました。"
        }), 500


# ==========================================
# Web投稿をDiscordへ送る
# ==========================================

async def send_web_post(
    content,
    anonymous,
    file
):

    global post_count


    board_channel = bot.get_channel(
        BOARD_CHANNEL_ID
    )


    if not board_channel:

        raise Exception(
            "BOARD_CHANNEL_IDが見つかりません"
        )


    post_count += 1


    now_jst = datetime.now(
        JST
    ).strftime(
        "%Y/%m/%d %H:%M"
    )


    # ======================================
    # 表示名
    # ======================================

    if anonymous:

        author_name = "匿名"

    else:

        # 現段階ではWebからDiscordユーザーを
        # 特定できないため「Web投稿者」と表示
        author_name = "Web投稿者"


    header_text = (
        f"#{post_count} | "
        f"{author_name} | "
        f"{now_jst}"
    )


    # ======================================
    # Embed
    # ======================================

    embed = discord.Embed(
        description=content
        if content
        else None,
        color=0x000000
    )


    # 匿名はアイコンなし
    if anonymous:

        embed.set_author(
            name=header_text
        )

    else:

        embed.set_author(
            name=header_text
        )


    # ======================================
    # ファイル
    # ======================================

    discord_file = None


    if file:

        file_bytes = file.read()


        # Discordの添付ファイルとして送信
        discord_file = discord.File(
            fp=__import__('io').BytesIO(
                file_bytes
            ),
            filename=file.filename
        )


    # ======================================
    # 投稿
    # ======================================

    if discord_file:

        sent_msg = await board_channel.send(
            embed=embed,
            file=discord_file,
            view=PostItemView(
                post_num=post_count
            )
        )

    else:

        sent_msg = await board_channel.send(
            embed=embed,
            view=PostItemView(
                post_num=post_count
            )
        )


    print(
        "Discordへ投稿しました:",
        sent_msg.jump_url
    )


    return post_count


# ==========================================
# Webサーバー起動
# ==========================================

def run_web():

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    app.run(
        host='0.0.0.0',
        port=port
    )


def keep_alive():

    t = threading.Thread(
        target=run_web
    )

    t.daemon = True
    t.start()


# ==========================================
# UI
# ==========================================

class TextPostModal(discord.ui.Modal):

    def __init__(
        self,
        is_anonymous: bool,
        reply_target: str = None
    ):

        target_str = (
            f"（{reply_target} 宛て）"
            if reply_target
            else ""
        )

        anon_str = (
            "匿名"
            if is_anonymous
            else "非匿名"
        )

        super().__init__(
            title=f'{anon_str}投稿{target_str}'
        )

        self.is_anonymous = is_anonymous
        self.reply_target = reply_target

        self.content_input = discord.ui.TextInput(
            label='メッセージ',
            style=discord.TextStyle.paragraph,
            placeholder='メッセージを入力してください...',
            required=True,
            max_length=2000,
        )

        self.add_item(
            self.content_input
        )


    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        await send_board_post(
            interaction=interaction,
            content=self.content_input.value,
            is_anonymous=self.is_anonymous,
            reply_target=self.reply_target
        )


# ==========================================
# 通報
# ==========================================

class ReportModal(discord.ui.Modal):

    def __init__(
        self,
        target_post: str = None
    ):

        title_text = (
            f'🚨 通報 ({target_post})'
            if target_post
            else '🚨 管理者への通報'
        )

        super().__init__(
            title=title_text
        )

        default_reason = (
            f"{target_post} について: "
            if target_post
            else ""
        )

        self.report_reason = discord.ui.TextInput(
            label='通報理由',
            style=discord.TextStyle.paragraph,
            placeholder='理由を入力してください...',
            default=default_reason,
            required=True,
            max_length=1000,
        )

        self.add_item(
            self.report_reason
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
                "エラー: LOG_CHANNEL_IDが設定されていません。",
                ephemeral=True
            )

            return


        now_jst = datetime.now(
            JST
        ).strftime(
            "%Y/%m/%d %H:%M"
        )


        report_embed = discord.Embed(
            title="🚨【通報】",
            description=self.report_reason.value,
            color=0xff0000
        )


        report_embed.add_field(
            name="通報者",
            value=(
                f"{interaction.user.mention} "
                f"({interaction.user.name} / "
                f"ID: `{interaction.user.id}`)"
            )
        )


        report_embed.add_field(
            name="通報日時",
            value=now_jst
        )


        await log_channel.send(
            embed=report_embed
        )


        await interaction.response.send_message(
            "通報を送信しました。",
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


        # 匿名
        self.add_item(
            discord.ui.Button(
                label="匿名",
                style=discord.ButtonStyle.link,
                url=(
                    "https://a-ai9n.onrender.com"
                    "/post?anonymous=true"
                )
            )
        )


        # 非匿名
        self.add_item(
            discord.ui.Button(
                label="非匿名",
                style=discord.ButtonStyle.link,
                url=(
                    "https://a-ai9n.onrender.com"
                    "/post?anonymous=false"
                )
            )
        )


# ==========================================
# 投稿ボタン
# ==========================================

class PostItemView(discord.ui.View):

    def __init__(
        self,
        post_num: int
    ):

        super().__init__(
            timeout=None
        )


        target_id = f"_{post_num}"
        reply_str = f"#{post_num}"


        # 匿名
        btn_anon = discord.ui.Button(
            label="匿名",
            style=discord.ButtonStyle.primary,
            custom_id=f"btn_anon{target_id}",
            row=0
        )


        async def cb_anon(
            interaction: discord.Interaction
        ):

            await interaction.response.send_modal(
                TextPostModal(
                    is_anonymous=True
                )
            )


        btn_anon.callback = cb_anon

        self.add_item(
            btn_anon
        )


        # 非匿名
        btn_named = discord.ui.Button(
            label="非匿名",
            style=discord.ButtonStyle.primary,
            custom_id=f"btn_named{target_id}",
            row=0
        )


        async def cb_named(
            interaction: discord.Interaction
        ):

            await interaction.response.send_modal(
                TextPostModal(
                    is_anonymous=False
                )
            )


        btn_named.callback = cb_named

        self.add_item(
            btn_named
        )


        # 匿名返信
        btn_reply_anon = discord.ui.Button(
            label="匿名返信",
            style=discord.ButtonStyle.secondary,
            custom_id=f"btn_reply_anon{target_id}",
            row=1
        )


        async def cb_reply_anon(
            interaction: discord.Interaction
        ):

            await interaction.response.send_modal(
                TextPostModal(
                    is_anonymous=True,
                    reply_target=reply_str
                )
            )


        btn_reply_anon.callback = cb_reply_anon

        self.add_item(
            btn_reply_anon
        )


        # 非匿名返信
        btn_reply_named = discord.ui.Button(
            label="非匿名返信",
            style=discord.ButtonStyle.secondary,
            custom_id=f"btn_reply_named{target_id}",
            row=1
        )


        async def cb_reply_named(
            interaction: discord.Interaction
        ):

            await interaction.response.send_modal(
                TextPostModal(
                    is_anonymous=False,
                    reply_target=reply_str
                )
            )


        btn_reply_named.callback = cb_reply_named

        self.add_item(
            btn_reply_named
        )


        # 通報
        btn_report = discord.ui.Button(
            label="通報",
            style=discord.ButtonStyle.danger,
            custom_id=f"btn_report{target_id}",
            row=1
        )


        async def cb_report(
            interaction: discord.Interaction
        ):

            await interaction.response.send_modal(
                ReportModal(
                    target_post=reply_str
                )
            )


        btn_report.callback = cb_report

        self.add_item(
            btn_report
        )


# ==========================================
# Bot
# ==========================================

TOKEN = os.environ.get(
    "DISCORD_TOKEN"
)

BOARD_CHANNEL_ID = 1543316045786386493
LOG_CHANNEL_ID = 1543231098937413642


intents = discord.Intents.default()
intents.message_content = True


class CustomBot(
    commands.Bot
):

    async def setup_hook(self):

        self.add_view(
            PanelView()
        )


bot = CustomBot(
    command_prefix="!",
    intents=intents
)


# ==========================================
# Discord通常投稿
# ==========================================

async def send_board_post(
    interaction: discord.Interaction,
    content: str,
    is_anonymous: bool,
    reply_target: str = None
):

    global post_count


    board_channel = bot.get_channel(
        BOARD_CHANNEL_ID
    )

    log_channel = bot.get_channel(
        LOG_CHANNEL_ID
    )


    if not board_channel:

        if not interaction.response.is_done():

            await interaction.response.send_message(
                "エラー: BOARD_CHANNEL_IDが設定されていません。",
                ephemeral=True
            )

        return


    post_count += 1


    now_jst = datetime.now(
        JST
    ).strftime(
        "%Y/%m/%d %H:%M"
    )


    if reply_target:

        body_text = (
            f"> **{reply_target} への返信**\n"
            f"{content}"
        )

    else:

        body_text = content


    if is_anonymous:

        author_name = "匿名"

    else:

        author_name = (
            interaction.user.display_name
        )


    embed = discord.Embed(
        description=body_text,
        color=0x000000
    )


    header_text = (
        f"#{post_count} | "
        f"{author_name} | "
        f"{now_jst}"
    )


    if is_anonymous:

        embed.set_author(
            name=header_text
        )

    else:

        embed.set_author(
            name=header_text,
            icon_url=interaction.user.display_avatar.url
        )


    sent_msg = await board_channel.send(
        embed=embed,
        view=PostItemView(
            post_num=post_count
        )
    )


    if log_channel:

        log_embed = discord.Embed(
            title=f"📋 【投稿ログ #{post_count}】",
            description=content,
            color=0x2b2d31
        )


        user_info = (
            f"{interaction.user.mention}\n"
            f"**名前:** {interaction.user.name}\n"
            f"**ID:** `{interaction.user.id}`"
        )


        log_embed.add_field(
            name="👤 投稿者（本人）",
            value=user_info,
            inline=True
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


        if reply_target:

            log_embed.add_field(
                name="💬 返信先",
                value=reply_target,
                inline=True
            )


        log_embed.add_field(
            name="⏰ 投稿時間",
            value=now_jst,
            inline=True
        )


        log_embed.add_field(
            name="🔗 メッセージリンク",
            value=sent_msg.jump_url,
            inline=False
        )


        await log_channel.send(
            embed=log_embed
        )


    if not interaction.response.is_done():

        await interaction.response.send_message(
            "投稿が完了しました！",
            ephemeral=True
        )


# ==========================================
# 直接投稿削除
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
# Ready
# ==========================================

@bot.event
async def on_ready():

    print(
        f'Logged in as {bot.user.name}'
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
            "下のボタンを押して投稿してください。"
        ),
        color=0x000000
    )


    await interaction.channel.send(
        embed=embed,
        view=PanelView()
    )


    await interaction.response.send_message(
        "パネルを設置しました。",
        ephemeral=True
    )


# ==========================================
# nuke
# ==========================================

@bot.tree.command(
    name="nuke",
    description="実行したチャンネルのメッセージをすべて消去して再作成します"
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


    embed = discord.Embed(
        title="💥 Nuke 完了",
        description="このチャンネルの全メッセージが消去されました。",
        color=0xff0000
    )


    await new_channel.send(
        embed=embed
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

        await interaction.response.send_message(
            "❌ このコマンドを実行するには「管理者権限」が必要です。",
            ephemeral=True
        )


# ==========================================
# 起動
# ==========================================

if __name__ == "__main__":

    if TOKEN:

        keep_alive()

        bot.run(
            TOKEN
        )

    else:

        print(
            "エラー: DISCORD_TOKEN が設定されていません。"
        )
