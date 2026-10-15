#pragma once
#include "esp_err.h"
#include <cstddef>
#include <cstdint>
using nvs_handle_t=int;
constexpr int NVS_READONLY=0,NVS_READWRITE=1;
struct nvs_stats_t { size_t used_entries=0,free_entries=10000,total_entries=10000,namespace_count=0; };
esp_err_t nvs_open(const char*,int,nvs_handle_t*);
esp_err_t nvs_open_from_partition(const char*,const char*,int,nvs_handle_t*);
esp_err_t nvs_get_str(nvs_handle_t,const char*,char*,size_t*);
esp_err_t nvs_get_u8(nvs_handle_t,const char*,uint8_t*);
esp_err_t nvs_get_u32(nvs_handle_t,const char*,uint32_t*);
esp_err_t nvs_get_i32(nvs_handle_t,const char*,int32_t*);
esp_err_t nvs_set_str(nvs_handle_t,const char*,const char*);
esp_err_t nvs_set_u8(nvs_handle_t,const char*,uint8_t);
esp_err_t nvs_set_u32(nvs_handle_t,const char*,uint32_t);
esp_err_t nvs_set_i32(nvs_handle_t,const char*,int32_t);
esp_err_t nvs_get_stats(const char*,nvs_stats_t*);
esp_err_t nvs_erase_all(nvs_handle_t);
esp_err_t nvs_commit(nvs_handle_t);
void nvs_close(nvs_handle_t);
