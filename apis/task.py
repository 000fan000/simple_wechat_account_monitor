"""
账号任务管理 API
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

from db import get_db, Article
from driver.wx_api import get_mpsweb, extract_biz_from_url, extract_fakeid_from_html, biz_to_fakeid
from driver.scheduler import get_all_tasks, save_task, delete_task
from driver.scheduler import get_all_tasks as scheduler_get_all

router = APIRouter(prefix="/api", tags=["task"])


@router.get("/tasks")
async def list_tasks():
    """获取所有账号任务配置 + 统计数据"""
    # 自动同步 accounts.json 中的账号到任务列表
    _sync_accounts_to_tasks()

    _sync_accounts_to_tasks()
    tasks = scheduler_get_all()
    db = get_db()
    session = db.get_session()
    from sqlalchemy import func
    rows = session.query(Article.mp_name, func.count(Article.id)).filter(
        Article.mp_name != '', Article.mp_name.isnot(None)
    ).group_by(Article.mp_name).all()
    session.close()
    stats = {name: count for name, count in rows}

    for t in tasks:
        name = t.get('mp_name', '')
        t['article_count'] = stats.get(name, 0)

    return JSONResponse({"code": 0, "data": {"tasks": tasks, "total": len(tasks)}})


def _sync_accounts_to_tasks():
    acc_file = os.path.join("data", "accounts.json")
    if not os.path.exists(acc_file):
        return
    try:
        with open(acc_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except:
        return
    existing = scheduler_get_all()
    existing_fakeids = {t.get('fakeid') for t in existing}
    for acc in accounts:
        fakeid = acc.get('fakeid', '')
        if fakeid and fakeid not in existing_fakeids:
            save_task({"fakeid": fakeid, "mp_name": acc.get('mp_name', ''), "cron": "", "enabled": False, "max_pages": 3})

    for t in tasks:
        name = t.get('mp_name', '')
        t['article_count'] = stats.get(name, 0)

    return JSONResponse({"code": 0, "data": {"tasks": tasks, "total": len(tasks)}})


def _sync_accounts_to_tasks():
    """从 accounts.json 导入账号到 tasks.json（如果 tasks 中不存在）"""
    acc_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "accounts.json")
    if not os.path.exists(acc_file):
        return
    try:
        with open(acc_file, 'r', encoding='utf-8') as f:
            accounts = json.load(f)
    except:
        return
    existing = scheduler_get_all()
    existing_fakeids = {t.get('fakeid') for t in existing}
    for acc in accounts:
        fakeid = acc.get('fakeid', '')
        if fakeid and fakeid not in existing_fakeids:
            save_task({
                "fakeid": fakeid,
                "mp_name": acc.get('mp_name', ''),
                "cron": "",
                "enabled": False,
                "max_pages": 3,
            })


class SaveTaskRequest(BaseModel):
    fakeid: str
    mp_name: str = ""
    cron: str = ""
    enabled: bool = False
    max_pages: int = 3


@router.post("/tasks/save")
async def save_task_endpoint(req: SaveTaskRequest):
    """保存/更新某个账号的任务配置"""
    if not req.fakeid:
        return JSONResponse({"code": 1, "msg": "fakeid 为空"})
    task = save_task({
        "fakeid": req.fakeid,
        "mp_name": req.mp_name,
        "cron": req.cron,
        "enabled": req.enabled,
        "max_pages": req.max_pages,
    })
    return JSONResponse({"code": 0, "msg": "保存成功", "data": task})


@router.post("/tasks/{fakeid}/run")
async def run_task(fakeid: str, mp_name: str = "", max_pages: int = 3):
    """手动触发立即回采"""
    from apis.article import fetch_by_account_raw
    try:
        success, count, msg = await fetch_by_account_raw(fakeid, mp_name, max_pages)
        return JSONResponse({
            "code": 0 if success else 1,
            "msg": msg,
            "data": {"success": success, "count": count}
        })
    except Exception as e:
        return JSONResponse({"code": 1, "msg": str(e)})


@router.post("/tasks/{fakeid}/delete")
async def delete_task_endpoint(fakeid: str):
    """移除账号及任务"""
    ok = delete_task(fakeid)
    if ok:
        return JSONResponse({"code": 0, "msg": "已移除"})
    return JSONResponse({"code": 1, "msg": "账号不存在"})
