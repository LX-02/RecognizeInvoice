# RecognizeInvoice

企业报销发票识别 MVP：上传发票图片，调用阿里云百炼 Qwen VL OCR 模型识别，结果以 JSON 展示并保存到本地。

## 启动

```powershell
$env:DASHSCOPE_API_KEY="你的阿里云百炼 API Key"
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 本地数据

```text
data/
  uploads/      原始上传图片
  results/      每张图片的识别 JSON
  index.json    上传历史索引
```

重复上传同一张图片时，会根据文件哈希复用历史记录。

## 环境变量

- `DASHSCOPE_API_KEY`：必填，阿里云百炼 API Key。
- `DASHSCOPE_BASE_URL`：可选，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `QWEN_OCR_MODEL`：可选，默认 `qwen-vl-ocr-latest`。
