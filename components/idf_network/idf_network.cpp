#include "idf_network.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
static SemaphoreHandle_t network_mutex = nullptr;
esp_err_t idf_network_init() {
    if (!network_mutex) network_mutex = xSemaphoreCreateMutex();
    return network_mutex ? ESP_OK : ESP_ERR_NO_MEM;
}
IdfNetworkGuard::IdfNetworkGuard() {
    acquired_ = network_mutex && xSemaphoreTake(network_mutex, pdMS_TO_TICKS(30000)) == pdTRUE;
}
IdfNetworkGuard::~IdfNetworkGuard() { if (acquired_) xSemaphoreGive(network_mutex); }
