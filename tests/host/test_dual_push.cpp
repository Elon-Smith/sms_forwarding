#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>
using IdfModemId=uint8_t;
constexpr IdfModemId IDF_SIM1=1;
constexpr int PUSH_QUEUE_MAX=4, PUSH_RETRY_MAX=3, portMAX_DELAY=0, pdTRUE=1;
// @struct@
std::array<PushJob,PUSH_QUEUE_MAX> s_push_jobs;
int s_mutex=1;std::atomic<bool> s_busy{false};int64_t clock_us=0;
bool online[3]={false,true,true},success=false;
std::vector<uint32_t> completed,failed;
struct Delivery {int sim;std::string receiver,text;};std::vector<Delivery> delivered;
int64_t esp_timer_get_time(){return clock_us;}
bool http_transport_available(IdfModemId sim){return online[sim];}
struct Wifi{bool staConnected=true;};Wifi idf_wifi_get_status(){return {};}
bool low_heap_defer(){return false;}
void ensure_init(){}
int xSemaphoreTake(int,int){return 1;}void xSemaphoreGive(int){}
bool channel_cooling(int,int64_t){return false;}
struct IdfPushChannel{};
bool idf_config_get_push_channel(int,IdfPushChannel&){return true;}
bool channel_valid(const IdfPushChannel&){return true;}
void cancel_forward_completion(uint32_t id){failed.push_back(id);}
void note_forward_target_success(uint32_t id){completed.push_back(id);}
void note_channel_result(int,bool){}
void idf_inbox_set_forwarded(uint32_t,bool){}
void idf_logf(const char*,...){}
uint32_t backoff_seconds(int,uint32_t){return 10;}
bool send_to_channel(IdfModemId sim,const IdfPushChannel&,const char*,const char* text,const char*,bool,const std::string& receiver){
    delivered.push_back({sim,receiver,text});return success;
}
// @functions@
int main(){
    assert(enqueue_push_job_locked(0,"same","[SIM1] body","",0,0,false,11,101,1,"old-card-1"));
    assert(enqueue_push_job_locked(0,"same","[SIM2] body","",0,0,false,22,202,2,"old-card-2"));
    assert(process_push_one()); // Network failure keeps the original source and receiver.
    online[1]=false;
    assert(process_push_one()); // SIM2 can progress while SIM1 cannot deliver.
    assert(delivered.size()==2 && delivered[0].sim==1 && delivered[1].sim==2);
    clock_us=11*1000000LL;success=true;
    assert(process_push_one());
    assert(completed.size()==1 && completed[0]==202);
    online[1]=true;assert(process_push_one());
    assert(delivered.back().receiver=="old-card-1" && delivered.back().text=="[SIM1] body");
    assert(completed.size()==2 && completed[1]==101 && failed.empty());
    assert(!process_push_one());
    for(int i=0;i<4;i++)assert(enqueue_push_job_locked(0,"a","b","",0,0,false,0,0,2,"card2"));
    assert(!enqueue_push_job_locked(1,"new","new","",0,0));
    for(const auto& job:s_push_jobs)assert(job.sim==2 && job.receiver=="card2");
    s_push_jobs={};success=false;
    assert(enqueue_push_job_locked(0,"same","[SIM2] body","",2,0,false,22,303,2,"card2"));
    assert(process_push_one());assert(failed.back()==303);assert(!s_busy);
    puts("dual push: failure retry keeps SIM/receiver/completion, offline isolation and full queue passed");
}
