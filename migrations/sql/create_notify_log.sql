-- 通知推播記錄表
-- 每次實際推播（_send / _send_and_finish）都寫一筆

CREATE TABLE IF NOT EXISTS notify_log (
    id              INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    task_id         INT          NOT NULL COMMENT 'tracking_tasks.id',
    source          VARCHAR(10)  NOT NULL DEFAULT 'line' COMMENT 'line / web / test',
    hospital_code   VARCHAR(50)  NOT NULL,
    department      VARCHAR(100) DEFAULT NULL,
    doctor_name     VARCHAR(50)  DEFAULT NULL,
    clinic_room     VARCHAR(100) DEFAULT NULL,
    user_number     INT          DEFAULT NULL COMMENT '用戶號碼',
    current_number  INT          DEFAULT NULL COMMENT '當時看診號碼',
    remaining       INT          DEFAULT NULL COMMENT '剩餘號數',
    event_type      VARCHAR(30)  NOT NULL COMMENT 'notify / arrived / passed / skipped / timeout / doctor_gone',
    message_preview VARCHAR(200) DEFAULT NULL,
    created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'UTC',

    INDEX ix_nl_task_id    (task_id),
    INDEX ix_nl_created_at (created_at),
    INDEX ix_nl_hospital_event (hospital_code, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='通知推播記錄（每次推播一筆）';
