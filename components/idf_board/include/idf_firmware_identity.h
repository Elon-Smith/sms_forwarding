#pragma once
#include <cstring>

// 双模组镜像使用独立产品标识，拒绝误装上游单模组应用。
inline bool idf_dual_firmware_identity_valid(const char* project, const char* version)
{
    return project && version && std::strcmp(project, "sms_forwarding_dual") == 0 &&
           std::strstr(version, "-dual.") != nullptr;
}
