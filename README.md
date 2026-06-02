# RecognizeInvoice

企业 ERP/报销场景的发票识别 MVP。用户上传发票图片或 PDF，后端调用 Qwen VL OCR 识别关键字段，前端展示结构化结果，并将上传记录和识别结果保存到本地。

## 功能范围

- 上传图片或 PDF 发票文件。
- 按文件哈希做基础重复上传识别。
- 调用 OCR 模型提取发票身份、购销方、金额税额、明细和辅助信息。
- 将识别结果保存为 JSON，支持查看历史结果。
- 通过 `static/field-mapping.json` 配置前端字段展示名称、分组和顺序。

## 项目结构

```text
app/
  main.py              FastAPI 应用装配入口
  config.py            路径、模型和上传类型等配置
  schemas.py           API 数据模型
  storage.py           上传索引、文件和结果读写
  routes/
    files.py           上传、列表、预览、结果查询接口
    recognition.py     识别接口
  services/
    ocr.py             OCR 请求、Data URL 和 JSON 解析
static/
  index.html           前端页面
  field-mapping.json   字段展示配置
data/
  uploads/             原始上传文件，本地运行时生成
  results/             每个文件的识别 JSON，本地运行时生成
  index.json           上传历史索引，本地运行时生成
```

## 启动

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\uvicorn.exe app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## 环境变量

应用启动时会读取项目根目录下的 `.env` 文件。

- `DASHSCOPE_API_KEY`：必填，阿里云百炼 API Key。
- `DASHSCOPE_BASE_URL`：可选，默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- `QWEN_OCR_MODEL`：可选，默认 `qwen-vl-ocr-latest`。

## 开发规范

安装开发依赖：

```powershell
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
```

运行格式和静态检查：

```powershell
.\.venv\Scripts\ruff.exe check app
.\.venv\Scripts\ruff.exe format app
```

基础语法检查：

```powershell
.\.venv\Scripts\python.exe -m compileall app
```
