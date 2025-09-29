import streamlit as st
from sqlalchemy import create_engine, inspect, text
import pandas as pd
import json

DB_FILE = "database.db"
DB_URI = f"sqlite:///{DB_FILE}"

@st.cache_resource
def get_engine():
    """
    SQLAlchemyのエンジンをシングルトンとして作成し、返します。
    Streamlitのキャッシュ機能を利用して、アプリケーション全体で単一の接続を共有します。
    """
    return create_engine(DB_URI, echo=False)

def get_table_names():
    """
    データベース内に存在するすべてのテーブル名のリストを取得します。
    """
    engine = get_engine()
    try:
        with engine.connect() as connection:
            inspector = inspect(engine)
            return inspector.get_table_names()
    except Exception:
        return []

def execute_query(query_str: str):
    """
    SQLクエリ（特にDDL）を実行します。
    """
    engine = get_engine()
    with engine.connect() as connection:
        with connection.begin(): # トランザクションを開始
            connection.execute(text(query_str))

def get_table_preview(table_name: str, limit=10) -> pd.DataFrame:
    """
    指定されたテーブルの先頭N行をDataFrameとして取得します。
    """
    engine = get_engine()
    return pd.read_sql_query(f"SELECT * FROM \"{table_name}\" LIMIT {limit}", engine)

def table_exists(table_name):
    """
    指定されたテーブルがデータベースに存在するかどうかを確認します。
    """
    return table_name in get_table_names()

def init_dashboard_table():
    """
    ダッシュボード保存用の `_dashboards` テーブルがなければ作成する。
    """
    engine = get_engine()
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("""
            CREATE TABLE IF NOT EXISTS _dashboards (
                name TEXT PRIMARY KEY,
                layout TEXT NOT NULL
            )
            """))

def save_dashboard(name: str, layout: list):
    """
    ダッシュボードのレイアウトをJSONとしてDBに保存または上書きする。
    """
    engine = get_engine()
    layout_json = json.dumps(layout)
    with engine.connect() as connection:
        with connection.begin():
            # UPSERT (INSERT OR REPLACE)
            connection.execute(
                text("INSERT OR REPLACE INTO _dashboards (name, layout) VALUES (:name, :layout)"),
                {"name": name, "layout": layout_json}
            )

def get_dashboard_names() -> list[str]:
    """
    保存されているすべてのダッシュボードの名前を取得する。
    """
    init_dashboard_table() # テーブルがなければ作成
    engine = get_engine()
    with engine.connect() as connection:
        result = connection.execute(text("SELECT name FROM _dashboards ORDER BY name"))
        return [row[0] for row in result]

def load_dashboard(name: str) -> list:
    """
    指定された名前のダッシュボードのレイアウトを読み込む。
    """
    engine = get_engine()
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT layout FROM _dashboards WHERE name = :name"),
            {"name": name}
        ).scalar_one_or_none()
        if result:
            return json.loads(result)
        return []