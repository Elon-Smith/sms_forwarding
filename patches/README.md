# ESP-IDF 5.5.5 补丁配置

本分支按用户最新要求固定 **ESP-IDF v5.5.5 / Mbed TLS 3.6.6**。保留上游应用基线 d4271d4，不导入旧本地应用代码。

```bash
python tools/apply_idf_patches.py --idf-path "$IDF_PATH"
```

Windows 构建入口和 CI 自动执行。脚本先检查 SDK 版本和完整上下文；`--check-only` 不修改 SDK，重复应用可识别。请使用独立 SDK 副本。

唯一活动补丁为 `idf5.5.5/0001-x509-parse-all-certificate-policy-oids.patch`，针对 5.5.5 的 Mbed TLS 提交 `9d669eadb1955d348986b9280156710aaaadf79f`：解析合法 certificate policy OID，保持未知关键扩展、证书链、签名与主机名检查。已按 3.6.6 的枚举及 OID 函数名称适配。

`mbedtls/` 和 `esp-idf/` 中的旧补丁仅作为上游 6.0.2 历史资料保存，**不会被活动脚本应用**。5.5.5 没有 6.0.2 的 `esp_crt_ca_cb_callback` 和 `CONFIG_MBEDTLS_CERTIFICATE_BUNDLE_CROSS_SIGNED_VERIFY`，因此不移植该 CA 回调或其内存修复。使用 5.5.5 原生 `esp_crt_verify_callback`、完整公共 CA 包和 GSMA 根证书；不关闭 TLS 验证。

## 验证

```bash
python -m unittest discover -s tools/tests -v
python tools/verify_build.py --idf-path "$IDF_PATH"
```

提供 `IDF_PATH`、主机 `CC`/`CXX` 后，测试提取真实 5.5.5 签名验证辅助函数和证书回调，执行 6,000 次成功/失败循环，检查临时密钥释放、未知根拒绝及其他验证错误标志保留。密码学边界由桩模拟，不能代替设备 TLS 握手。

LPA 迁移测试编译同一 SDK 的真实 SHA-256 实现，并以独立 Python 摘要为预期值；另覆盖 HTTP 200/400/403/500 和协议头校验，确保错误正文不进入 BPP 解析。

环境审计还反向验证补丁后的文件能精确还原 SDK 原文，拒绝额外 SDK 修改，并校验应用及 bootloader 的组件/源码/头文件搜索路径、工具链、配置和镜像身份。实机推送、SMTP、eSIM、OTA 及长时间运行仍待验收。
