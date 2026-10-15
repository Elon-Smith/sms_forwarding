#pragma once
#include "esp_err.h"
esp_err_t idf_network_init();
// 必须在创建网络任务前初始化；仅在一次 HTTP/SMTP 会话期间持锁。
class IdfNetworkGuard {
public:
    IdfNetworkGuard();
    ~IdfNetworkGuard();
    IdfNetworkGuard(const IdfNetworkGuard&) = delete;
    bool acquired() const { return acquired_; }
private:
    bool acquired_ = false;
};
