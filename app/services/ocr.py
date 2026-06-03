from __future__ import annotations

# ruff: noqa: E501
import base64
import json
import logging
import mimetypes
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


PROMPT = """你是企业 ERP 报销发票识别验证阶段的 VL-OCR 抽取助手。
你的任务是从单张发票/票据图片或 PDF 页面中读取票面文字，并抽取 ERP 后续流程需要的关键字段。

票据可能包括：
增值税电子普通发票、增值税专用发票、数电票、全电发票、卷式发票、通用机打发票、定额发票、餐饮发票、火车票、出租车票、行程单、电子发票截图或其他报销票据。

必须遵守：
1. 只输出一个合法 JSON 对象。
2. 不要输出 Markdown、代码块、解释文字或多余前后缀。
3. JSON key 必须完整保留，不要省略字段，不要新增外层字段。
4. 看得见但不确定的内容，优先填写最可能的识别结果；只有票面完全没有、被遮挡、严重模糊或无法判断时才填 null。
5. 不要根据常识编造票面不存在的信息。

识别流程必须按以下顺序执行，但最终只输出 JSON：
1. 先从上到下、从左到右完整读取票面文字，特别检查四个角、标题两侧、二维码周围、金额合计区、底部签章/经办人区域。
2. 再根据字段标签、相邻位置和发票版式抽取字段。
3. 最后做一次补漏自检：invoice_number、issue_date、issuer 这三个字段如果仍为 null，必须回看票面右上角/标题附近/底部人员栏再判断一次。

关键字段定位规则：
- invoice_type：票据标题，例如“增值税电子普通发票”“电子发票（普通发票）”“增值税专用发票”“数电票”“出租车发票”“火车票”“行程单”等。
- invoice_code：标签通常是“发票代码”。传统增值税发票常为 10-12 位数字。数电票/全电发票通常没有发票代码，确实没有则填 null。
- invoice_number：标签通常是“发票号码”“号码”“No.”“票据号码”。常在右上角、标题右侧、二维码旁边或票据上方。传统发票常为 8 位左右数字；数电票可能是 20 位号码。
- digital_invoice_number：标签通常是“数电票号码”“电子发票号码”“全电发票号码”。如果票面是数电票/全电发票，且只有一个 20 位左右的“发票号码”，请同时填入 digital_invoice_number；invoice_number 也可填同一号码。
- issue_date：标签通常是“开票日期”“填开日期”“日期”。请抽取票面开具日期，不要把付款日期、乘车日期、服务日期误当作开票日期；若特殊票据只有一个明确日期，可填该票面日期。
- check_code：标签通常是“校验码”，可能是长数字，也可能分段显示在右侧或底部。
- buyer_name / buyer_tax_id：从“购买方”“购方”“付款方”“客户名称”“名称”“纳税人识别号”“统一社会信用代码”等区域抽取。
- seller_name / seller_tax_id：从“销售方”“销方”“收款单位”“开票单位”“名称”“纳税人识别号”“统一社会信用代码”等区域抽取。
- issuer：只抽取明确标注在“开票人”后面的姓名。该字段常在底部人员栏，附近可能还有“收款人”“复核”。不要把“复核人”或“收款人”误填为 issuer；但如果票面只有“开票员/操作员/经办人”且语义等同开票人，可以填入。
- remark：抽取“备注”栏内容。

金额和明细规则：
- amount_without_tax：优先取“不含税金额”“金额”合计，或明细合计中的不含税金额。
- tax_amount：优先取“税额”合计。
- total_amount：优先取“价税合计（小写）”“合计金额”“金额合计”“票价”等最终应报销总额。
- total_amount_cn：抽取“价税合计（大写）”或金额大写。
- tax_rate：优先取主税率/征收率QW；多税率时可填主要税率或合计区域税率。
- items：抽取商品/服务明细行。明细很多时至少抽取主要项目名称、金额、税率、税额；没有明细表的票据填 []。

标准化规则：
- 金额输出数字字符串，去掉“￥”“¥”“人民币”“元”、逗号和空格，例如 "123.45"。
- 日期尽量输出 YYYY-MM-DD，例如票面“2026年6月2日”输出 "2026-06-02"。
- 税率保留百分比字符串，例如 "13%"；免税、不征税、空白或无法判断时按票面输出或填 null。
- 税号/统一社会信用代码保留大写字母和数字，去掉空格。
- 发票号码、发票代码、校验码保留数字/字母原文，不要加入空格。
- ocr_text 必须尽量包含票面主要文字，尤其要包含发票号码、开票日期、开票人周边文字，便于人工复核。

最终 JSON 必须严格使用以下结构：
{
  "invoice_type": null,
  "invoice_code": null,
  "invoice_number": null,
  "digital_invoice_number": null,
  "issue_date": null,
  "check_code": null,
  "buyer_name": null,
  "buyer_tax_id": null,
  "seller_name": null,
  "seller_tax_id": null,
  "amount_without_tax": null,
  "tax_rate": null,
  "tax_amount": null,
  "total_amount": null,
  "total_amount_cn": null,
  "items": [
    {
      "name": null,
      "spec": null,
      "unit": null,
      "quantity": null,
      "unit_price": null,
      "amount": null,
      "tax_rate": null,
      "tax_amount": null
    }
  ],
  "remark": null,
  "issuer": null,
  "ocr_text": null
}"""

USER_OCR_PROMPT = "请识别这张发票或报销票据图片，按 system prompt 的字段和格式要求只返回 JSON。"


def to_data_url_from_bytes(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def to_data_url(path: Path, content_type: str | None) -> str:
    mime_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return to_data_url_from_bytes(path.read_bytes(), mime_type)


def is_pdf(record: dict[str, Any], path: Path) -> bool:
    content_type = (record.get("content_type") or "").split(";")[0].lower()
    return content_type == "application/pdf" or path.suffix.lower() == ".pdf"


def read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"{name} must be a positive integer") from exc
    if value <= 0:
        raise HTTPException(status_code=500, detail=f"{name} must be a positive integer")
    return value


def render_pdf_pages(upload_path: Path) -> tuple[list[str], dict[str, Any]]:
    try:
        import fitz
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF recognition requires PyMuPDF. Run `pip install -r requirements.txt`.",
        ) from exc

    dpi = read_positive_int_env("PDF_RENDER_DPI", 200)
    max_pages = read_positive_int_env("PDF_MAX_PAGES", 1)

    try:
        with fitz.open(upload_path) as document:
            total_pages = document.page_count
            if total_pages <= 0:
                raise HTTPException(status_code=400, detail="PDF file has no pages")

            rendered_pages = min(total_pages, max_pages)
            data_urls = []
            for page_index in range(rendered_pages):
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(dpi=dpi, alpha=False)
                data_urls.append(to_data_url_from_bytes(pixmap.tobytes("png"), "image/png"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to render PDF: {exc}") from exc

    return data_urls, {
        "kind": "pdf",
        "render_dpi": dpi,
        "rendered_pages": rendered_pages,
        "total_pages": total_pages,
    }


def prepare_model_images(record: dict[str, Any], upload_path: Path) -> tuple[list[str], dict[str, Any]]:
    if is_pdf(record, upload_path):
        return render_pdf_pages(upload_path)
    return [to_data_url(upload_path, record.get("content_type"))], {
        "kind": "image",
        "image_count": 1,
    }


def parse_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S | re.I)
        if match:
            return json.loads(match.group(1))
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def recognize_file(
    record: dict[str, Any],
    upload_path: Path,
    model_config: dict[str, str],
) -> dict[str, Any]:
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("DASHSCOPE_BASE_URL", settings.default_base_url),
    )

    image_data_urls, input_meta = prepare_model_images(record, upload_path)
    image_messages = [
        {
            "type": "image_url",
            "image_url": {
                "url": data_url,
            },
        }
        for data_url in image_data_urls
    ]

    try:
        completion = client.chat.completions.create(
            model=model_config["model"],
            messages=[
                {
                    "role": "system",
                    "content": PROMPT,
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": USER_OCR_PROMPT},
                        *image_messages,
                    ],
                },
            ],
        )
        content = completion.choices[0].message.content or ""
        logger.debug("OCR model raw content: %s", content)
        extracted = parse_json_object(content)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Qwen OCR request failed: {exc}") from exc

    return {
        "file": record,
        "input": input_meta,
        "model_key": model_config["key"],
        "model_label": model_config["label"],
        "model": model_config["model"],
        "recognized_at": datetime.now(UTC).isoformat(),
        "result": extracted,
    }
