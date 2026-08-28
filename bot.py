import os
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask
import discord
from discord.ext import commands

# JST（日本時間）の定義
JST = timezone(timedelta(hours=+9))

# 投稿番号カウンター（メモリ上で管理）
post_count = 0

# 画像投稿を待機するユーザーの管理
waiting_users = {}

# ==========================================
# 1. Renderのポート監視エラー回避用Webサーバー
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = threading.Thread(target=run_web)
    t.daemon = True
    t.start()

# ==========================================
# 2. Discord Bot 設定
# ==========================================
TOKEN = os.environ.get("DISCORD_TOKEN")
BOARD_CHANNEL_ID = int(os.environ.get("BOARD_CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "0"))

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# --- 案内メッセージ送信関数 ---
async def start_attachment_post(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    target_str = f"（{reply_target} 宛て）" if reply_target else ""
    type_str = "匿名" if is_anonymous else "非匿名"
    
    msg = (
        f"で投稿するよ {target_str}**\n\n"
        f"メッセージや画像をこのチャンネルに入力・送信してください。\n"
        f"*(送信したら元メッセージは自動で消えて掲示板に載ります)*"
    )
    
    # メッセージを送信し、オブジェクトを取得
    await interaction.response.send_message(msg, ephemeral=True)
    notice_msg = await interaction.original_response()

    waiting_users[interaction.user.id] = {
        "is_anonymous": is_anonymous,
        "reply_target": reply_target,
        "channel_id": interaction.channel_id,
        "notice_message": notice_msg  # 案内メッセージを保持
    }

# --- ユーザーからの直接メッセージ（画像＋本文）を監視 ---
@bot.event
async def on_message(message: discord.Message):
    global post_count

    if message.author.bot:
        return

    if message.author.id in waiting_users:
        user_config = waiting_users[message.author.id]

        if message.channel.id == user_config["channel_id"]:
            # 登録情報を削除
            del waiting_users[message.author.id]

            # 案内メッセージ（ephemeral）を削除
            notice_msg = user_config.get("notice_message")
            if notice_msg:
                try:
                    await notice_msg.delete()
                except Exception:
                    pass

            board_channel = bot.get_channel(BOARD_CHANNEL_ID)
            log_channel = bot.get_channel(LOG_CHANNEL_ID)

            if not board_channel:
                await message.channel.send("エラー: 投稿先のチャンネルが見つかりません。", delete_after=5)
                return

            post_count += 1
            now_jst = datetime.now(JST).strftime("%Y/%m/%d %H:%M")

            # 添付ファイルを取得
            files_to_send = []
            for attachment in message.attachments:
                file_data = await attachment.to_file()
                files_to_send.append(file_data)

            # 元メッセージを即削除（匿名化のため）
            try:
                await message.delete()
            except Exception:
                pass

            body_text = message.content if message.content else "（画像のみ）"
            if user_config["reply_target"]:
                body_text = f"> **{user_config['reply_target']} への返信**\n" + body_text

            is_anon = user_config["is_anonymous"]
            author_name = "匿名" if is_anon else message.author.display_name

            embed = discord.Embed(description=body_text, color=0x000000)
            header_text = f"#{post_count} | {author_name} | {now_jst}"

            if is_anon:
                embed.set_author(name=header_text)
            else:
                embed.set_author(name=header_text, icon_url=message.author.display_avatar.url)

            # 投稿
            post_view = PostItemView(post_num=post_count)
            if files_to_send:
                sent_msg = await board_channel.send(embed=embed, files=files_to_send, view=post_view)
            else:
                sent_msg = await board_channel.send(embed=embed, view=post_view)

            # ログ
            if log_channel:
                log_embed = discord.Embed(
                    title=f"【投稿ログ #{post_count}】",
                    description=body_text,
                    color=0x2b2d31
                )
                log_embed.add_field(name="投稿者", value=f"{message.author.mention} ({message.author.id})")
                log_embed.add_field(name="表示タイプ", value="匿名" if is_anon else "非匿名")
                log_embed.add_field(name="投稿時間", value=now_jst)
                log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
                await log_channel.send(embed=log_embed)

    await bot.process_commands(message)

# --- 通報用モーダル ---
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
# 各投稿メッセージの下につくボタン一覧（指定順）
# ==========================================
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    # 1. 匿名
    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True)

    # 2. 非匿名
    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False)

    # 3. 匿名返信
    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.success, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True, reply_target=f"#{self.post_num}")

    # 4. 非匿名返信
    @discord.ui.button(label="非匿名返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False, reply_target=f"#{self.post_num}")

    # 5. 通報
    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

# --- メインパネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True)

    @discord.ui.button(label="非匿名", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False)

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="btn_report")
    async def open_report(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal())

# --- Bot起動処理 ---
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.add_view(PanelView())
    
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# --- パネル設置コマンド ---
@bot.tree.command(name="setup_panel", description="掲示板パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板",
        description="🔹 **匿名**: 名前を隠して投稿\n"
                    "⚙️ **非匿名**: ユーザー名を表示して投稿\n"
                    "🚨 **通報**: 違反投稿を通知",
        color=0x000000
    )
    await interaction.channel.send(embed=embed, view=PanelView())
    await interaction.response.send_message("パネルを設置しました。", ephemeral=True)

# 実行
if __name__ == "__main__":
    if TOKEN:
        keep_alive()
        bot.run(TOKEN)
    else:
        print("エラー: DISCORD_TOKEN が設定されていません。")
