import re
from playwright.sync_api import sync_playwright, Page, expect
import time

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    try:
        # Base URL for the Streamlit app
        base_url = "http://localhost:8501"

        # 1. Go to Data Management page and upload data
        print("Navigating to Data Management page...")
        page.goto(f"{base_url}/Data_Management", timeout=60000)

        print("Uploading sample_data.csv...")
        # 1. Upload file and verify the result
        page.locator('input[type="file"]').first.set_input_files('sample_data.csv')
        # Wait for the preprocessing section to appear, which confirms the upload and rerun
        expect(page.get_by_role("heading", name="2. データの前処理 (オプション)")).to_be_visible(timeout=20000)
        print("File uploaded successfully.")

        # 2. Set table name and save to DB
        table_name_input = page.get_by_label("テーブル名")
        expect(table_name_input).to_have_value(re.compile("sample_data"))
        table_name_input.fill("sales_data")

        page.get_by_role("button", name="データベースに保存").click()

        # 3. Verify save by checking for the table in the management list
        # This is the most robust check, as it waits for the final, persistent state.
        saved_table_heading = page.get_by_role("heading", name="`sales_data`")
        expect(saved_table_heading).to_be_visible(timeout=20000)
        print("Table saved successfully.")

        # 4. Go to Data Analysis page
        print("Navigating to Data Analysis page...")
        # Use get_by_text for sidebar link as roles can be tricky in Streamlit
        page.get_by_text("データ分析", exact=True).click()
        expect(page.get_by_role("heading", name="分析ダッシュボード")).to_be_visible(timeout=15000)

        # 5. Select the data source
        print("Selecting 'sales_data' as data source...")
        page.get_by_label("1. 分析データソースを選択").select_option("sales_data")
        expect(page.get_by_text("データソース 'sales_data' を読み込みました。")).to_be_visible(timeout=15000)
        print("Data source selected.")

        # 6. Add a bar chart widget
        print("Adding a bar chart widget...")
        page.get_by_role("button", name="＋ ウィジェットを追加").click()

        dialog = page.locator('div[data-testid="stDialog"]')
        expect(dialog).to_be_visible()

        dialog.get_by_label("ウィジェットの種類を選択").select_option("棒グラフ")
        dialog.get_by_label("タイトル").fill("Revenue by Region")
        dialog.get_by_label("X軸 (カテゴリ)").select_option("Region")
        dialog.get_by_label("Y軸 (数値)").select_option("Revenue")
        dialog.get_by_label("Y軸の集計方法").select_option("sum")

        dialog.get_by_role("button", name="追加").click()
        expect(dialog).not_to_be_visible()
        expect(page.get_by_role("heading", name="Revenue by Region")).to_be_visible(timeout=10000)
        print("Bar chart added.")

        # 7. Add a KPI card widget
        print("Adding a KPI card widget...")
        page.get_by_role("button", name="＋ ウィジェットを追加").click()

        dialog = page.locator('div[data-testid="stDialog"]')
        expect(dialog).to_be_visible()

        dialog.get_by_label("ウィジェットの種類を選択").select_option("KPIカード")
        dialog.get_by_label("タイトル").fill("Total Revenue")
        dialog.get_by_label("対象カラム").select_option("Revenue")
        dialog.get_by_label("集計方法").select_option("sum")

        dialog.get_by_role("button", name="追加").click()
        expect(dialog).not_to_be_visible()
        expect(page.get_by_role("heading", name="Total Revenue")).to_be_visible(timeout=10000)
        print("KPI card added.")

        # 8. Take a screenshot
        print("Taking screenshot...")
        page.screenshot(path="jules-scratch/verification/bi_tool_dashboard.png")
        print("Screenshot saved to jules-scratch/verification/bi_tool_dashboard.png")

    except Exception as e:
        print(f"An error occurred: {e}")
        page.screenshot(path="jules-scratch/verification/error.png")
        raise
    finally:
        browser.close()

if __name__ == "__main__":
    with sync_playwright() as p:
        run(p)