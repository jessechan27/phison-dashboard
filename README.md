# 群聯 8299 自動更新投資戰情室

網站預期網址：https://jessechan27.github.io/phison-dashboard/

## 安裝與啟用

1. GitHub 儲存庫選擇 **Add file → Upload files**，將 ZIP 解壓後的全部檔案及 `.github/workflows/daily.yml` 上傳至儲存庫（要保留資料夾結構）。**注意：GitHub 網頁上的 Upload files 對隱藏資料夾 `.github` 的上傳可能不方便，建議使用 GitHub Desktop 或 git 上傳解壓後的整個目錄。**
2. 在儲存庫 **Settings → Pages**，設定 **Source: GitHub Actions**。
3. 到 **Settings → Actions → General → Workflow permissions**，選 **Read and write permissions**。
4. 到 **Actions** 手動執行 **Daily Phison Market and Pages** 一次。
5. 成功部署後開啟 https://jessechan27.github.io/phison-dashboard/ 。

## 每日更新

週一至週五台灣時間 16:40 觸發 GitHub Actions。排程可能延遲；休市日使用上一筆可用資料。首次執行會補抓過去約 120 天資料。`update.py` 僅在辨識到官方表格欄位後寫入，不會使用範例假資料。若 API 格式變動，工作流程會報錯，以免顯示假資料。

目前的自動下載範圍只涵蓋盤後收盤價與成交股數。**三大法人、借券、融資融券尚未接上，網站明確顯示未取得**，不是假裝已完整自動化。年底情境價格為靜態假設。
