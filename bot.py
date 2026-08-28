import datetime
import discord
from discord import app_commands
from discord.ext import commands

# --------------------------------------------------
# 【設定】IDとトークン
# --------------------------------------------------
BOARD_CHANNEL_ID = 1542868096640098444  # 掲示板チャンネルID
LOG_CHANNEL_ID = 1542866592566747166  # 管理者用ログチャンネルID
BOT_TOKEN = os.environ.get("DISCORD_TOKEN")

post_count = 0

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


# 投稿入力モーダル（ポップアップ画面）
class PostModal(discord.ui.Modal, title="投稿"):

  def __init__(self):
    super().__init__()

  content = discord.ui.TextInput(
      label="投稿",
      style=discord.TextStyle.paragraph,
      placeholder="本文（任意・画像・動画のみの投稿も可）",
      required=False,
      max_length=1800,
  )

  ref_id = discord.ui.TextInput(
      label="レス",
      style=discord.TextStyle.short,
      placeholder="例: 99 / n99",
      required=False,
  )

  method = discord.ui.TextInput(
      label="投稿方法",
      style=discord.TextStyle.short,
      placeholder="「匿名」または「非匿名」を入力してください（初期値: 匿名）",
      default="匿名",
      required=False,
  )

  async def on_submit(self, interaction: discord.Interaction):
    global post_count
    post_count += 1

    board_channel = interaction.guild.get_channel(BOARD_CHANNEL_ID)
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)

    # 日時の取得（例: 今日 1:48）
    now = datetime.datetime.now()
    time_str = f"今日 {now.strftime('%H:%M')}"

    # 投稿者名の判定
    is_anon = self.method.value.strip() != "非匿名"
    author_name = "匿名" if is_anon else interaction.user.display_name

    # 本文の作成（レス番号があれば追加）
    description_text = ""
    if self.ref_id.value:
      description_text += f">>{self.ref_id.value}\n"
    if self.content.value:
      description_text += self.content.value

    # Embedの作成
    embed = discord.Embed(
        description=description_text or "（本文なし）", color=0x2B2D31
    )
    embed.set_author(name=f"{post_count} : {author_name}")
    embed.set_footer(text=time_str)

    # 掲示板チャンネルへ送信
    if board_channel:
      await board_channel.send(embed=embed, view=PostButtonsView())

    # 管理用ログチャンネルへ送信
    if log_channel:
      log_embed = discord.Embed(
          title=f"【投稿ログ】No.{post_count}",
          color=0x2B2D31,
          timestamp=now,
      )
      log_embed.add_field(
          name="投稿者",
          value=f"{interaction.user.mention} ({interaction.user.name})",
          inline=False,
      )
      log_embed.add_field(
          name="投稿種別", value="匿名" if is_anon else "非匿名", inline=True
      )
      log_embed.add_field(
          name="内容",
          value=self.content.value or "（本文なし）",
          inline=False,
      )
      await log_channel.send(embed=log_embed)

    await interaction.response.send_message(
        "投稿が完了しました！", ephemeral=True
    )


# 掲示板の下に付くボタン
class PostButtonsView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="投稿", style=discord.ButtonStyle.secondary, emoji="✉️"
  )
  async def post_button(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_modal(PostModal())

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


# コマンドでパネルを設置
@bot.tree.command(
    name="setup_panel", description="掲示板に投稿ボタンパネルを設置します"
)
async def setup_panel(interaction: discord.Interaction):
  embed = discord.Embed(
      title="📝 匿名掲示板",
      description="下の「投稿」ボタンを押すとフォームが開きます。",
      color=0x5865F2,
  )
  await interaction.channel.send(embed=embed, view=PostButtonsView())
  await interaction.response.send_message(
      "パネルを設置しました。", ephemeral=True
  )


if __name__ == "__main__":
  import os

  if BOT_TOKEN:
    bot.run(BOT_TOKEN)
