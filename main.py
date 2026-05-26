import os
import sys

os.makedirs("data", exist_ok=True)
os.makedirs("static", exist_ok=True)

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jinja2 import Environment, FileSystemLoader
import uvicorn

from db import init_db, get_db
from apis.article import router as article_router
from config import cfg


app = FastAPI(title="微信公众号文章采集", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(article_router)


@app.on_event("startup")
async def startup():
    connection_str = cfg.get("db.connection", "sqlite:///data/articles.db")
    init_db(connection_str)
    print("[启动] 数据库初始化完成")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=cfg.get("server.host", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=cfg.get("server.port", 8000))
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    print(f"[启动] 服务地址: http://{args.host}:{args.port}")
    uvicorn.run("main:app", host=args.host, port=args.port, reload=args.reload)