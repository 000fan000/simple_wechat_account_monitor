"""
文章管理 API 接口
"""
import asyncio
import io
import re
import time
from datetime import datetime
from typing import List, Dict, Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db, Article
from driver.wx_api import WeChat_api, get_qr_code, get_login_status, logout
from driver.wxarticle import fetch_article_content


router = APIRouter(prefix="/api", tags=["article"])


class FetchRequest(BaseModel):
    urls: List[str]


class ArticleResponse(BaseModel):
    id: str
    title: str
    author: str
    url: str
    pic_url: str
    description: str
    content: str
    content_text: str
    publish_time: int
    mp_name: str
    mp_id: str
    has_content: int
    is_favorite: int
    created_at: str


@router.get("/auth/qrcode")
async def get_qrcode():
    """获取登录二维码"""
    result = get_qr_code()
    if result.get('code'):
        return JSONResponse({"code": 0, "data": result})
    return JSONResponse({"code": 1, "msg": result.get('msg', '获取二维码失败')})


@router.get("/auth/status")
async def get_status():
    """获取扫码状态"""
    status = get_login_status()
    return JSONResponse({"code": 0, "data": status})


@router.post("/auth/logout")
async def do_logout():
    """退出登录"""
    logout()
    return JSONResponse({"code": 0, "msg": "已退出登录"})


@router.post("/articles/fetch")
async def fetch_articles(req: FetchRequest):
    """批量抓取文章URL列表的正文内容"""
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls:
        return JSONResponse({"code": 1, "msg": "URL列表为空"})

    results = []
    success_count = 0
    fail_count = 0

    for url in urls:
        try:
            result = await fetch_article_content(url)

            if result.get("fetch_error"):
                results.append({
                    "url": url,
                    "status": "failed",
                    "error": result.get("fetch_error")
                })
                fail_count += 1
                continue

            db = get_db()
            article_data = {
                "id": result.get("id", "") or url,
                "title": result.get("title", "未知标题"),
                "author": result.get("author", ""),
                "url": url,
                "pic_url": result.get("topic_image", ""),
                "description": result.get("description", ""),
                "content": result.get("content", ""),
                "content_text": result.get("content_text", ""),
                "publish_time": result.get("publish_time", 0),
                "mp_name": result.get("mp_info", {}).get("mp_name", ""),
                "mp_id": result.get("mp_id", ""),
                "has_content": 1 if result.get("content") else 0,
            }

            db.add_article(article_data)
            success_count += 1

            results.append({
                "url": url,
                "status": "success",
                "title": article_data["title"],
                "mp_name": article_data["mp_name"]
            })

        except Exception as e:
            results.append({
                "url": url,
                "status": "failed",
                "error": str(e)
            })
            fail_count += 1

        await asyncio.sleep(1)

    return JSONResponse({
        "code": 0,
        "msg": f"抓取完成，成功 {success_count}，失败 {fail_count}",
        "data": {
            "success": success_count,
            "failed": fail_count,
            "results": results
        }
    })


@router.get("/articles")
async def list_articles(page: int = 1, size: int = 20, search: str = ""):
    """分页查询文章列表"""
    db = get_db()
    result = db.get_articles(page=page, size=size, search=search)
    return JSONResponse({"code": 0, "data": result})


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str):
    """删除单篇文章"""
    db = get_db()
    success = db.delete_article(article_id)
    if success:
        return JSONResponse({"code": 0, "msg": "删除成功"})
    return JSONResponse({"code": 1, "msg": "删除失败，文章不存在"})


@router.get("/articles/export")
async def export_articles(ids: str = ""):
    """导出文章为 Excel"""
    db = get_db()

    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return JSONResponse({"code": 1, "msg": "openpyxl 未安装，请运行: pip install openpyxl"})

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "微信公众号文章"

    headers = ["标题", "公众号", "作者", "发布时间", "摘要", "链接", "正文"]
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
        session = db.get_session()
        if id_list:
            articles = session.query(Article).filter(Article.id.in_(id_list)).all()
        else:
            articles = []
    else:
        result = db.get_articles(page=1, size=10000, search="")
        article_ids = [a["id"] for a in result["items"]]
        session = db.get_session()
        articles = session.query(Article).filter(Article.id.in_(article_ids)).all() if article_ids else []

    EXCEL_MAX_TEXT = 32767

    for row_idx, article in enumerate(articles, 2):
        publish_time_str = ""
        if article.publish_time:
            try:
                publish_time_str = datetime.fromtimestamp(article.publish_time).strftime("%Y-%m-%d %H:%M")
            except Exception:
                publish_time_str = str(article.publish_time)

        content_text = article.content_text or ""
        content_text = re.sub(r'^[ \t\xa0]+$', '', content_text, flags=re.MULTILINE)
        content_text = '\n'.join(line.strip() for line in content_text.split('\n') if line.strip())
        if len(content_text) > EXCEL_MAX_TEXT:
            content_text = f"[正文过长，已截断原始长度 {len(content_text)} 字符]"

        row_data = [
            article.title or "",
            article.mp_name or "",
            article.author or "",
            publish_time_str,
            article.description or "",
            article.url or "",
            content_text
        ]

        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 20
    ws.column_dimensions[get_column_letter(1)].width = 40
    ws.column_dimensions[get_column_letter(5)].width = 30
    ws.column_dimensions[get_column_letter(6)].width = 40
    ws.column_dimensions[get_column_letter(7)].width = 50

    ws.row_dimensions[1].height = 25

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"微信公众号文章_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"
        }
    )