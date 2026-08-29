const fileInput = document.getElementById("fileInput");
const preview = document.getElementById("preview");
const submit = document.getElementById("postButton");
const content = document.getElementById("content");
const statusText = document.getElementById("status");

// 匿名 / 非匿名
const params = new URLSearchParams(window.location.search);
const isAnonymous = params.get("anonymous") === "true";

// モード表示
const modeText = document.getElementById("modeText");

if (isAnonymous) {
    modeText.textContent = "🔒 匿名投稿";
} else {
    modeText.textContent = "👤 非匿名投稿";
}

// 画像・動画プレビュー
fileInput.addEventListener("change", () => {

    preview.innerHTML = "";

    const file = fileInput.files[0];

    if (!file) {
        return;
    }

    const url = URL.createObjectURL(file);

    if (file.type.startsWith("image/")) {

        const img = document.createElement("img");

        img.src = url;

        preview.appendChild(img);

    } else if (file.type.startsWith("video/")) {

        const video = document.createElement("video");

        video.src = url;
        video.controls = true;

        preview.appendChild(video);
    }
});

// 投稿
submit.addEventListener("click", async () => {

    const text = content.value.trim();
    const file = fileInput.files[0];

    if (!text && !file) {

        statusText.textContent =
            "本文または画像・動画を入力してください。";

        return;
    }

    submit.disabled = true;

    statusText.textContent =
        "投稿しています...";

    const formData = new FormData();

    formData.append(
        "content",
        text
    );

    formData.append(
        "anonymous",
        isAnonymous ? "true" : "false"
    );

    if (file) {

        formData.append(
            "file",
            file
        );
    }

    try {

        const response = await fetch(
            "/api/post",
            {
                method: "POST",
                body: formData
            }
        );

        const result = await response.json();

        if (!response.ok) {

            throw new Error(
                result.error ||
                "投稿に失敗しました"
            );
        }

        statusText.textContent =
            "✅ 投稿しました！";

        content.value = "";

        fileInput.value = "";

        preview.innerHTML = "";

    } catch (error) {

        statusText.textContent =
            "❌ エラー: " +
            error.message;

    } finally {

        submit.disabled = false;
    }
});
