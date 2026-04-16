-- 診間開關診時間表
-- 從 ClinicProgress 歷史資料每日統計，用來判斷看診時段

CREATE TABLE IF NOT EXISTS clinic_schedule (
    id           INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    hospital_code VARCHAR(50) NOT NULL COMMENT '醫院代碼',
    department   VARCHAR(100) NOT NULL COMMENT '科別',
    clinic_room  VARCHAR(255) NOT NULL COMMENT '診間號碼',
    weekday      TINYINT      NOT NULL COMMENT '星期幾 0=週一 6=週日',
    open_time    TIME         NOT NULL COMMENT '開診時間（台灣時間）',
    close_time   TIME         NOT NULL COMMENT '關診時間（台灣時間）',
    sample_count INT          NOT NULL DEFAULT 0 COMMENT '統計樣本數',
    updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_clinic_schedule (hospital_code, department, clinic_room, weekday),
    INDEX ix_cs_hospital_weekday (hospital_code, weekday)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='診間每週開關診時間（從歷史資料統計）';
