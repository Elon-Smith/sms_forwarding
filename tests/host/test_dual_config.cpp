#include "idf_firmware_identity.h"
// Compile and fault-inject the complete production config component.
#include <cassert>
#include <cstring>
#include <iostream>
#include <map>
#include <string>
#include <variant>
#include "idf_config.h"
#include "nvs.h"
using Value=std::variant<std::string,uint8_t,uint32_t,int32_t>;
using Store=std::map<std::string,std::map<std::string,Value>>;
Store flash;
std::map<int,std::string> handles;
int next_handle=0, writes=0, fail_at=-1;
bool full=false;
bool fail(){return ++writes==fail_at;}
int nvs_open_from_partition(const char* part,const char* ns,int mode,int* handle){
 std::string name=std::string(part)+":"+ns;
 if(!mode && !flash.count(name))return ESP_ERR_NVS_NOT_FOUND;
 if(mode)flash[name];
 *handle=++next_handle;handles[*handle]=name;return ESP_OK;
}
int nvs_open(const char* ns,int mode,int* handle){return nvs_open_from_partition("nvs",ns,mode,handle);}
void nvs_close(int h){handles.erase(h);}
int nvs_commit(int){return fail()?ESP_FAIL:ESP_OK;}
int nvs_erase_all(int h){if(fail())return ESP_FAIL;flash[handles.at(h)].clear();return ESP_OK;}
int nvs_get_stats(const char*,nvs_stats_t* stats){stats->free_entries=full?0:10000;return ESP_OK;}
template<class T> int get(int h,const char* key,T* out){
 auto& map=flash[handles.at(h)];auto it=map.find(key);if(it==map.end())return ESP_ERR_NVS_NOT_FOUND;
 auto p=std::get_if<T>(&it->second);if(!p)return ESP_FAIL;*out=*p;return ESP_OK;
}
template<class T> int put(int h,const char* key,T value){if(fail())return ESP_FAIL;flash[handles.at(h)][key]=value;return ESP_OK;}
int nvs_get_u8(int h,const char* k,uint8_t* v){return get(h,k,v);}
int nvs_get_u32(int h,const char* k,uint32_t* v){return get(h,k,v);}
int nvs_get_i32(int h,const char* k,int32_t* v){return get(h,k,v);}
int nvs_set_u8(int h,const char* k,uint8_t v){return put(h,k,v);}
int nvs_set_u32(int h,const char* k,uint32_t v){return put(h,k,v);}
int nvs_set_i32(int h,const char* k,int32_t v){return put(h,k,v);}
int nvs_set_str(int h,const char* k,const char* v){return put(h,k,std::string(v));}
int nvs_get_str(int h,const char* k,char* v,size_t* len){
 std::string value;int err=get(h,k,&value);if(err)return err;
 size_t need=value.size()+1;if(!v){*len=need;return ESP_OK;}
 if(*len<need){*len=need;return ESP_ERR_NVS_INVALID_LENGTH;}
 memcpy(v,value.c_str(),need);*len=need;return ESP_OK;
}
int main(){
 assert(idf_dual_firmware_identity_valid("sms_forwarding_dual","1.1.7-dual.1"));
 assert(!idf_dual_firmware_identity_valid("sms_forwarding_idf","1.1.7"));
 assert(!idf_dual_firmware_identity_valid("sms_forwarding_dual","1.1.7"));
 assert(!idf_dual_firmware_identity_valid(nullptr,"1.1.7-dual.1"));

 // Old namespace credentials must never become the new default configuration.
 flash["nvs:sms_config"]["wifiSsid"]=std::string("DO-NOT-IMPORT");
 assert(idf_config_load()==ESP_OK);assert(idf_config_get().wifiNetworks[0].ssid.empty());
 assert(!idf_config_get().kaEnabled && !idf_config_get().modem2.kaEnabled);
 assert(idf_config_save_keepalive(1,false,175,1,"","https://one.invalid/payload","")==ESP_OK);
 assert(idf_config_save_keepalive(2,false,99,2,"12345","https://two.invalid/payload","")==ESP_OK);
 assert(idf_config_load()==ESP_OK);
 assert(idf_config_get_keepalive_run_view(1).kaIntervalDays==175);
 assert(idf_config_get_keepalive_run_view(2).kaIntervalDays==99);
 IdfSimCredential credentials[IDF_MAX_SIM_CREDENTIALS];
 credentials[0].iccid="8986001234567890123";credentials[0].pin="1234";
 assert(idf_config_save_sim(2,false,true,"apn2","","222",credentials)==ESP_OK);
 assert(!idf_config_get_sim_unlock_view(1,credentials[0].iccid).found);
 assert(idf_config_get_sim_unlock_view(2,credentials[0].iccid).found);
 assert(idf_config_record_sim_unlock_result(2,credentials[0].iccid,false,false)==ESP_OK);
 assert(idf_config_load()==ESP_OK);
 assert(idf_config_get_sim_unlock_view(2,credentials[0].iccid).credential.pinFailedAttempts==1);
 assert(idf_config_get_sim_settings_view(1).apn.empty());
 IdfSchedTask tasks[IDF_MAX_SCHED_TASKS];tasks[0].sim=2;tasks[0].name="SIM2 task";
 assert(idf_config_save_sched_tasks(tasks)==ESP_OK);assert(idf_config_load()==ESP_OK);
 assert(idf_config_get_sched_run_view(2,0).valid);assert(!idf_config_get_sched_run_view(1,0).valid);
 auto before=idf_config_export_text(true);auto snapshot=flash;
 std::string imported=before+"\nwebUser=newadmin\nkaTarget=111\nsim2.kaTarget=222\nst0Sim=1\n";
 writes=0;assert(idf_config_import_text(imported,nullptr)==ESP_OK);int write_count=writes;
 auto expected=idf_config_export_text(true);
 assert(expected!=before);
 for(int fault=1;fault<=write_count;fault++){
  flash=snapshot;fail_at=-1;assert(idf_config_load()==ESP_OK);
  writes=0;fail_at=fault;int err=idf_config_import_text(imported,nullptr);assert(err!=ESP_OK);
  fail_at=-1;assert(handles.empty());assert(idf_config_load()==ESP_OK);
  auto recovered=idf_config_export_text(true);
  // NVS setters write immediately: interruption after selector can yield the entire new config.
  assert(recovered==before || recovered==expected);
 }
 full=true;auto saved=idf_config_export_text(true);
 assert(idf_config_save_account("rejected","password")==ESP_ERR_NVS_NOT_ENOUGH_SPACE);
 assert(idf_config_export_text(true)==saved);full=false;
 assert(idf_config_factory_reset()==ESP_OK);assert(idf_config_load()==ESP_OK);
 auto reset=idf_config_get();assert(reset.webUser==IDF_DEFAULT_WEB_USER);
 assert(reset.kaTarget.empty() && reset.modem2.kaTarget.empty());
 assert(!reset.kaEnabled && !reset.modem2.kaEnabled);
 assert(idf_config_import_text(before,nullptr)==ESP_OK);assert(idf_config_load()==ESP_OK);
 assert(idf_config_export_text(true)==before);
 assert(idf_config_save_keepalive(3,false,1,1,"","","")==ESP_ERR_INVALID_ARG);
 auto task_config=idf_config_get();auto expected_task=task_config.schedTasks[0];
 assert(idf_config_set_sched_last_if(0,123,expected_task)==ESP_OK);
 task_config.schedTasks[0].sim=expected_task.sim==1?2:1;
 assert(idf_config_save_sched_tasks(task_config.schedTasks)==ESP_OK);
 assert(idf_config_set_sched_last_if(0,999,expected_task)==ESP_ERR_INVALID_STATE);
 std::cout<<"dual config: "<<write_count<<" write-failure points, restore, target isolation, defaults and capacity passed\n";
}
