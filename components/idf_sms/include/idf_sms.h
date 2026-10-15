#pragma once
#include "idf_board.h"

#include <stdint.h>

#include <string>

#include "esp_err.h"

struct IdfSmsStatus {
    uint32_t total = 0;
    uint32_t lastSmsEpoch = 0;
    bool receiveReady = false;
};

esp_err_t idf_sms_start(void);
esp_err_t idf_sms_send_text(const std::string& phone, const std::string& text, std::string& message, bool track_reply = false);
esp_err_t idf_sms_enqueue_outgoing(const std::string& phone, const std::string& text, std::string& message);
int idf_sms_outgoing_queue_depth(void);
IdfSmsStatus idf_sms_get_status(void);

// 自定义短信任务体检：仅一个蜂窝任务可持有窗口；超时使用单调时钟。
bool idf_sms_reply_check_begin(const std::string& sender_pattern, const std::string& body_pattern);
void idf_sms_reply_check_arm(int timeout_seconds);
// 0=等待，1=匹配成功，-1=超时/未启用。
int idf_sms_reply_check_poll(void);
void idf_sms_reply_check_cancel(void);

// 显式卡位入口。
esp_err_t idf_sms_start(IdfModemId sim);
esp_err_t idf_sms_send_text(IdfModemId sim, const std::string& phone_raw, const std::string& text_raw, std::string& message, bool track_reply = false);
esp_err_t idf_sms_enqueue_outgoing(IdfModemId sim, const std::string& phone_raw, const std::string& text_raw, std::string& message);
int idf_sms_outgoing_queue_depth(IdfModemId sim);
IdfSmsStatus idf_sms_get_status(IdfModemId sim);
bool idf_sms_reply_check_begin(IdfModemId sim, const std::string& sender_pattern, const std::string& body_pattern);
void idf_sms_reply_check_arm(IdfModemId sim, int timeout_seconds);
int idf_sms_reply_check_poll(IdfModemId sim);
void idf_sms_reply_check_cancel(IdfModemId sim);
