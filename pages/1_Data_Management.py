import streamlit as st
import pandas as pd
import os
import re
from db_utils import (
    get_engine,
    get_table_names,
    execute_query,
    get_table_preview,
    table_exists
)

st.set_page_config(page_title="データ管理", layout="wide")
st.title("📊 データ管理")
st.markdown("---")

# --- セッション状態の初期化 ---
def init_session_state():
    defaults = {
        'uploaded_df': None,
        'processed_df': None,
        'table_name': "",
        'preprocessing_settings': {},
        'new_upload': False,
        'encoding': 'utf-8'
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

# --- UIコンポーネント関数 ---

def display_file_uploader():
    """ファイルアップロードUIを表示し、アップロードされたファイルを処理する"""
    with st.container(border=True):
        st.header("1. データのアップロード")
        st.info("分析したいCSVまたはExcelファイルをアップロードしてください。")

        def set_new_upload_flag():
            st.session_state.new_upload = True

        uploaded_file = st.file_uploader(
            "ファイルを選択", type=['csv', 'xlsx'], label_visibility="collapsed", on_change=set_new_upload_flag
        )

        # CSVがアップロードされた場合のみエンコーディング選択肢を表示
        if uploaded_file and uploaded_file.name.endswith('.csv'):
            st.selectbox(
                "CSVファイルのエンコーディング:",
                ('utf-8', 'shift-jis', 'cp932'),
                key='encoding',
                on_change=set_new_upload_flag
            )

        if uploaded_file and st.session_state.new_upload:
            try:
                with st.spinner("ファイルを読み込んでいます..."):
                    uploaded_file.seek(0)
                    if uploaded_file.name.endswith('.csv'):
                        df = pd.read_csv(uploaded_file, encoding=st.session_state.encoding)
                    else:
                        df = pd.read_excel(uploaded_file)

                    # 状態をリセット
                    st.session_state.uploaded_df = df
                    st.session_state.processed_df = df.copy()
                    st.session_state.table_name = os.path.splitext(uploaded_file.name)[0]
                    st.session_state.preprocessing_settings = {
                        col: {'dtype': str(df[col].dtype), 'missing_values': '何もしない'} for col in df.columns
                    }
                    st.session_state.new_upload = False
                    st.success(f"ファイル「{uploaded_file.name}」を正常に読み込みました。")
                    st.rerun()

            except UnicodeDecodeError:
                st.error(f"エンコーディング '{st.session_state.encoding}' でファイルをデコードできませんでした。正しいエンコーディングを選択してください。")
                st.session_state.new_upload = True # エラーが出ても再試行できるようにフラグを立てておく
                st.session_state.uploaded_df = None # エラーが出たらDFをクリア
                st.session_state.processed_df = None
            except Exception as e:
                st.error(f"ファイルの読み込み中にエラーが発生しました: {e}")
                for key in ['uploaded_df', 'processed_df', 'table_name', 'new_upload']:
                    st.session_state[key] = None

def display_preprocessing_ui():
    """データ前処理のUIを表示・処理する"""
    if st.session_state.processed_df is None:
        return

    with st.container(border=True):
        st.header("2. データの前処理 (オプション)")
        st.markdown("データの型を変更したり、欠損値の処理方法を指定できます。")

        df = st.session_state.processed_df
        st.dataframe(df.head(50))
        st.markdown("---")
        st.subheader("カラムごとの設定")

        settings = st.session_state.preprocessing_settings
        for col in df.columns:
            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 3])
            with c1: st.write(f"**{col}**")
            with c2: st.write(f"`{df[col].dtype}`")
            with c3: st.write(f"欠損: {df[col].isnull().sum()}件")

            dtype_options = ['object', 'int64', 'float64', 'datetime64']
            current_dtype = str(df[col].dtype)
            if current_dtype not in dtype_options: dtype_options.insert(0, current_dtype)
            with c4:
                settings[col]['dtype'] = st.selectbox("データ型", dtype_options, index=dtype_options.index(current_dtype), key=f"dtype_{col}")

            missing_options = ['何もしない', '行ごと削除', '0で埋める']
            if pd.api.types.is_numeric_dtype(df[col]):
                missing_options.extend(['平均値で埋める', '中央値で埋める'])
            with c5:
                settings[col]['missing_values'] = st.selectbox("欠損値処理", missing_options, key=f"missing_{col}")

        if st.button("前処理を適用", type="primary"):
            apply_preprocessing(settings)

def apply_preprocessing(settings):
    """設定に基づいてデータ前処理を実行する"""
    with st.spinner("前処理を実行中です..."):
        df = st.session_state.uploaded_df.copy()
        for col, options in settings.items():
            if options['missing_values'] == '行ごと削除': df.dropna(subset=[col], inplace=True)
            elif options['missing_values'] == '0で埋める': df[col].fillna(0, inplace=True)
            elif options['missing_values'] == '平均値で埋める': df[col].fillna(df[col].mean(), inplace=True)
            elif options['missing_values'] == '中央値で埋める': df[col].fillna(df[col].median(), inplace=True)
            try:
                target_dtype = options['dtype']
                if str(df[col].dtype) != target_dtype:
                    df[col] = pd.to_datetime(df[col], errors='coerce') if target_dtype == 'datetime64' else df[col].astype(target_dtype)
            except Exception as e:
                st.warning(f"カラム '{col}' の型変換に失敗: {e}")
        st.session_state.processed_df = df
    st.success("前処理が適用されました。")
    st.rerun()

def display_save_to_db_ui():
    """データベースへの保存UIを表示・処理する"""
    if st.session_state.processed_df is None:
        return

    with st.container(border=True):
        st.header("3. データベースへの保存")
        df_to_save = st.session_state.processed_df

        table_name_input = st.text_input("テーブル名", value=st.session_state.table_name)
        st.session_state.table_name = table_name_input.strip()

        is_valid_name = re.match(r"^[a-zA-Z0-9_]+$", st.session_state.table_name)
        if not is_valid_name:
            st.error("テーブル名には英数字とアンダースコア(_)のみ使用できます。")
            return

        exists = table_exists(st.session_state.table_name)
        if exists:
            st.warning(f"テーブル '{st.session_state.table_name}' は既に存在します。上書きしますか？")
            if st.button("上書き保存する", type="primary"):
                save_dataframe(df_to_save, st.session_state.table_name, if_exists='replace')
        else:
            if st.button("データベースに保存", type="primary"):
                save_dataframe(df_to_save, st.session_state.table_name, if_exists='fail')

def save_dataframe(df, name, if_exists):
    """DataFrameをデータベースに保存する"""
    try:
        with st.spinner(f"テーブル '{name}' を保存しています..."):
            engine = get_engine()
            df.to_sql(name, engine, if_exists=if_exists, index=False)
        st.success(f"テーブル '{name}' を正常に保存しました。")
        st.rerun()
    except Exception as e:
        st.error(f"データベースへの保存中にエラーが発生しました: {e}")

def display_table_management_ui():
    """保存済みテーブルの管理UIを表示する"""
    with st.container(border=True):
        st.header("4. 保存済みテーブルの管理")
        table_names = [name for name in get_table_names() if not name.startswith('_')]

        if not table_names:
            st.info("現在、データベースに保存されているテーブルはありません。")
            return

        for table in table_names:
            with st.container(border=True):
                c1, c2, c3 = st.columns([4, 1, 1])
                with c1: st.subheader(f"`{table}`")
                with c2:
                    if st.button("プレビュー", key=f"preview_{table}"):
                        st.session_state[f"show_preview_{table}"] = not st.session_state.get(f"show_preview_{table}", False)
                with c3:
                    if st.button("削除", key=f"delete_{table}", type="secondary"):
                        st.session_state[f"confirm_delete_{table}"] = True

                if st.session_state.get(f"confirm_delete_{table}"):
                    st.warning(f"本当にテーブル `{table}` を削除しますか？この操作は取り消せません。")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("はい、削除します", key=f"confirm_del_btn_{table}", type="primary"):
                        delete_table(table)
                    if cc2.button("キャンセル", key=f"cancel_del_btn_{table}"):
                        st.session_state[f"confirm_delete_{table}"] = False
                        st.rerun()

                if st.session_state.get(f"show_preview_{table}"):
                    display_table_preview(table)

def delete_table(table_name):
    """テーブルを削除する"""
    try:
        execute_query(f'DROP TABLE "{table_name}"')
        st.success(f"テーブル '{table_name}' を削除しました。")
        # 状態をクリアしてリロード
        st.session_state[f"confirm_delete_{table_name}"] = False
        st.rerun()
    except Exception as e:
        st.error(f"テーブル '{table_name}' の削除中にエラーが発生しました: {e}")

def display_table_preview(table_name):
    """テーブルのプレビューを表示する"""
    with st.expander("テーブルプレビュー", expanded=True):
        try:
            preview_df = get_table_preview(table_name)
            st.dataframe(preview_df)
            st.write("**カラムのデータ型:**")
            st.table(preview_df.dtypes.astype(str).rename("データ型"))
        except Exception as e:
            st.error(f"プレビューの読み込み中にエラーが発生しました: {e}")

# --- メイン実行ブロック ---
if __name__ == "__main__":
    init_session_state()
    display_file_uploader()
    display_preprocessing_ui()
    display_save_to_db_ui()
    st.markdown("---")
    display_table_management_ui()