cmake_minimum_required(VERSION 3.22.1)

# 原生 ESP-IDF 固件工程入口；Arduino fallback 已移除。
include($ENV{IDF_PATH}/tools/cmake/version.cmake)
if(NOT "$ENV{IDF_VERSION}" STREQUAL "5.5.5")
    message(FATAL_ERROR "This branch requires ESP-IDF 5.5.5; use a separate clean build directory.")
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
set(PROJECT_VER "1.1.7-dual.2-idf555")
project(sms_forwarding_dual)
