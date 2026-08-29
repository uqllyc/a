const fileInput = document.getElementById("file");
const preview = document.getElementById("preview");
const submit = document.getElementById("submit");
const content = document.getElementById("content");
const statusText = document.getElementById("status");


// ==========================================
// 画像・動画を選択したときのプレビュー
// ==========================================

fileInput.addEventListener("change", () => {

    preview.innerHTML = "";

    const file = fileInput.files[0];

    if (!file) {
        return;
    }

    const url = URL.createObjectURL(file);


    // 画像
    if (file.type.startsWith("image/")) {

        const img = document.createElement("img");

        img.src = url;

        preview.appendChild(img);
    }


    // 動画
    else if (file.type.startsWith("video/")) {

        const video = document.createElement("video");

        video.src = url;
        video.controls = true;

        preview.appendChild(video);
    }

});


// ==========================================
// 投稿ボタン
// ==========================================

submit.addEventListener("click", async () => {

    const text = content.value.trim();
    const file = fileInput.files[0];


    // 本文もファイルもない
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


        const result =
            await response.json();


        if (!response.ok) {

            throw new Error(
                result.error ||
                "投稿に失敗しました"
            );

        }


        statusText.textContent =
            "投稿しました！";


        content.value = "";

        fileInput.value = "";

        preview.innerHTML = "";


    } catch (error) {

        statusText.textContent =
            "エラー: " +
            error.message;


    } finally {

        submit.disabled = false;

    }

});
