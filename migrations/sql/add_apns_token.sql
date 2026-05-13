-- 追蹤任務：加入 APNs device token 欄位（供 iOS App 推播）
-- 執行前請備份資料庫

ALTER TABLE tracking_tasks
  ADD COLUMN apns_token VARCHAR(200) NULL DEFAULT NULL COMMENT 'iOS APNs device token (hex)';
