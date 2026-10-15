#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cctype>
#include <cstdio>
#include <deque>
#include <functional>
#include <string>
using esp_err_t=int;using TaskHandle_t=void*;
struct Semaphore { bool signalled=false; };using SemaphoreHandle_t=Semaphore*;
struct Queue { std::deque<void*> items; };using QueueHandle_t=Queue*;
constexpr int ESP_OK=0,ESP_FAIL=-1,ESP_ERR_INVALID_STATE=1,ESP_ERR_NO_MEM=2,ESP_ERR_TIMEOUT=3,pdTRUE=1,portMAX_DELAY=-1;
TaskHandle_t current_task=reinterpret_cast<void*>(7);std::function<void()> pump;
TaskHandle_t xTaskGetCurrentTaskHandle(){return current_task;}
Semaphore* xSemaphoreCreateBinary(){return new Semaphore;}
void vSemaphoreDelete(Semaphore* s){delete s;}
int xSemaphoreTake(Semaphore* s,int){if(!s->signalled)pump();assert(s->signalled);return 1;}
void xSemaphoreGive(Semaphore* s){s->signalled=true;}
int xQueueSend(Queue* q,void* ptr,int){if(q->items.size()==4)return 0;q->items.push_back(*static_cast<void**>(ptr));return 1;}
int xQueueReceive(Queue* q,void* ptr,int){if(q->items.empty())return 0;*static_cast<void**>(ptr)=q->items.front();q->items.pop_front();return 1;}
struct Status {bool atReady=true;uint32_t generation=1;};
class Owner {public:
 std::atomic<int> s_reset_request{0};Status status;
 Status idf_modem_get_status(){return status;}
// @owner@
};
int64_t now=100;
int64_t esp_timer_get_time(){return now;}
std::string idf_util_trim_copy(const std::string& s){auto a=s.find_first_not_of(" \r\n\t");return a==std::string::npos?"":s.substr(a,s.find_last_not_of(" \r\n\t")-a+1);}
class Urc {public:
 uint32_t s_uart_generation = 0;
struct UrcIdentity { uint32_t generation = 1; } urc_identity;
UrcIdentity idf_modem_get_status() { return urc_identity; }
std::string s_uart_line_carry,received;
 int64_t s_uart_line_started_us=0,s_uart_wait_cmt_until_us=0;
 bool s_uart_wait_cmt_pdu=false;
 void append_urc_text(const std::string& text,int64_t){received+=text;}
 void feed(const std::string& text){preserve_uart_urcs(reinterpret_cast<const uint8_t*>(text.data()),text.size());}
// @urc@
};
int main(){
 Owner one,two;Queue q1,q2;one.owner_=reinterpret_cast<void*>(1);two.owner_=reinterpret_cast<void*>(2);one.commands_=&q1;two.commands_=&q2;
 int calls1=0,calls2=0;
 pump=[&]{one.service_commands();two.service_commands();};
 assert(one.invoke([&]{++calls1;return ESP_ERR_TIMEOUT;})==ESP_ERR_TIMEOUT);
 assert(one.s_reset_request==2 && two.s_reset_request==0);
 assert(two.invoke([&]{++calls2;return ESP_OK;})==ESP_OK);
 assert(one.invoke([&]{++calls1;return ESP_OK;})==ESP_ERR_INVALID_STATE);
 one.s_reset_request=0;
 assert(one.invoke([&]{++calls1;return ESP_OK;},999)==ESP_ERR_INVALID_STATE);
 pump=[&]{one.status.generation++;one.service_commands();};
 assert(one.invoke([&]{++calls1;return ESP_OK;})==ESP_ERR_INVALID_STATE);
 pump=[&]{one.session_owner_=reinterpret_cast<void*>(8);one.service_commands();};
 assert(one.invoke([&]{++calls1;return ESP_OK;})==ESP_ERR_INVALID_STATE);one.session_owner_=0;
 for(int i=0;i<4;i++)q1.items.push_back(nullptr);
 assert(one.invoke([&]{++calls1;return ESP_OK;})==ESP_ERR_TIMEOUT);q1.items.clear();
 assert(calls1==1 && calls2==1);
 Semaphore done;Owner::Command stale{[&]{++calls1;return ESP_OK;},&done,ESP_FAIL,one.status.generation,1,current_task};
 q1.items.push_back(&stale);one.service_commands();assert(stale.result==ESP_ERR_INVALID_STATE && calls1==1);
 Urc a,b;
 const std::string pdu="00112233445566778899AABBCCDDEEFF";
 a.feed("AT+CSQ\r\n+CMT: ,16\r\n"+pdu.substr(0,12));
 b.feed("+CMTI: \"SM\",7\r\nOK\r\n");
 a.feed(pdu.substr(12)+"\r\n+CSQ: 20,99\r\nOK\r\n");
 assert(a.received=="+CMT: ,16\r\n"+pdu+"\r\n");
 assert(b.received=="+CMTI: \"SM\",7\r\n");
 a.feed("+CMT: ,16\r\n"+pdu.substr(0,12));
 ++a.urc_identity.generation;
 const auto before = a.received;
 a.feed(pdu.substr(12)+"\r\n");
 assert(a.received==before); // Old partial PDU never crosses an identity boundary.
 puts("dual owner: isolated timeout, stale responses/identity, session exclusion, queue full and interleaved URCs passed");
}
