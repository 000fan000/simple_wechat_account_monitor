"""
SQLite 数据库模块 + Article 模型
"""
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, BigInteger, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Article(Base):
    __tablename__ = 'articles'

    id = Column(String(255), primary_key=True)
    title = Column(String(1000))
    author = Column(String(255))
    url = Column(String(500), unique=True)
    pic_url = Column(String(500))
    description = Column(Text)
    content = Column(Text)
    content_text = Column(Text)
    publish_time = Column(Integer)
    mp_name = Column(String(255))
    mp_id = Column(String(255))
    has_content = Column(Integer, default=0)
    is_favorite = Column(Integer, default=0)
    created_at = Column(DateTime)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'title': self.title,
            'author': self.author,
            'url': self.url,
            'pic_url': self.pic_url,
            'description': self.description,
            'content': self.content,
            'content_text': self.content_text,
            'publish_time': self.publish_time,
            'mp_name': self.mp_name,
            'mp_id': self.mp_id,
            'has_content': self.has_content,
            'is_favorite': self.is_favorite,
            'created_at': self.created_at.isoformat() if self.created_at and hasattr(self.created_at, "isoformat") else None,
        }


class Db:
    def __init__(self, connection_str: str = "sqlite:///data/articles.db", tag: str = "DB"):
        self.connection_str = connection_str
        self.tag = tag
        self.Session = None
        self.engine = None
        self.session_factory = None
        self.init(connection_str)

    def init(self, con_str: str) -> None:
        try:
            self.connection_str = con_str

            if con_str.startswith('sqlite:///'):
                db_path = con_str[10:]
                if db_path:
                    os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else '.', exist_ok=True)
                    if not os.path.exists(db_path):
                        open(db_path, 'w').close()

            connect_args = {}
            if con_str.startswith('sqlite:///'):
                connect_args = {"check_same_thread": False}

            self.engine = create_engine(
                con_str,
                pool_size=2,
                max_overflow=20,
                pool_timeout=30,
                echo=False,
                pool_recycle=60,
                isolation_level="AUTOCOMMIT",
                connect_args=connect_args
            )

            @event.listens_for(self.engine, "connect")
            def set_sqlite_text_factory(dbapi_conn, connection_record):
                dbapi_conn.text_factory = lambda x: x.decode('utf-8', errors='replace')

            self.session_factory = sessionmaker(bind=self.engine, autoflush=True, expire_on_commit=True, future=True)
            self.ensure_columns()
        except Exception as e:
            print(f"[{self.tag}] 数据库初始化失败: {e}")
            raise

    def ensure_columns(self):
        try:
            inspector = inspect(self.engine)
            if "articles" not in inspector.get_table_names():
                Base.metadata.create_all(self.engine)
                return

            columns = {column["name"] for column in inspector.get_columns("articles")}
            alter_statements = []

            if "author" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN author TEXT")
            if "content_text" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN content_text TEXT")
            if "mp_name" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN mp_name TEXT")
            if "mp_id" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN mp_id TEXT")
            if "has_content" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN has_content INTEGER DEFAULT 0")
            if "is_favorite" not in columns:
                alter_statements.append("ALTER TABLE articles ADD COLUMN is_favorite INTEGER DEFAULT 0")

            if alter_statements:
                with self.engine.begin():
                    for stmt in alter_statements:
                        try:
                            self.engine.execute(text(stmt))
                        except Exception:
                            pass

        except Exception as e:
            print(f"[{self.tag}] 检查表结构失败: {e}")

    def get_session(self):
        def _session():
            self.Session = scoped_session(self.session_factory)
            return self.Session

        if self.Session is None:
            _session()

        session = self.Session()
        if not session.is_active:
            _session()
            session = self.Session()

        try:
            session.query(Article.id).count()
        except Exception:
            self.init(self.connection_str)
            _session()
            session = self.Session()

        return session

    def add_article(self, article_data: dict, check_exist: bool = True) -> bool:
        session = None
        try:
            session = self.get_session()

            article_id = article_data.get('id', '')
            url = article_data.get('url', '')

            if check_exist and url:
                existing = session.query(Article).filter(Article.url == url).first()
                if existing:
                    if article_data.get('title') == existing.title and article_data.get('content') == existing.content:
                        return False

                    for key, value in article_data.items():
                        if key not in ['id', 'created_at']:
                            setattr(existing, key, value)

                    existing.created_at = existing.created_at or datetime.now()
                    session.commit()
                    return True

            art = Article(**article_data)
            art.created_at = datetime.now()
            session.add(art)
            session.commit()
            return True

        except Exception as e:
            if session:
                session.rollback()
            if "UNIQUE" in str(e):
                return False
            print(f"[{self.tag}] 添加文章失败: {e}")
            return False
        finally:
            if session is not None:
                session.close()

    def get_articles(self, page: int = 1, size: int = 20, search: str = "") -> Dict[str, Any]:
        session = None
        try:
            session = self.get_session()
            query = session.query(Article)

            if search:
                search_pattern = f"%{search}%"
                query = query.filter(
                    (Article.title.like(search_pattern)) |
                    (Article.description.like(search_pattern)) |
                    (Article.mp_name.like(search_pattern))
                )

            total = query.count()
            offset = (page - 1) * size
            articles = query.order_by(Article.created_at.desc()).offset(offset).limit(size).all()

            return {
                "items": [a.to_dict() for a in articles],
                "total": total,
                "page": page,
                "size": size,
                "pages": (total + size - 1) // size
            }

        except Exception as e:
            print(f"[{self.tag}] 查询文章失败: {e}")
            return {"items": [], "total": 0, "page": page, "size": size, "pages": 0}
        finally:
            if session is not None:
                session.close()

    def delete_article(self, article_id: str) -> bool:
        session = None
        try:
            session = self.get_session()
            article = session.query(Article).filter(Article.id == article_id).first()
            if article:
                session.delete(article)
                session.commit()
                return True
            return False
        except Exception as e:
            print(f"[{self.tag}] 删除文章失败: {e}")
            return False
        finally:
            if session is not None:
                session.close()

    def get_article_by_url(self, url: str) -> Optional[Article]:
        session = None
        try:
            session = self.get_session()
            return session.query(Article).filter(Article.url == url).first()
        except Exception:
            return None
        finally:
            if session is not None:
                session.close()

    def close(self) -> None:
        if self.Session:
            self.Session.remove()


DB = None


def get_db() -> Db:
    global DB
    if DB is None:
        from config import cfg
        connection_str = cfg.get("db.connection", "sqlite:///data/articles.db")
        DB = Db(connection_str)
    return DB


def init_db(connection_str: str = "sqlite:///data/articles.db") -> Db:
    global DB
    DB = Db(connection_str)
    return DB