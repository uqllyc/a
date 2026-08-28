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

# 画像投稿を待機するユーザーの管理 {user_id: {"is_anon": bool, "reply_target": str}}
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

# --- 画像・文章を待機する共通の案内関数 ---
async def start_attachment_post(interaction: discord.Interaction, is_anonymous: bool, reply_target: str = None):
    waiting_users[interaction.user.id] = {
        "is_anonymous": is_anonymous,
        "reply_target": reply_target,
        "channel_id": interaction.channel_id
    }
    
    type_str = "匿名" if is_anonymous else "名前表示"
    target_str = f"（{reply_target} への返信）" if reply_target else ""
    
    await interaction.response.send_message(
        f"📷 **【{type_str}投稿{target_str}】**\n"
        f"このチャンネルに、通常メッセージで**【文章】**と**【画像（＋ボタンで添付）】**を送信してください！\n"
        f"*(※送信後、元のメッセージは自動削除されて掲示板へ反映されます)*",
        ephemeral=True
    )

# --- ユーザーからの直接メッセージ（画像＋本文）を監視 ---
@bot.event
async def on_message(message: discord.Message):
    global post_count

    if message.author.bot:
        return

    # ユーザーが待機中かチェック
    if message.author.id in waiting_users:
        user_config = waiting_users[message.author.id]

        if message.channel.id == user_config["channel_id"]:
            # 待機状態を削除
            del waiting_users[message.author.id]

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

            # メッセージ本体の組み立て
            body_text = message.content if message.content else "（画像のみ）"
            if user_config["reply_target"]:
                body_text = f"> **{user_config['reply_target']} への返信**\n" + body_text

            is_anon = user_config["is_anonymous"]
            author_name = "匿名" if is_anon else message.author.display_name

            embed = discord.Embed(description=body_text, color=0x2b2d31)
            header_text = f"#{post_count} | {author_name} | {now_jst}"

            if is_anon:
                embed.set_author(name=header_text)
            else:
                embed.set_author(name=header_text, icon_url=message.author.display_avatar.url)

            # 送信
            post_view = PostItemView(post_num=post_count)
            if files_to_send:
                sent_msg = await board_channel.send(embed=embed, files=files_to_send, view=post_view)
            else:
                sent_msg = await board_channel.send(embed=embed, view=post_view)

            # ログ送信
            if log_channel:
                log_embed = discord.Embed(
                    title=f"【投稿ログ #{post_count}】",
                    description=body_text,
                    color=0x3498db
                )
                log_embed.add_field(name="投稿者", value=f"{message.author.mention} ({message.author.id})")
                log_embed.add_field(name="表示タイプ", value="匿名" if is_anon else "名前表示")
                log_embed.add_field(name="投稿時間", value=now_jst)
                log_embed.add_field(name="対象メッセージ", value=sent_msg.jump_url)
                await log_channel.send(embed=log_embed)

    await bot.process_commands(message)

# --- 通報用モーダル ---
class ReportModal(discord.ui.Modal):
    def __init__(self, target_post: str = None):
        title_text = f'🚨 通報 ({target_post})' if target_post else '🚨 管理者への通報フォーム'
        super().__init__(title=title_text)

        default_reason = f"{target_post} についての通報: " if target_post else ""
        
        self.report_reason = discord.ui.TextInput(
            label='通報内容・理由',
            style=discord.TextStyle.paragraph,
            placeholder='違反投稿の理由などを入力してください...',
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
        report_embed = discord.Embed(title="🚨【通報が届きました】", description=self.report_reason.value, color=0xff0000)
        report_embed.add_field(name="通報者", value=f"{interaction.user.mention} ({interaction.user.id})")
        report_embed.add_field(name="通報日時", value=now_jst)
        
        await log_channel.send(embed=report_embed)
        await interaction.response.send_message("通報を管理者に送信しました。", ephemeral=True)

# --- 各投稿メッセージの下につくボタン一覧 ---
class PostItemView(discord.ui.View):
    def __init__(self, post_num: int):
        super().__init__(timeout=None)
        self.post_num = post_num

    @discord.ui.button(label="匿名返信", style=discord.ButtonStyle.primary, custom_id="item_reply_anon")
    async def reply_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True, reply_target=f"#{self.post_num}")

    @discord.ui.button(label="名前返信", style=discord.ButtonStyle.secondary, custom_id="item_reply_named")
    async def reply_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False, reply_target=f"#{self.post_num}")

    @discord.ui.button(label="匿名投稿", style=discord.ButtonStyle.success, custom_id="item_post_anon")
    async def post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True)

    @discord.ui.button(label="名前投稿", style=discord.ButtonStyle.secondary, custom_id="item_post_named")
    async def post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False)

    @discord.ui.button(label="通報", style=discord.ButtonStyle.danger, custom_id="item_report")
    async def report_item(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ReportModal(target_post=f"#{self.post_num}"))

# --- メインパネルのボタン設定 ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="匿名で投稿", style=discord.ButtonStyle.primary, custom_id="btn_post_anon")
    async def open_post_anon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=True)

    @discord.ui.button(label="名前表示で投稿", style=discord.ButtonStyle.secondary, custom_id="btn_post_named")
    async def open_post_named(self, interaction: discord.Interaction, button: discord.ui.Button):
        await start_attachment_post(interaction, is_anonymous=False)

    @discord.ui.button(label="通報する", style=discord.ButtonStyle.danger, custom_id="btn_report")
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
@bot.tree.command(name="setup_panel", description="掲示板の投稿・通報パネルを設置します")
async def setup_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📝 掲示板パネル",
        description="用途に合わせて下のボタンを押して投稿してください。\n\n"
                    "🔹 **匿名で投稿**: 名前を隠して新規投稿します\n"
                    "⚙️ **名前表示で投稿**: ユーザー名を表示して新規投稿します\n"
                    "🚨 **通報する**: 違反内容を管理者に通知します",
        color=0x3498db
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
