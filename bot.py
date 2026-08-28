<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>投稿</title>
  <style>
    :root {
      --bg-color: #000000;         /* 背景：完全な黒 */
      --card-bg: #111111;         /* カード背景：超暗色 */
      --input-bg: #181818;        /* 入力欄背景 */
      --text-color: #ffffff;      /* 文字色：白 */
      --sub-text: #8e8e93;        /* サブテキスト */
      --accent-color: #5865f2;    /* Discordブルー */
      --border-color: #222222;    /* 枠線 */
    }

    * {
      box-sizing: border-box;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg-color);
      color: var(--text-color);
      margin: 0;
      padding: 16px;
      display: flex;
      justify-content: center;
      align-items: flex-start;
      min-height: 100vh;
    }

    .container {
      width: 100%;
      max-width: 480px;
    }

    .form-group {
      margin-bottom: 18px;
    }

    label {
      display: block;
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 8px;
      color: var(--sub-text);
      letter-spacing: -0.2px;
    }

    textarea, input[type="text"] {
      width: 100%;
      background-color: var(--input-bg);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 12px 14px;
      color: var(--text-color);
      font-size: 15px;
      outline: none;
      transition: border-color 0.2s;
    }

    textarea:focus, input[type="text"]:focus {
      border-color: var(--accent-color);
    }

    textarea {
      height: 110px;
      resize: none;
    }

    /* 匿名 / 非匿名 セグメントスイッチ */
    .toggle-group {
      display: flex;
      background-color: var(--input-bg);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 3px;
      gap: 4px;
    }

    .toggle-option {
      flex: 1;
      text-align: center;
      padding: 9px;
      font-size: 14px;
      font-weight: 600;
      border-radius: 7px;
      cursor: pointer;
      user-select: none;
      color: var(--sub-text);
      transition: all 0.2s ease;
    }

    .toggle-option.active {
      background-color: var(--accent-color);
      color: #ffffff;
    }

    /* ファイル添付領域 */
    .file-input-wrapper {
      position: relative;
      background-color: var(--input-bg);
      border: 1px dashed var(--border-color);
      border-radius: 10px;
      padding: 16px;
      text-align: center;
      cursor: pointer;
    }

    .file-input-wrapper input[type="file"] {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      opacity: 0;
      cursor: pointer;
    }

    .file-label {
      font-size: 14px;
      color: var(--sub-text);
    }

    .file-name {
      margin-top: 8px;
      font-size: 13px;
      color: var(--accent-color);
      word-break: break-all;
    }

    button[type="submit"] {
      width: 100%;
      background-color: var(--accent-color);
      color: white;
      border: none;
      border-radius: 10px;
      padding: 14px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 8px;
      transition: opacity 0.2s;
    }

    button[type="submit"]:disabled {
      opacity: 0.5;
    }

    #status-msg {
      margin-top: 12px;
      text-align: center;
      font-size: 13px;
      font-weight: 500;
    }
  </style>
</head>
<body>

<div class="container">
  <form id="postForm" enctype="multipart/form-data">
    
    <div class="form-group">
      <label>本文（任意・画像・動画のみも可）</label>
      <textarea id="content" name="content" placeholder="投稿内容を入力..."></textarea>
    </div>

    <div class="form-group">
      <label>レス先番号（任意）</label>
      <input type="text" id="ref_id" name="ref_id" placeholder="例: 99">
    </div>

    <div class="form-group">
      <label>投稿方法</label>
      <div class="toggle-group">
        <div class="toggle-option active" id="btn-anon" onclick="setAnonymous(true)">匿名</div>
        <div class="toggle-option" id="btn-real" onclick="setAnonymous(false)">非匿名</div>
      </div>
      <input type="hidden" id="anonymous" name="anonymous" value="true">
    </div>

    <div class="form-group">
      <label>画像・動画添付</label>
      <div class="file-input-wrapper">
        <span class="file-label">📷 タップして写真・動画を選択</span>
        <input type="file" id="file" name="file" accept="image/*,video/*" onchange="showFileName(this)">
      </div>
      <div id="file-name" class="file-name"></div>
    </div>

    <button type="submit" id="submit-btn">送信する</button>
    <div id="status-msg"></div>

  </form>
</div>

<script>
  function setAnonymous(isAnon) {
    document.getElementById('anonymous').value = isAnon ? "true" : "false";
    document.getElementById('btn-anon').classList.toggle('active', isAnon);
    document.getElementById('btn-real').classList.toggle('active', !isAnon);
  }

  function showFileName(input) {
    const display = document.getElementById('file-name');
    if (input.files && input.files[0]) {
      display.textContent = '選択中: ' + input.files[0].name;
    } else {
      display.textContent = '';
    }
  }

  document.getElementById('postForm').addEventListener('submit', async function(e) {
    e.preventDefault();
    const btn = document.getElementById('submit-btn');
    const msg = document.getElementById('status-msg');

    btn.disabled = true;
    msg.textContent = '送信中...';
    msg.style.color = '#8e8e93';

    try {
      const response = await fetch('/submit', {
        method: 'POST',
        body: new FormData(this)
      });
      const resData = await response.json();

      if (response.ok && resData.success) {
        msg.textContent = '✅ 投稿しました';
        msg.style.color = '#23a55a';
        document.getElementById('postForm').reset();
        document.getElementById('file-name').textContent = '';
        setAnonymous(true);
      } else {
        msg.textContent = '❌ ' + (resData.message || 'エラーが発生しました');
        msg.style.color = '#f23f43';
      }
    } catch (err) {
      msg.textContent = '❌ 通信エラーが発生しました';
      msg.style.color = '#f23f43';
    } finally {
      btn.disabled = false;
    }
  });
</script>

</body>
</html>
