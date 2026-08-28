import os
import io
import asyncio
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template_string
import discord
from discord.ext import commands

# JST（日本時間）の定義
JST = timezone(timedelta(hours=+9))
post_count = 0

app = Flask(__name__)

TOKEN = os.environ.get("DISCORD_TOKEN")
BOARD_CHANNEL_ID = int(os.environ.get("BOARD_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# 1. Webフォーム (背景真っ黒 & 入力枠拡大)
# ==========================================
HTML_FORM = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>掲示板 投稿</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #000000;
            color: #ffffff;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 90vh;
        }
        .container {
            width: 100%;
            max-width: 480px;
            background: #111111;
            padding: 24px;
            border-radius: 12px;
            border: 1px solid #222222;
            box-shadow: 0 8px 24px rgba(0,0,0,0.8);
        }
        h2 { font-size: 20px; margin-top: 0; color: #fff; border-bottom: 1px solid #333; padding-bottom: 10px; }
        label { font-size: 13px; font-weight: bold; color: #aaa; display: block; margin-top: 18px; }
        textarea {
            width: 100%;
            height: 200px;
            background: #1a1a1a;
            border: 1px solid #333;
            border-radius: 6px;
            color: #fff;
            padding: 12px;
            box-sizing: border-box;
            resize: vertical;
            font-size: 15px;
            margin-top: 8px;
            line-height: 1.5;
        }
        textarea:focus { outline: none; border-color: #5865f2; }
        input[type="file"] {
            margin-top: 8px; color: #aaa; font-size: 14px; width: 100%;
        }
        .submit-btn {
            width: 100%; background-color: #5865f2; color: white; border: none;
            padding: 14px; border-radius: 6px; font-weight: bold; font-size: 16px;
            margin-top: 24px; cursor: pointer; transition: 0.2s;
        }
        .submit-btn:hover { background-color: #4752c4; }
    </style>
</head>
<body>
    <div class="container">
        <h2>📝 {{ type_str }}投稿 {{ target_str }}</h2>
        <form action="/submit" method="post" enctype="multipart/form-data">
            <input type="hidden" name="is_anon" value="{{ is_anon }}">
            <input type="hidden" name="reply_target" value="{{ reply_target }}">

            <label>メッセージ本文</label>
            <textarea name="content" placeholder="ここにメッセージを入力してください..." required></textarea>

            <label>画像添付（任意）</label>
            <input type="file" name="image" accept="image/*">

            <button type="submit" class="submit-btn">送信する</button>
        </form>
    </div>
</body>
</html>
"""

HTML_SUCCESS = """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>送信完了</title>
    <style>
        body {
            background-color: #000000; color: #23a55a; font-family: sans-serif;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 100vh; margin: 0; text-align: center;
        }
        h2 { margin-bottom: 10px; font-size: 24px; }
        p { color: #888; font-size: 14px; }
    </style>
</head>
<body>
    <h2>投稿完了</h2>
    <p>この画面を閉じてDiscordに戻ってください。</p>
</body>
</html>
"""

# ==========================================
# 2. Flask ルーティング設定
# ==========================================
@app.route('/')
def home():
    return "Bot is running!"

@app.route('/upload')
def upload_page():
    is_anon = request.args.get('is_anon', 'true') == 'true'
    reply_target = request.args.get('reply_target', '')

    type_str = "匿名" if is_anon else "名前表示"
    target_str = f"({reply_target}宛て)" if reply_target else ""

    return render_template_string(
        HTML_FORM,
        is_anon=is_anon,
        reply_target=reply_target,
        type_str=type_str,
        target_str=target_str
    )

@app.route('/submit', methods=['POST'])
def submit_post():
    is_anon = request.form.get('is_anon') == 'True'
    reply_target = request.form.get('reply_target')
    content = request.form.get('content')
    
    image_file = request.files.get('image')
    image_bytes = None
    filename = None

    if image_file and image_file.filename != '':
        image_bytes = image_file.read()
        filename = image_file.filename

    asyncio.run_coroutine_threadsafe(
        process_web_post(
            is_anon=is_anon,
            reply_target=reply_target,
            content=content,
            image_bytes=image_bytes,
            filename=filename
        ),
        bot.loop
    )

    return render_template_string(HTML_SUCCESS)

async def process_web_post(is_anon, reply_target, content, image_bytes, filename):
    global post_count
    post_count += 1

    board_channel = bot.get_channel(BOARD_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if not board_channel:
        print("エラー: BOARD_CHANNEL_ID が不正です")
        return

    now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    body_text = content
    if reply_target:
        body_text = f"> **{reply_target} への返信**\n" + body_text

    display_author = "匿名"
    embed = discord.Embed(description=body_text, color=0x000000)
    header_text = f"#{post_count} | {display_author} | {now_jst}"

    embed.set_author(name=header_text)

    file_to_send = None
    if image_bytes and filename:
        file_to_send = discord.File(fp=io.BytesIO(image_bytes), filename=filename)

    post_view = PostItemView(post_num=post_count)
    
    try:
        if file_to_send:
            sent_msg = await board_channel.send(embed=embed, file=file_to_send, view=post_view)
        else:
            sent_msg = await board_channel.send(embed=embed, view=post_view)

        if log_channel:
            log_embed = discord.Embed(
                title=f"【投稿ログ #{post_count}】",
                description=body_text,
                color=0x2b2d31
            )
            log_embed.add_field(name="表示タイプ", value="匿名" if is_anon else "名前表示")
            log_embed.add_field(name="投稿時間", value=now_jst)
            log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
            await log_channel.send(embed=log_embed)
    except Exception as e:
        print(f"投稿送信時エラー: {e}")

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# 3. Direct Link Buttons (直飛び設定)
# ==========================================
def get_render_url():
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        url = "https://" + os.environ.get("RENDER_SERVICE_NAME", "app") + ".onrender.com"
    return url

class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        base_url = get_render_url()
        
        # リンクボタンとして直接追加（押した瞬間にブラウザが開く）
        self.add_item(discord.ui.Button(
            label="匿名返信",
            style=discord.ButtonStyle.link,
            url=f"{base_url}/upload?is_anon=true&reply_target=%23{post_num}"
        ))
        self.add_item(discord.ui.Button(
            label="名前返信",
            style=discord.ButtonStyle.link,
            url=f"{base_url}/upload?is_anon=false&reply_target=%23{post_num}"
        ))

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        base_url = get_render_url()

        # パネルのボタンも直接リンク化
        self.add_item(discord.ui.Button(
            label="匿名で投稿",
            style=discord.ButtonStyle.link,
            url=f"{base_url}/upload?is_anon=true"
        ))
        self.add_item(discord.ui.Button(
            label="名前表示で投稿",
            style=discord.ButtonStyle.link,
            url=f"{base_url}/upload?is_anon=false"
        ))

    @discord.ui.button(label="通報する", style=discord.ButtonStyle.danger, custom_id="btn_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

class ReportModal(discord.ui.Modal):
    def __init__(self, target_post: str = None):
        title_text = f'🚨 通報 ({target_post})' if target_post else '🚨 管理者への通報'
        super().__init__(title=title_text)

        default_reason = f"{target_post} について: " if target_post else ""
        
        self.report_reason = discord.ui.TextInput(
            label='通報理由',
            style=discord.TextStyle.paragraph,
            placeholder='理由を入力してください...',
            default=default_reason,
            required=True,
            max_length=1000,
        )
        self.add_item(self.report_reason)

    async def on_submit(self, interaction: discord.Interaction):
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            await interaction.response.send_message("エラー: LOG_CHANNEL_IDが設定されていません。", ephemeral=True)
            return

        now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")
        report_embed = discord.Embed(title="🚨【通報】", description=self.report_reason.value, color=0xff0000)
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.id})")
        report_embed.add_field(name="通報日時", value=now_jst)
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を送信しました。", ephemeral=True)

# ==========================================
# イベント・コマンド
# ==========================================
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.add_view(PanelView())
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="setup_panel", description="掲示板パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板",
        description="下のボタンを押すと投稿画面が開きます。\n画像の添付も可能です。",
        color=0x000000
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
