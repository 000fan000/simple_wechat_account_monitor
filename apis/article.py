"""
文章管理 API 接口
"""
import asyncio
import io
import re
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import get_db, Article
from driver.wx_api import WeChat_api, get_qr_code, get_login_status, logout, get_mpsweb, extract_biz_from_url, extract_fakeid_from_html, biz_to_fakeid
from driver.wxarticle import fetch_article_content


router = APIRouter(prefix="/api", tags=["article"])




class IdentifyRequest(BaseModel):
    urls: List[str]

class FetchByAccountRequest(BaseModel):
    fakeid: str
    mp_name: str = ""
    max_pages: int = 3
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
                "has_content": 1 if result.get("content") else 0,
            }

            db.add_article(article_data)
            success_count += 1

            results.append({
                "url": url,
                "status": "success",
                "title": article_data["title"],
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



@router.post("/articles/identify")
async def identify_accounts(req: IdentifyRequest):
    urls = [u.strip() for u in req.urls if u.strip()]
    if not urls:
        return JSONResponse({"code": 1, "msg": "URL列表为空"})

    import httpx
    accounts = {}

    for url in urls:
        try:
            biz = extract_biz_from_url(url)

            async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                })
                html = resp.text

                fakeid_from_page = extract_fakeid_from_html(html)

                if not biz and not fakeid_from_page:
                    continue

                mp_name = ""
                if not mp_name:
                    m = re.search(r'var\s+nickname\s*=\s*["\']([^"\']+)["\']', html)
                    if m:
                        mp_name = m.group(1)
                if not mp_name:
                    m = re.search(r'data-nickname=["\x27]([^"\x27]+)["\x27]', html)
                    if m:
                        mp_name = m.group(1)
                if not mp_name:
                    m = re.search(r"nick_name:\s*['\"](\w{2,20})['\"]", html)
                    if m:
                        mp_name = m.group(1)

            fakeid = fakeid_from_page if fakeid_from_page else (biz_to_fakeid(biz) if biz else '')

            if fakeid not in accounts:
                accounts[fakeid] = {"biz": biz, "fakeid": fakeid, "mp_name": mp_name, "urls": []}
            accounts[fakeid]["urls"].append(url)

        except Exception:
            continue

    result = list(accounts.values())
    return JSONResponse({
        "code": 0,
        "data": {
            "accounts": result,
            "total": len(result)
        }
    })


@router.post("/articles/fetch-by-account")
async def fetch_by_account(req: FetchByAccountRequest):
    import asyncio as aio

    success, count, msg = await fetch_by_account_raw(req.fakeid, req.mp_name, req.max_pages)
    return JSONResponse({"code": 0 if success else 1, "msg": msg, "data": {"new_count": count, "total": count}})



async def fetch_by_account_raw(fakeid: str, mp_name: str, max_pages: int = 3):
    import asyncio as aio, json
    from driver.wx_api import get_mpsweb
    db = get_db()
    try:
        mps = get_mpsweb()
    except Exception as e:
        return False, 0, str(e)
    new_count = 0
    for page in range(max_pages):
        begin = page * 5
        try:
            resp = mps.get_Articles(fakeid, begin=begin)
        except Exception as e:
            return False, new_count, str(e)
        base_resp = resp.get('base_resp', {})
        ret = base_resp.get('ret', 0)
        if ret == 200013:
            return False, new_count, "频率限制"
        if ret == 200003:
            return False, new_count, "登录过期"
        if ret != 0:
            return False, new_count, base_resp.get('err_msg', '')
        pub_page = resp.get('publish_page', '')
        if isinstance(pub_page, str):
            try:
                pub_page = json.loads(pub_page)
            except:
                pass
        pub_list = []
        if isinstance(pub_page, dict):
            pub_list = pub_page.get('publish_list', [])
        elif isinstance(pub_page, list):
            pub_list = pub_page
        if not pub_list:
            break
        for pub_item in pub_list:
            pub_info = pub_item.get('publish_info', '{}')
            if isinstance(pub_info, str):
                try:
                    pub_info = json.loads(pub_info)
                except:
                    continue
            articles_list = []
            if isinstance(pub_info, dict):
                articles_list = pub_info.get('appmsgex', [])
            for art_data in articles_list:
                link = art_data.get('link', '')
                if not link:
                    continue
                art = {
                    "id": str(art_data.get('aid', '')),
                    "title": art_data.get('title', '未知标题'),
                    "author": art_data.get('author', ''),
                    "url": link,
                    "pic_url": art_data.get('cover', ''),
                    "description": art_data.get('digest', ''),
                    "publish_time": int(art_data.get('update_time', 0) or art_data.get('create_time', 0)),
                    "mp_name": mp_name,
                    "content_text": art_data.get('digest', ''),
                    "has_content": 0,
                }
                if db.add_article(art):
                    new_count += 1
        await aio.sleep(3)
    return True, new_count, f"新增 {new_count} 篇"



class FetchContentRequest(BaseModel):
    ids: List[str]


@router.post("/articles/fetch-content")
async def fetch_articles_content(req: FetchContentRequest):
    """批量采集选定文章的正文字段（只更新 has_content=0 的文章）"""
    if not req.ids:
        return JSONResponse({"code": 1, "msg": "文章ID列表为空"})

    db = get_db()
    session = db.get_session()
    articles = session.query(Article).filter(Article.id.in_(req.ids)).all()
    session.close()

    results = []
    success_count = 0
    fail_count = 0

    for art in articles:
        if not art.url:
            results.append({"id": art.id, "status": "skipped", "reason": "无URL"})
            continue

        try:
            result = await fetch_article_content(art.url)

            if result.get("fetch_error"):
                results.append({"id": art.id, "status": "failed", "error": result["fetch_error"]})
                fail_count += 1
                continue

            session2 = db.get_session()
            a = session2.query(Article).filter(Article.id == art.id).first()
            if a:
                a.title = result.get("title") or a.title
                a.author = result.get("author") or a.author
                a.pic_url = result.get("topic_image") or a.pic_url
                a.description = result.get("description") or a.description
                a.content = result.get("content") or ""
                a.content_text = result.get("content_text") or ""
                a.publish_time = result.get("publish_time") or a.publish_time
                a.has_content = 1 if result.get("content") else 0
                session2.commit()
            session2.close()

            success_count += 1
            results.append({"id": art.id, "title": result.get("title"), "status": "success", "has_content": bool(result.get("content"))})
        except Exception as e:
            results.append({"id": art.id, "status": "failed", "error": str(e)})
            fail_count += 1

        await asyncio.sleep(1)

    return JSONResponse({
        "code": 0,
        "msg": f"采集完成，成功 {success_count}，失败 {fail_count}",
        "data": {"success": success_count, "failed": fail_count, "results": results}
    })

ACCOUNTS_FILE = "data/accounts.json"

def _load_accounts():
    import json, os
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    return []

def _save_accounts(accounts):
    import json, os
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


@router.get("/accounts")
async def list_accounts():
    """获取所有已识别+已入库的公众号列表"""
    stored = _load_accounts()
    db = get_db()
    session = db.get_session()
    from sqlalchemy import func
    rows = session.query(Article.mp_name, func.count(Article.id)).filter(
        Article.mp_name != '', Article.mp_name.isnot(None)
    ).group_by(Article.mp_name).all()
    session.close()

    db_accounts = {name: count for name, count in rows}
    seen = set()
    result = []
    for acc in stored:
        name = acc.get('mp_name', '') or ''
        seen.add(name)
        result.append({
            "mp_name": name,
            "fakeid": acc.get('fakeid', ''),
            "biz": acc.get('biz', ''),
            "article_count": db_accounts.get(name, 0),
            "saved": True
        })
    for name, count in db_accounts.items():
        if name not in seen:
            result.append({
                "mp_name": name,
                "fakeid": "",
                "biz": "",
                "article_count": count,
                "saved": False
            })
    return JSONResponse({"code": 0, "data": {"accounts": result, "total": len(result)}})


class SaveAccountRequest(BaseModel):
    accounts: list


@router.post("/accounts/save")
async def save_accounts(req: SaveAccountRequest):
    """保存识别到的公众号"""
    _save_accounts(req.accounts)
    return JSONResponse({"code": 0, "msg": f"已保存 {len(req.accounts)} 个公众号"})

class DeleteAccountsRequest(BaseModel):
    fakeids: List[str]


@router.post("/accounts/delete")
async def delete_accounts(req: DeleteAccountsRequest):
    if not req.fakeids:
        return JSONResponse({"code": 1, "msg": "fakeid列表为空"})
    stored = _load_accounts()
    before = len(stored)
    stored = [a for a in stored if a.get('fakeid', '') not in req.fakeids]
    _save_accounts(stored)
    return JSONResponse({"code": 0, "msg": f"已删除 {before - len(stored)} 个公众号"})


@router.get("/accounts/export")
async def export_accounts():
    stored = _load_accounts()
    if not stored:
        return JSONResponse({"code": 1, "msg": "暂无已保存的公众号"})
    content = json.dumps(stored, ensure_ascii=False, indent=2).encode('utf-8')
    from urllib.parse import quote
    return StreamingResponse(
        iter([content]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote("公众号账号库.json")}
    )


@router.post("/accounts/import")
async def import_accounts(file: UploadFile = File(None)):
    if not file:
        return JSONResponse({"code": 1, "msg": "请上传JSON文件"})
    try:
        raw = await file.read()
        imported = json.loads(raw.decode('utf-8'))
        if not isinstance(imported, list):
            return JSONResponse({"code": 1, "msg": "JSON格式错误，需要一个数组"})
        stored = _load_accounts()
        existing = {a.get('fakeid') for a in stored if a.get('fakeid')}
        new_count = 0
        for acc in imported:
            if not isinstance(acc, dict):
                continue
            if acc.get('fakeid') and acc['fakeid'] not in existing:
                stored.append(acc)
                existing.add(acc['fakeid'])
                new_count += 1
            elif not acc.get('fakeid') and acc.get('mp_name'):
                stored.append(acc)
                new_count += 1
        _save_accounts(stored)
        return JSONResponse({"code": 0, "msg": f"导入 {len(imported)} 条，新增 {new_count} 条"})
    except Exception as e:
        return JSONResponse({"code": 1, "msg": f"导入失败: {str(e)}"})


class DeleteAccountsRequest(BaseModel):
    fakeids: List[str]



class ArticleFilterParams:
    def __init__(self, page: int = 1, size: int = 20, search: str = "", mp_name: str = ""):
        self.page = page
        self.size = size
        self.search = search
        self.mp_name = mp_name


@router.get("/articles")
async def list_articles(page: int = 1, size: int = 20, search: str = "", mp_name: str = "", date_start: str = "", date_end: str = ""):
    """分页查询文章列表，支持按公众号过滤+日期范围"""
    db = get_db()
    session = db.get_session()
    query = session.query(Article)
    if search:
        p = f"%{search}%"
        query = query.filter((Article.title.like(p)) | (Article.description.like(p)))
    if mp_name:
        query = query.filter(Article.mp_name == mp_name)
    if date_start:
        try:
            ts = int(datetime.strptime(date_start, "%Y-%m-%d").timestamp())
            query = query.filter(Article.publish_time >= ts)
        except:
            pass
    if date_end:
        try:
            ts = int(datetime.strptime(date_end, "%Y-%m-%d").timestamp()) + 86400
            query = query.filter(Article.publish_time <= ts)
        except:
            pass
    total = query.count()
    offset = (page - 1) * size
    articles = query.order_by(Article.created_at.desc()).offset(offset).limit(size).all()
    session.close()
    return JSONResponse({
        "code": 0,
        "data": {
            "items": [a.to_dict() for a in articles],
            "total": total, "page": page, "size": size,
            "pages": (total + size - 1) // size
        }
    })


@router.get("/articles/{article_id}/detail")
async def get_article_detail(article_id: str):
    db = get_db()
    session = db.get_session()
    art = session.query(Article).filter(Article.id == article_id).first()
    session.close()
    if not art:
        return JSONResponse({"code": 1, "msg": "文章不存在"})
    return JSONResponse({"code": 0, "data": art.to_dict()})


@router.delete("/articles/{article_id}")
async def delete_article(article_id: str):
    """删除单篇文章"""
    db = get_db()
    success = db.delete_article(article_id)
    if success:
        return JSONResponse({"code": 0, "msg": "删除成功"})
    return JSONResponse({"code": 1, "msg": "删除失败，文章不存在"})


@router.get("/articles/export")
async def export_articles(ids: str = "", mp_name: str = ""):
    """导出文章为 Excel，支持按公众号过滤"""
    db = get_db()

    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return JSONResponse({"code": 1, "msg": "openpyxl 未安装"})

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

    session = db.get_session()
    query = session.query(Article)
    if ids:
        id_list = [i.strip() for i in ids.split(",") if i.strip()]
        query = query.filter(Article.id.in_(id_list)) if id_list else query
    if mp_name:
        query = query.filter(Article.mp_name == mp_name)
    articles = query.order_by(Article.created_at.desc()).all()

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