import streamlit as st
import pandas as pd
import plotly.express as px
import uuid
import json
from db_utils import (
    get_engine,
    get_table_names,
    save_dashboard,
    get_dashboard_names,
    load_dashboard,
    table_exists
)

# --- ページ設定とセッション状態の初期化 ---
st.set_page_config(page_title="データ分析", layout="wide")

def init_session_state():
    """セッション状態を初期化する"""
    defaults = {
        'main_df': None,
        'filtered_df': None,
        'selected_table_key': '---',
        'loaded_table_name': None,
        'dashboard_widgets': [],
        'show_widget_dialog': False,
        'selected_dashboard_key': '---'
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- データロードとUIコンポーネント ---

def load_data_source(table_name):
    """指定されたテーブルからデータを読み込む"""
    if not table_name or table_name == '---':
        return

    st.session_state.loaded_table_name = table_name
    try:
        with st.spinner(f"テーブル '{table_name}' を読み込んでいます..."):
            if not table_exists(table_name):
                st.error(f"エラー: テーブル '{table_name}' がデータベースに存在しません。")
                st.session_state.main_df = st.session_state.filtered_df = None
                return

            engine = get_engine()
            df = pd.read_sql_table(table_name, engine)
            st.session_state.main_df = df
            st.session_state.filtered_df = df.copy()
            st.success(f"データソース '{table_name}' を読み込みました。")
    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生しました: {e}")
        st.session_state.main_df = st.session_state.filtered_df = None
        st.session_state.loaded_table_name = None
    st.rerun()

def display_controls():
    """ページ上部のコントロールUI（データ選択、ダッシュボード操作）を表示する"""
    st.title("📈 分析ダッシュボード")
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            display_data_source_selector()
        with c2:
            display_dashboard_loader()

    with st.container(border=True):
        c1, c2, c3 = st.columns([2, 2, 1])
        with c1:
            display_dashboard_saver()
        with c2:
            display_csv_exporter()
        with c3:
            is_disabled = st.session_state.main_df is None
            if st.button("＋ ウィジェットを追加", type="primary", use_container_width=True, disabled=is_disabled):
                st.session_state.show_widget_dialog = True

def display_data_source_selector():
    """データソース選択のUI"""
    table_names = [name for name in get_table_names() if not name.startswith('_')]
    options = ["---"] + table_names

    def on_table_change():
        st.session_state.selected_dashboard_key = '---'
        st.session_state.dashboard_widgets = []

    st.selectbox("1. 分析データソースを選択", options, key='selected_table_key', on_change=on_table_change)

def display_dashboard_loader():
    """保存済みダッシュボードを読み込むUI"""
    dashboard_names = get_dashboard_names()
    load_options = ["---"] + dashboard_names

    def on_dashboard_load():
        name = st.session_state.selected_dashboard_key
        if name != "---":
            layout = load_dashboard(name)
            if layout and 'table_name' in layout:
                st.session_state.selected_table_key = layout['table_name']
                st.session_state.dashboard_widgets = layout.get('widgets', [])
            else:
                st.error("ダッシュボードの読み込みに失敗しました。")

    st.selectbox("2. または、保存済みダッシュボードを読み込む", load_options, key='selected_dashboard_key', on_change=on_dashboard_load)

def display_dashboard_saver():
    """ダッシュボード保存のUI"""
    if st.session_state.dashboard_widgets:
        with st.form(key="save_dashboard_form"):
            dashboard_name = st.text_input("現在のレイアウトを保存", placeholder="ダッシュボード名を入力")
            if st.form_submit_button("保存") and dashboard_name:
                layout = {"table_name": st.session_state.loaded_table_name, "widgets": st.session_state.dashboard_widgets}
                save_dashboard(dashboard_name, layout)
                st.success(f"ダッシュボード '{dashboard_name}' を保存しました。")

def display_csv_exporter():
    """CSVエクスポートのUI"""
    is_disabled = st.session_state.filtered_df is None
    csv_data = st.session_state.filtered_df.to_csv(index=False).encode('utf-8') if not is_disabled else ""
    file_name = f"{st.session_state.loaded_table_name}_filtered.csv" if not is_disabled else "data.csv"
    st.download_button("フィルター後データをエクスポート", csv_data, file_name, 'text/csv', use_container_width=True, disabled=is_disabled)

def display_sidebar():
    """サイドバーのグローバルフィルターを表示する"""
    with st.sidebar:
        st.title("グローバルフィルター")
        if st.session_state.main_df is None:
            st.info("データソースを選択すると、ここにフィルターが表示されます。")
            return

        df = st.session_state.main_df
        filtered_df = df.copy()

        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                min_v, max_v = df[col].min(), df[col].max()
                val = st.date_input(f"{col}", (min_v, max_v), min_value=min_v, max_value=max_v, key=f"d_{col}")
                if len(val) == 2: filtered_df = filtered_df[filtered_df[col].dt.date.between(*val)]
            elif pd.api.types.is_numeric_dtype(df[col]) and df[col].nunique() > 10:
                min_v, max_v = float(df[col].min()), float(df[col].max())
                val = st.slider(f"{col}", min_v, max_v, (min_v, max_v), key=f"s_{col}")
                filtered_df = filtered_df[filtered_df[col].between(*val)]
            elif df[col].nunique() < 50:
                opts = df[col].unique()
                val = st.multiselect(f"{col}", opts, default=opts, key=f"m_{col}")
                filtered_df = filtered_df[filtered_df[col].isin(val)]

        st.session_state.filtered_df = filtered_df

def display_dashboard():
    """メインコンテンツエリアにダッシュボードウィジェットを描画する"""
    if st.session_state.filtered_df is None:
        st.info("分析を開始するには、ページ上部のドロップダウンからデータソースを選択してください。")
        return

    if not st.session_state.dashboard_widgets:
        st.info("「＋ ウィジェットを追加」ボタンから、表示するグラフやKPIを追加してください。")
        return

    num = len(st.session_state.dashboard_widgets)
    cols = st.columns(min(num, 3))

    for i, config in enumerate(st.session_state.dashboard_widgets):
        with cols[i % 3]:
            render_widget(config, i)

def render_widget(config, index):
    """個別のウィジェットコンテナと中身を描画する"""
    with st.container(border=True):
        st.subheader(config.get("title", "無題のウィジェット"))
        df = st.session_state.filtered_df

        # カラム存在チェック
        required_cols = [config.get(k) for k in ['column', 'x_axis', 'y_axis', 'z_axis', 'names', 'values', 'color', 'size'] if config.get(k)]
        if not all(col in df.columns for col in required_cols):
            st.error("エラー: 必要なカラムがデータ内に見つかりません。")
            return

        try:
            fig = None
            widget_type = config["type"]
            if widget_type == "KPIカード":
                value = df[config["column"]].agg(config["agg_func"])
                st.metric(label=f"{config['column']} ({config['agg_func']})", value=f"{value:,.2f}")
            elif widget_type == "棒グラフ":
                grouped = df.groupby(config["x_axis"])[config["y_axis"]].agg(config["agg_func"]).reset_index()
                fig = px.bar(grouped, x=config["x_axis"], y=config["y_axis"], color=config.get("color"))
            elif widget_type == "折れ線グラフ":
                fig = px.line(df, x=config["x_axis"], y=config["y_axis"], color=config.get("color"))
            elif widget_type == "散布図":
                fig = px.scatter(df, x=config["x_axis"], y=config["y_axis"], color=config.get("color"), size=config.get("size"))
            elif widget_type == "円グラフ":
                fig = px.pie(df, names=config["names"], values=config["values"])
            elif widget_type == "ヒストグラム":
                fig = px.histogram(df, x=config["x_axis"], nbins=config.get("nbins", 20))
            elif widget_type == "箱ひげ図":
                fig = px.box(df, x=config.get("x_axis"), y=config["y_axis"], color=config.get("color"))
            elif widget_type == "ヒートマップ":
                pivot = df.pivot_table(index=config["y_axis"], columns=config["x_axis"], values=config["z_axis"], aggfunc='mean')
                fig = px.imshow(pivot)

            if fig:
                st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"グラフ描画エラー: {e}")

        if st.button("削除", key=f"del_{config['id']}", type="secondary", use_container_width=True):
            st.session_state.dashboard_widgets.pop(index)
            st.rerun()

@st.dialog("ウィジェット設定")
def widget_dialog():
    """ウィジェット追加・設定用のダイアログ"""
    st.subheader("新しいウィジェットを追加")
    df = st.session_state.main_df
    numeric = df.select_dtypes('number').columns.tolist()
    categorical = df.select_dtypes(['object', 'category']).columns.tolist()
    datetime = df.select_dtypes(['datetime', 'datetimetz']).columns.tolist()
    all_cols = df.columns.tolist()

    w_type = st.selectbox("ウィジェットの種類を選択", ["KPIカード", "棒グラフ", "折れ線グラフ", "散布図", "円グラフ", "ヒストグラム", "箱ひげ図", "ヒートマップ"])
    cfg = {"type": w_type, "id": str(uuid.uuid4()), "title": st.text_input("タイトル")}

    if w_type == "KPIカード":
        if not numeric: st.error("このグラフには数値カラムが必要です。"); return
        cfg["column"] = st.selectbox("対象カラム", numeric)
        cfg["agg_func"] = st.selectbox("集計方法", ["sum", "mean", "median", "count", "nunique"])

    elif w_type == "棒グラフ":
        if not numeric or not categorical: st.error("このグラフには数値カラムとカテゴリカルカラムが両方必要です。"); return
        cfg["x_axis"] = st.selectbox("X軸 (カテゴリ)", categorical)
        cfg["y_axis"] = st.selectbox("Y軸 (数値)", numeric)
        cfg["agg_func"] = st.selectbox("Y軸の集計方法", ["sum", "mean", "count"])
        cfg["color"] = st.selectbox("色分け (オプション)", [None] + categorical)

    elif w_type == "折れ線グラフ":
        if not numeric: st.error("このグラフにはY軸となる数値カラムが必要です。"); return
        cfg["x_axis"] = st.selectbox("X軸", datetime + numeric + categorical)
        cfg["y_axis"] = st.selectbox("Y軸", numeric)
        cfg["color"] = st.selectbox("色分け (オプション)", [None] + categorical)

    elif w_type == "散布図":
        if len(numeric) < 2: st.error("このグラフにはX軸・Y軸となる数値カラムが2つ以上必要です。"); return
        cfg["x_axis"] = st.selectbox("X軸", numeric)
        cfg["y_axis"] = st.selectbox("Y軸", numeric)
        cfg["color"] = st.selectbox("色分け (オプション)", [None] + categorical)
        cfg["size"] = st.selectbox("サイズ (オプション)", [None] + numeric)

    elif w_type == "円グラフ":
        if not numeric or not categorical: st.error("このグラフには数値カラムとカテゴリカルカラムが両方必要です。"); return
        cfg["names"] = st.selectbox("ラベル", categorical)
        cfg["values"] = st.selectbox("値", numeric)

    elif w_type == "ヒストグラム":
        if not numeric: st.error("このグラフには数値カラムが必要です。"); return
        cfg["x_axis"] = st.selectbox("対象カラム", numeric)
        cfg["nbins"] = st.number_input("ビンの数", min_value=5, value=20)

    elif w_type == "箱ひげ図":
        if not numeric: st.error("このグラフにはY軸となる数値カラムが必要です。"); return
        cfg["x_axis"] = st.selectbox("X軸 (カテゴリ)", [None] + categorical)
        cfg["y_axis"] = st.selectbox("Y軸 (数値)", numeric)
        cfg["color"] = st.selectbox("色分け (オプション)", [None] + categorical)

    elif w_type == "ヒートマップ":
        if len(categorical) < 2 or not numeric: st.error("このグラフには2つ以上のカテゴリカルカラムと1つ以上の数値カラムが必要です。"); return
        cfg["x_axis"] = st.selectbox("X軸", categorical)
        cfg["y_axis"] = st.selectbox("Y軸", categorical)
        cfg["z_axis"] = st.selectbox("Z値 (集計対象)", numeric)

    if st.button("追加"):
        st.session_state.dashboard_widgets.append(cfg)
        st.session_state.show_widget_dialog = False
        st.rerun()

# --- メイン実行ブロック ---
if __name__ == "__main__":
    init_session_state()
    display_controls()

    # データソース選択の変更を検知してデータロード
    if st.session_state.selected_table_key != st.session_state.get('loaded_table_name'):
        load_data_source(st.session_state.selected_table_key)

    display_sidebar()
    st.markdown("---")
    display_dashboard()

    if st.session_state.show_widget_dialog:
        widget_dialog()