#pragma once
#include <mutex>
using SemaphoreHandle_t=std::recursive_mutex*;
inline SemaphoreHandle_t xSemaphoreCreateMutex(){return new std::recursive_mutex;}
inline int xSemaphoreTake(SemaphoreHandle_t m, int){ m->lock();return 1; }
inline void xSemaphoreGive(SemaphoreHandle_t m){m->unlock();}
