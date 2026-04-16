-- 追蹤任務：加入來源與訪客 ID 欄位，user_id 改可為 null
-- 執行前請備份資料庫

ALTER TABLE tracking_tasks
  MODIFY COLUMN user_id INT NULL,
  ADD COLUMN source VARCHAR(10) NOT NULL DEFAULT 'line' COMMENT '來源: line/web' AFTER user_id,
  ADD COLUMN guest_id VARCHAR(64) NULL COMMENT '網頁訪客 ID（localStorage UUID）' AFTER source;
