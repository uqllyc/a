import datetime
import json
import os
from threading import Thread
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

# --------------------------------------------------
# 【Render無料枠対応】Webサーバー用設定
# --------------------------------------------------
app = Flask("")


@app.route("/")
def home():
  return "Bot is running!"


def run():
  port = int(os.environ.get("PORT", 10000))
  app.run(host="0.0.0.0", port=port)


def keep_alive():
  t = Thread(target=run)
  t.start()


# --------------------------------------------------
# 【設定】IDとトークン
# --------------------------------------------------
BOARD_CHANNEL_ID = 1542868096640098444  # 掲示板チャンネルのID
LOG_CHANNEL_ID = 1542866592566747166  # 管理者用ログチャンネル
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")
DATA_FILE = "post_count.json"  # 投稿番号の保存用ファイル

intents = discord.Intents.default()
intents.message_content = True


def load_post_id():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("current_post_id", 0)
    except Exception:
      return 0
  return 0


def save_post_id(post_id):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
    json.dump({"current_post_id": post_id}, f)


class AnonymousBoardBot(commands.Bot):

  def __init__(self):
    super().__init__(command_prefix="!", intents=intents)
    self.current_post_id = load_post_id()

  async def setup_hook(self):
    self.add_view(PostButtonsView())


bot = AnonymousBoardBot()


# --------------------------------------------------
# 1. 通報ボタン（投稿カード下部）
# --------------------------------------------------
class PostButtonsView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

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


# --------------------------------------------------
# 2. 投稿コマンド（/post）
# --------------------------------------------------
@bot.tree.command(
    name="post",
    description="掲示板に投稿します（画像・動画ファイル直接添付可能）",
)
@app_commands.describe(
    content="投稿するテキスト（省略可能）",
    file="添付する画像または動画ファイル（省略可能）",
    anonymous="True: 匿名で投稿 / False: 名前を表示して投稿",
)
async def post(
    interaction: discord.Interaction,
    content: str = None,
    file: discord.Attachment = None,
    anonymous: bool = True,
):
  if not content and not file:
    await interaction.response.send_message(
        "テキストかファイルのどちらかは必須です。", ephemeral=True
    )
    return

  bot.current_post_id += 1
  post_id = bot.current_post_id
  save_post_id(post_id)

  board_channel = interaction.guild.get_channel(BOARD_CHANNEL_ID)
  log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

  now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
  author_name = "匿名" if anonymous else interaction.user.display_name

  embed = discord.Embed(description=content or "", color=0x2B2D31)
  embed.set_author(name=f"{post_id} : {author_name} • {now_str}")

  if not anonymous:
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

  # 送信用ファイルと画像の埋め込み処理
  discord_file = None
  if file:
    file_bytes = await file.read()
    import io

    discord_file = discord.File(io.BytesIO(file_bytes), filename=file.filename)

    # 画像の場合はEmbed内にセット
    if file.content_type and file.content_type.startswith("image/"):
      embed.set_image(url=f"attachment://{file.filename}")

  # 掲示板へ送信
  if board_channel:
    if discord_file:
      await board_channel.send(
          embed=embed, file=discord_file, view=PostButtonsView()
      )
    else:
      await board_channel.send(embed=embed, view=PostButtonsView())

  # 管理者用ログ送信
  log_embed = discord.Embed(
      title=f"【投稿ログ】No.{post_id}",
      color=0x2B2D31,
      timestamp=datetime.datetime.now(),
  )
  log_embed.add_field(
      name="投稿者",
      value=f"{interaction.user.mention} ({interaction.user.name})",
      inline=False,
  )
  log_embed.add_field(
      name="投稿種別",
      value="匿名投稿" if anonymous else "公開投稿",
      inline=True,
  )
  log_embed.add_field(name="内容", value=content or "（なし）", inline=False)
  if file:
    log_embed.add_field(
        name="添付ファイル", value=f"`{file.filename}`", inline=False
    )

  if log_channel:
    await log_channel.send(embed=log_embed)

  await interaction.response.send_message(
      "投稿が完了しました！", ephemeral=True
  )


# --------------------------------------------------
# 3. 起動設定とコマンド自動同期
# --------------------------------------------------
@bot.event
async def on_ready():
  try:
    synced = await bot.tree.sync()
    print(f"コマンド同期完了: {len(synced)} 個のコマンドを同期しました。")
  except Exception as e:
    print(f"コマンド同期エラー: {e}")

  print(
      f"Logged in as {bot.user} - 起動完了（現在の投稿ID: {bot.current_post_id}）"
  )


if __name__ == "__main__":
  keep_alive()
  if BOT_TOKEN:
    bot.run(BOT_TOKEN)
  else:
    print("Error: DISCORD_TOKEN is not set.")
