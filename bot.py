import os
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, request, render_template_string
import discord
from discord.ext import commands

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
# 1. 投稿用Webフォーム (HTML/CSS)
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
            background-color: #313338;
            color: #dbdee1;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 400px;
            background: #2b2d31;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }
        h2 { font-size: 18px; margin-top: 0; color: #fff; }
        label { font-size: 12px; font-weight: bold; color: #b5bac1; display: block; margin-top: 15px; }
        textarea {
            width: 100%; height: 100px; background: #1e1f22; border: none;
            border-radius: 4px; color: #dbdee1; padding: 10px; box-sizing: border-box;
            resize: vertical; font-size: 14px; margin-top: 5px;
        }
        input[type="file"] {
            margin-top: 5px; color: #b5bac1; font-size: 14px; width: 100%;
        }
        .submit-btn {
            width: 100%; background-color: #5865f2; color: white; border: none;
            padding: 12px; border-radius: 4px; font-weight: bold; font-size: 15px;
            margin-top: 20px; cursor: pointer; transition: 0.2s;
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
            <input type="hidden" name="user_id" value="{{ user_id }}">
            <input type="hidden" name="user_name" value="{{ user_name }}">
            <input type="hidden" name="avatar_url" value="{{ avatar_url }}">

            <label>メッセージ</label>
            <textarea name="content" placeholder="メッセージを入力..." required></textarea>

            <label>画像（任意）</label>
            <input type="file" name="image" accept="image/*">

            <button type="submit" class="submit-btn">投稿する</button>
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
            background-color: #313338; color: #23a55a; font-family: sans-serif;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            height: 100vh; margin: 0; text-align: center;
        }
        h2 { margin-bottom: 10px; }
        p { color: #b5bac1; font-size: 14px; }
    </style>
</head>
<body>
    <h2>✨ 投稿完了しました！</h2>
    <p>画面を閉じてDiscordに戻ってください。</p>
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
    user_id = request.args.get('user_id', '')
    user_name = request.args.get('user_name', '')
    avatar_url = request.args.get('avatar_url', '')

    type_str = "匿名" if is_anon else "名前表示"
    target_str = f"({reply_target}宛て)" if reply_target else ""

    return render_template_string(
        HTML_FORM,
        is_anon=is_anon,
        reply_target=reply_target,
        user_id=user_id,
        user_name=user_name,
        avatar_url=avatar_url,
        type_str=type_str,
        target_str=target_str
    )

@app.route('/submit', methods=['POST'])
def submit_post():
    global post_count
    
    is_anon = request.form.get('is_anon') == 'True'
    reply_target = request.form.get('reply_target')
    user_id = request.form.get('user_id')
    user_name = request.form.get('user_name')
    avatar_url = request.form.get('avatar_url')
    content = request.form.get('content')
    
    image_file = request.files.get('image')

    # 非同期処理をDiscord Botのイベントループで実行
    bot.loop.create_task(process_web_post(
        is_anon=is_anon,
        reply_target=reply_target,
        user_id=user_id,
        user_name=user_name,
        avatar_url=avatar_url,
        content=content,
        image_file=image_file
    ))

    return render_template_string(HTML_SUCCESS)

async def process_web_post(is_anon, reply_target, user_id, user_name, avatar_url, content, image_file):
    global post_count
    post_count += 1

    board_channel = bot.get_channel(BOARD_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    if not board_channel:
        return

    now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

    body_text = content
    if reply_target:
        body_text = f"> **{reply_target} への返信**\n" + body_text

    display_author = "匿名" if is_anon else user_name
    embed = discord.Embed(description=body_text, color=0x2b2d31)
    header_text = f"#{post_count} | {display_author} | {now_jst}"

    if is_anon:
        embed.set_author(name=header_text)
    else:
        embed.set_author(name=header_text, icon_url=avatar_url)

    # 添付画像の処理
    file_to_send = None
    if image_file and image_file.filename != '':
        file_bytes = image_file.read()
        file_to_send = discord.File(fp=io.BytesIO(file_bytes), filename=image_file.filename)

    post_view = PostItemView(post_num=post_count)
    if file_to_send:
        sent_msg = await board_channel.send(embed=embed, file=file_to_send, view=post_view)
    else:
        sent_msg = await board_channel.send(embed=embed, view=post_view)

    # ログ出力
    if log_channel:
        log_embed = discord.Embed(
            title=f"【投稿ログ #{post_count}】",
            description=body_text,
            color=0x3498db
        )
        log_embed.add_field(name="投稿者", value=f"<@{user_id}> ({user_id})")
        log_embed.add_field(name="表示タイプ", value="匿名" if is_anon else "名前表示")
        log_embed.add_field(name="投稿時間", value=now_jst)
        log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
        await log_channel.send(embed=log_embed)

import io

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# 3. Discord Bot UI & イベント
# ==========================================
async def send_upload_link(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    # Renderのホスト名または環境変数からURLを取得
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "http://localhost:10000")
    
    target_param = reply_target if reply_target else ""
    link = (
        f"{render_url}/upload?"
        f"is_anon={str(is_anonymous).lower()}&"
        f"reply_target={target_param}&"
        f"user_id={interaction.user.id}&"
        f"user_name={interaction.user.display_name}&"
        f"avatar_url={interaction.user.display_avatar.url}"
    )

    embed = discord.Embed(
        description="下のボタンから投稿フォームを開いて投稿してください。",
        color=0x5865f2
    )
    
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="投稿フォームを開く", url=link, style=discord.ButtonStyle.link))

    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.primary, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=True, reply_target=f"#{self.post_num}")

    @discord.ui.button(label="名前返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=False, reply_target=f"#{self.post_num}")

    @discord.ui.button(label="匿名投稿", style=discord.ButtonStyle.success, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=True)

    @discord.ui.button(label="名前投稿", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=False)

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名で投稿", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=True)

    @discord.ui.button(label="名前表示で投稿", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_upload_link(interaction, is_anonymous=False)

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
        description="🔹 **匿名投稿**: 名前を隠して投稿\n"
                    "⚙️ **名前投稿**: ユーザー名を表示して投稿\n"
                    "🚨 **通報**: 違反投稿を通知",
        color=0x3498db
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
