# 群聯 8299 自動更新投資戰情室

網站預期網址：https://jessechan27.github.io/phison-dashboard/

## 安裝與啟用

1. GitHub 儲存庫選擇 **Add file → Upload files**，將 ZIP 解壓後的全部檔案及 `.github/workflows/daily.yml` 上傳至儲存庫（要保留資料夾結構）。**注意：GitHub 網頁上的 Upload files 對隱藏資料夾 `.github` 的上傳可能不方便，建議使用 GitHub Desktop 或 git 上傳解壓後的整個目錄。**
2. 在儲存庫 **Settings → Pages**，設定 **Source: GitHub Actions**。
3. 到 **Settings → Actions → General → Workflow permissions**，選 **Read and write permissions**。
4. 到 **Actions** 手動執行 **Daily Phison Market and Pages** 一次。
5. 成功部署後開啟 https://jessechan27.github.io/phison-dashboard/ 。

## 每日更新

週一至週五台灣時間 16:40 與 22:00 觸發 GitHub Actions。排程可能延遲；休市日使用上一筆可用資料。首次執行會補抓過去約 120 天資料。`update.py` 僅在辨識到官方表格欄位、日期相符且小計核對無誤後寫入，不會使用範例假資料；個別來源失敗時保留舊資料，並把原因寫進 `data/market.json` 的 `warnings`。

| 項目 | 來源 | 更新頻率 |
|---|---|---|
| 收盤價、成交量 | 櫃買中心 個股日成交行情 | 每個交易日 |
| 三大法人買賣超（外資、投信、自營商） | 櫃買中心 三大法人買賣明細 | 每個交易日 |
| 融資、融券餘額 | 櫃買中心 融資融券餘額 | 每個交易日（晚間公布） |
| 借券賣出餘額 | 櫃買中心 信用額度總量管制餘額表 | 每個交易日（晚間公布） |
| 大戶持股（400 張以上、千張以上） | 集保結算所 集保戶股權分散表 | 每週 |

要重新補抓較舊的缺漏資料，可在本機執行 `BACKFILL_DAYS=120 python update.py`。年底情境價格為靜態假設。
