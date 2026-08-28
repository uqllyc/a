import datetime
import io
import json
import os
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask, jsonify, render_template, request

# --------------------------------------------------
# 【設定】IDと環境変数
# --------------------------------------------------
BOARD_CHANNEL_ID = 1542868096640098444  # 掲示板チャンネルID
LOG_CHANNEL_ID = 1542866592566747166  # 管理者用ログチャンネルID
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")
WEB_URL = os.environ.get(
    "RENDER_EXTERNAL_URL", "https://a-ai9n.onrender.com"
)
DATA_FILE = "post_count.json"


# --------------------------------------------------
# 投稿番号の保存・読み込み
# --------------------------------------------------
def load_post_id():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("current_post_id", 0)
    except Exception:
      return 0
  return 0


def save_post_id(post_id):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump({"current_post_id": post_id}, f)


current_post_id = load_post_id()

# --------------------------------------------------
# Discord Botの設定
# --------------------------------------------------
intents = discord.Intents.default()
intents.message_content = True


class AnonymousBoardBot(commands.Bot):

  def __init__(self):
    super().__init__(command_prefix="!", intents=intents)

  async def setup_hook(self):
    self.add_view(PostButtonsView())
    await self.tree.sync()


bot = AnonymousBoardBot()


class PostButtonsView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)
    # Discordアプリ内でフォームを開くリンクボタン
    self.add_item(
        discord.ui.Button(
            label="投稿",
            style=discord.ButtonStyle.link,
            url=WEB_URL,
            emoji="✉️",
        )
    )

  @discord.ui.button(
      label="通報",
      style=discord.ButtonStyle.danger,
      custom_id="report_button_persistent",
  )
  async def report_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    message = interaction.message
    post_title = (
        message.embeds[0].author.name if message.embeds else "不明な投稿"
    )
    post_content = (
        message.embeds[0].description if message.embeds else "内容なし"
    )

    if log_channel:
      report_embed = discord.Embed(
          title="🚨 通報通知", color=0xED4245, timestamp=datetime.datetime.now()
      )
      report_embed.add_field(
          name="通報者",
          value=f"{interaction.user.mention} ({interaction.user.name})",
          inline=False,
      )
      report_embed.add_field(
          name="対象投稿", value=post_title, inline=False
      )
      report_embed.add_field(
          name="投稿内容", value=post_content, inline=False
      )
      report_embed.add_field(
          name="投稿URL", value=message.jump_url, inline=False
      )
      await log_channel.send(embed=report_embed)

    await interaction.response.send_message(
        "通報を受け付けました。", ephemeral=True
    )


@bot.tree.command(
    name="setup_panel", description="掲示板に投稿ボタンパネルを設置します"
)
async def setup_panel(interaction: discord.Interaction):
  embed = discord.Embed(
      title="📝 匿名掲示板",
      description="下の「投稿」ボタンを押すと入力フォームが開きます。\n写真や動画もアップロード可能です！",
      color=0x5865F2,
  )
  view = discord.ui.View()
  view.add_item(
      discord.ui.Button(
          label="投稿",
          style=discord.ButtonStyle.link,
          url=WEB_URL,
          emoji="✉️",
      )
  )
  await interaction.channel.send(embed=embed, view=view)
  await interaction.response.send_message(
      "パネルを設置しました。", ephemeral=True
  )


# --------------------------------------------------
# Webサーバー（Flask）の設定 & Renderエラー回避
# --------------------------------------------------
app = Flask(__name__)


@app.route("/")
def index():
  return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
  global current_post_id

  content = request.form.get("content", "")
  ref_id = request.form.get("ref_id", "")
  anonymous = request.form.get("anonymous", "true") == "true"
  file = request.files.get("file")

  if not content and not file:
    return (
        jsonify(
            {"success": False, "message": "テキストかファイルを入力してください。"}
        ),
        400,
    )

  current_post_id += 1
  post_id = current_post_id
  save_post_id(post_id)

  async def send_to_discord():
    board_channel = bot.get_channel(BOARD_CHANNEL_ID)
    log_channel = bot.get_channel(LOG_CHANNEL_ID)

    author_name = "匿名" if anonymous else "投稿者"

    # 日本時間の現在時刻（例: 今日 02:22）
    now = datetime.datetime.now()
    time_str = f"今日 {now.strftime('%H:%M')}"

    description = content
    if ref_id:
      description = f">> {ref_id}\n" + description

    embed = discord.Embed(description=description, color=0x2B2D31)
    embed.set_author(name=f"{post_id} : {author_name}")
    embed.set_footer(text=time_str)

    discord_file = None
    if file:
      file_bytes = file.read()
      discord_file = discord.File(
          io.BytesIO(file_bytes), filename=file.filename
      )
      if file.content_type and file.content_type.startswith("image/"):
        embed.set_image(url=f"attachment://{file.filename}")

    if board_channel:
      if discord_file:
        await board_channel.send(
            embed=embed, file=discord_file, view=PostButtonsView()
        )
      else:
        await board_channel.send(embed=embed, view=PostButtonsView())

    if log_channel:
      log_embed = discord.Embed(
          title=f"【投稿ログ】No.{post_id}",
          color=0x2B2D31,
          timestamp=now,
      )
      log_embed.add_field(
          name="投稿種別",
          value="匿名" if anonymous else "非匿名",
          inline=True,
      )
      log_embed.add_field(
          name="内容", value=content or "（本文なし）", inline=False
      )
      if file:
        log_embed.add_field(
            name="添付ファイル", value=f"`{file.filename}`", inline=False
        )
      await log_channel.send(embed=log_embed)

  bot.loop.create_task(send_to_discord())
  return jsonify({"success": True, "message": "投稿が完了しました！"})


def run_flask():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
  t = Thread(target=run_flask)
  t.start()
  if BOT_TOKEN:
    bot.run(BOT_TOKEN)
