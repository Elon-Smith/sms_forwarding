#define __STDC_FORMAT_MACROS
#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <inttypes.h>
#include <string>

// 用轻量替身编译真实日志增量函数与页面模板请求处理器。
static constexpr size_t LOG_RING_SIZE = 120;
static std::array<std::string, LOG_RING_SIZE> s_lines;
static size_t s_count = 0, s_next = 0;
static uint32_t s_seq = 0;
static std::atomic<uint32_t> s_seq_mirror{0};
static bool s_log_mutex = true, lock_available = true;
static constexpr int pdTRUE = 1;
static int pdMS_TO_TICKS(int ms) { return ms; }
static int xSemaphoreTake(bool, int) { return lock_available ? pdTRUE : 0; }
static void xSemaphoreGive(bool) {}
static void ensure_init() {}
static void idf_util_json_escape_append(std::string& out, const std::string& text)
{
    for (char ch : text) {
        if (ch == '"' || ch == '\\') out += '\\';
        if (ch == '\n') out += "\\n";
        else out += ch;
    }
}

// @日志增量函数@

using esp_err_t = int;
static constexpr esp_err_t ESP_OK = 0;
static constexpr int HTTPD_400_BAD_REQUEST = 400, HTTPD_404_NOT_FOUND = 404;
static const char* WEB_ASSET_HASH = "abcdef012345";
struct WebAsset {};
struct httpd_req_t {
    std::string query, cache;
    bool authenticated = true;
    int error = 0, sent = 0;
};
static bool check_auth(httpd_req_t* req) { return req->authenticated; }
static esp_err_t httpd_req_get_url_query_str(httpd_req_t* req, char* out, size_t size)
{
    if (req->query.size() >= size) return -1;
    std::strcpy(out, req->query.c_str());
    return ESP_OK;
}
static esp_err_t httpd_query_key_value(const char* query, const char* key, char* out, size_t size)
{
    std::string text(query), prefix = std::string(key) + "=";
    for (size_t start = 0; start < text.size();) {
        size_t end = text.find('&', start);
        std::string item = text.substr(start, end == std::string::npos ? end : end - start);
        if (item.rfind(prefix, 0) == 0) {
            std::string value = item.substr(prefix.size());
            if (value.size() >= size) return -1;
            std::strcpy(out, value.c_str());
            return ESP_OK;
        }
        if (end == std::string::npos) break;
        start = end + 1;
    }
    return -1;
}
static const WebAsset* findWebPanelAsset(const char* name)
{
    static const WebAsset asset;
    return std::strcmp(name, "overview") == 0 ? &asset : nullptr;
}
static void httpd_resp_send_err(httpd_req_t* req, int code, const char*) { req->error = code; }
static esp_err_t send_gzip_asset(httpd_req_t* req, const WebAsset&, const char* cache)
{
    req->cache = cache;
    req->sent++;
    return ESP_OK;
}

// @模板请求处理器@

static void append_log(const std::string& text)
{
    s_lines[s_next] = text;
    s_next = (s_next + 1) % LOG_RING_SIZE;
    if (s_count < LOG_RING_SIZE) s_count++;
    s_seq++;
    s_seq_mirror = s_seq;
}

int main()
{
    assert(idf_log_json_since(0) == "{\"seq\":0,\"lines\":[]}");
    append_log("one"); append_log("two\n\"quoted\""); append_log("three");
    assert(idf_log_json_since(1) == "{\"seq\":3,\"lines\":[\"two\\n\\\"quoted\\\"\",\"three\"]}");
    auto idle = idf_log_json_since(3);
    assert(idle == "{\"seq\":3,\"lines\":[]}");
    assert(idle.capacity() < 128);  // 空轮询不能再预分配 2048 字节。
    assert(idf_log_json_since(99) == idf_log_json_since(0));  // 设备重启后的旧游标。
    for (int i = 4; i <= 130; i++) append_log(std::to_string(i));
    auto all = idf_log_json_since(0);
    assert(all.find("[\"11\",\"12\"") != std::string::npos);  // 环回后最老日志。
    assert(idf_log_json_since(129) == "{\"seq\":130,\"lines\":[\"130\"]}");
    assert(idf_log_json_since(10) == all);
    lock_available = false;
    assert(idf_log_json_since(0) == "{\"seq\":130,\"lines\":[]}");
    lock_available = true;

    httpd_req_t matched;
    matched.query = "panel=overview&v=abcdef012345";
    handle_ui_panel(&matched);
    assert(matched.sent == 1);
    assert(matched.cache == "private, max-age=31536000, immutable");
    for (const char* query : {"panel=overview", "panel=overview&v=old", "panel=overview&v=too-long-to-fit-in-version-buffer"}) {
        httpd_req_t req;
        req.query = query;
        handle_ui_panel(&req);
        assert(req.cache == "private, no-cache, max-age=0");
    }
    httpd_req_t denied;
    denied.query = matched.query; denied.authenticated = false;
    handle_ui_panel(&denied);
    assert(denied.sent == 0 && denied.cache.empty());
    httpd_req_t missing;
    handle_ui_panel(&missing);
    assert(missing.error == HTTPD_400_BAD_REQUEST);
    httpd_req_t unknown;
    unknown.query = "panel=missing";
    handle_ui_panel(&unknown);
    assert(unknown.error == HTTPD_404_NOT_FOUND);
    std::puts("web template cache and log delta regressions passed");
}
