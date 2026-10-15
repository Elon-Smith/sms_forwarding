#include <array>
#include <cassert>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

// 用轻量 NVS 和 HTTP 替身执行生产函数；故障注入不能改变运行中的配置。
using esp_err_t = int;
using nvs_handle_t = int;
constexpr int ESP_OK = 0, ESP_FAIL = -1, ESP_ERR_INVALID_ARG = 1;
constexpr int IDF_MAX_WIFI_NETWORKS = 5, portMAX_DELAY = 0;
struct IdfWifiNetwork { std::string ssid, pass; };
struct Config {
    IdfWifiNetwork wifiNetworks[IDF_MAX_WIFI_NETWORKS];
    std::string mdnsHost = "sms";
    bool wifiFromFallback = false;
};
static Config s_config, persisted;
static bool fail_mdns_write = false, fail_commit = false;
static int s_config_mutex = 1, commit_count = 0;
static void xSemaphoreTake(int, int) {}
static void xSemaphoreGive(int) {}
class ConfigTransaction {
    Config desired=s_config;
public:
    int error() const {return ESP_OK;}
    Config& next(){return desired;}
    int commit(){if(fail_mdns_write || fail_commit)return ESP_FAIL; s_config=desired; persisted=desired; ++commit_count; return ESP_OK;}
};
esp_err_t idf_config_save_wifi(const std::string&, const std::string&, const std::string* = nullptr);
static void idf_config_copy_mdns_host(char* out, size_t size) { std::snprintf(out, size, "%s", s_config.mdnsHost.c_str()); }

using IdfFormFields = std::vector<std::pair<std::string, std::string>>;
struct httpd_req_t { std::string body, response; bool auth = true, csrf = true; };
struct IdfWifiStatus { bool apMode = true, staConnected = false; std::string ip; };
static IdfWifiStatus wifi;
static int connect_calls = 0, restart_calls = 0;
static bool check_auth(httpd_req_t* req) { return req->auth; }
static bool check_csrf(httpd_req_t* req) { return req->csrf; }
static esp_err_t read_body(httpd_req_t* req, std::string& out, size_t max)
{
    if (req->body.size() > max) return ESP_FAIL;
    out = req->body;
    return ESP_OK;
}
static void set_json_no_cache(httpd_req_t*) {}
static esp_err_t httpd_resp_send(httpd_req_t* req, const char* body, size_t size) { req->response.assign(body, size); return ESP_OK; }
static void json_prop(std::string& out, const char* key, const std::string& value)
{
    out += '"'; out += key; out += "\":\"";
    for (char ch : value) { if (ch == '"' || ch == '\\') out += '\\'; out += ch; }
    out += '"';
}
static bool idf_wifi_is_ap_mode() { return wifi.apMode; }
static IdfWifiStatus idf_wifi_get_status() { return wifi; }
static void idf_wifi_provision_connect(const std::string& ssid, const std::string& pass)
{
    assert(s_config.wifiNetworks[0].ssid == ssid && s_config.wifiNetworks[0].pass == pass);
    ++connect_calls;
}
static void schedule_restart_or_now(const char*) { ++restart_calls; }

// @配网函数@

int main()
{
    httpd_req_t request;
    request.body = "ssid=Home+WiFi&pass=test-pass&mdnsHost=Living-Room";
    handle_wifi_config(&request);
    assert(s_config.mdnsHost == "living-room" && persisted.mdnsHost == "living-room");
    assert(s_config.wifiNetworks[0].ssid == "Home WiFi" && persisted.wifiNetworks[0].pass == "test-pass");
    assert(commit_count == 1 && connect_calls == 1);
    assert(request.response.find("\"mdnsHost\":\"living-room\"") != std::string::npos);

    // 未提交 mDNS 的旧配网、控制台和后台连接调用必须保留名称。
    request.body = "ssid=Office&pass=other-pass";
    handle_wifi_config(&request);
    assert(s_config.mdnsHost == "living-room" && persisted.mdnsHost == "living-room");
    assert(idf_config_save_wifi("Legacy", "") == ESP_OK);
    assert(s_config.mdnsHost == "living-room");

    const auto previous_ssid = s_config.wifiNetworks[0].ssid;
    const int connections_before = connect_calls, commits_before = commit_count;
    request.body = "ssid=Failed&pass=new-pass&mdnsHost=new-device";
    fail_mdns_write = true;
    handle_wifi_config(&request);
    fail_mdns_write = false;
    assert(s_config.mdnsHost == "living-room" && s_config.wifiNetworks[0].ssid == previous_ssid);
    assert(persisted.mdnsHost == "living-room" && commit_count == commits_before && connect_calls == connections_before);
    assert(request.response.find("\"success\":false") != std::string::npos);
    fail_commit = true;
    handle_wifi_config(&request);
    fail_commit = false;
    assert(s_config.mdnsHost == "living-room" && connect_calls == connections_before);

    request.body = "ssid=" + std::string(33, 'x') + "&mdnsHost=bad-network";
    handle_wifi_config(&request);
    assert(commit_count == commits_before && connect_calls == connections_before);
    request.body = "ssid=Office&mdnsHost=New-Device";
    request.auth = false;
    handle_wifi_config(&request);
    request.auth = true; request.csrf = false;
    handle_wifi_config(&request);
    request.csrf = true;
    assert(commit_count == commits_before);

    // 复用已有名称规范化规则，允许其他客户端填入完整 .local 地址。
    request.body = "ssid=Office&mdnsHost=http%3A%2F%2FDesk-Hub.local";
    handle_wifi_config(&request);
    assert(s_config.mdnsHost == "desk-hub");
    request.body = "ssid=Office&mdnsHost=";
    handle_wifi_config(&request);
    assert(s_config.mdnsHost == "sms");
    std::string long_host(60, 'A');
    assert(idf_config_save_wifi("Office", "", &long_host) == ESP_OK);
    assert(s_config.mdnsHost == std::string(32, 'a'));

    wifi.staConnected = true; wifi.ip = "192.168.1.50";
    handle_apstatus(&request);
    assert(request.response.find("\"connected\":true") != std::string::npos);
    assert(request.response.find("\"mdnsHost\":\"" + s_config.mdnsHost + "\"") != std::string::npos);
    assert(request.response.find("pass") == std::string::npos && request.response.find("ssid") == std::string::npos);
    wifi.apMode = false;
    request.body = "ssid=Office&mdnsHost=Sta-Host";
    handle_wifi_config(&request);
    assert(restart_calls == 1 && s_config.mdnsHost == "sta-host");
    std::puts("AP mDNS persistence, legacy requests and failure regressions passed");
}
