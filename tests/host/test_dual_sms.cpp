#include <array>
#include <algorithm>
#include <string>
#include <vector>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <functional>
int64_t clock_us=1000;
int64_t esp_timer_get_time(){return clock_us;}
constexpr int portMAX_DELAY=0;
void xSemaphoreTake(int,int){} void xSemaphoreGive(int){}
void idf_logf(const char*,...){} void idf_log_line(const char*){}
class SmsFixture { public:
// @parts@
// @fields@
uint32_t s_card_generation=1; int s_out_mutex=1;
std::vector<std::string> delivered;
void idf_sms_reply_check_cancel(){}
void process_sms_content(const char*,const char* body,const char*,int64_t,uint32_t,bool=false){delivered.emplace_back(body);}
// @functions@
};
int main(){
 SmsFixture one,two;
 auto part=[](const char* text,int num){SmsFixture::DecodedSms p;p.sender="10086";p.text=text;p.timestamp="261015120000+32";p.concat[0]=42;p.concat[1]=num;p.concat[2]=2;return p;};
 one.handle_decoded_pdu(part("same-",1));two.handle_decoded_pdu(part("same-",1));
 two.handle_decoded_pdu(part("second",2));one.handle_decoded_pdu(part("first",2));
 assert(one.delivered==std::vector<std::string>{"same-first"});
 assert(two.delivered==std::vector<std::string>{"same-second"});
 one.handle_decoded_pdu(part("first",2));assert(one.delivered.size()==1);
 assert(!one.seen_recently(0));assert(one.seen_recently(0));assert(!two.seen_recently(0));
 one.reset_card_state(2);two.reset_card_state(2);
 for(auto* card:{&one,&two}){card->handle_decoded_pdu(part("A",1));card->handle_decoded_pdu(part("B",2));assert(card->delivered.back()=="AB");}
 one.handle_decoded_pdu(part("old",1));two.handle_decoded_pdu(part("peer",1));
 one.enqueue_index(7,10);one.s_out_count=1;one.s_out_queue[0].phone="123";
 one.reset_card_state(3);assert(one.s_index_count==0 && one.s_out_count==0 && !one.seen_recently(0));
 one.handle_decoded_pdu(part("new",2));assert(one.delivered.size()==2);
 two.handle_decoded_pdu(part("done",2));assert(two.delivered.back()=="peerdone");
 for(int i=0;i<10;++i)one.enqueue_index(i,10);
 assert(one.s_index_count==one.INDEX_QUEUE_MAX && one.s_backfill_pending);
 two.enqueue_index(7,20);int idx;int64_t when;assert(two.pop_index(idx,when)&&idx==7&&when==20);
 puts("dual SMS assembly, identical ref/content, dedupe, queue full and card replacement passed");
}
