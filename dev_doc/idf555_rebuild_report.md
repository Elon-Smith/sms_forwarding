# ESP-IDF 5.5.5 重新构建与校验报告

日期：2026-10-15。状态：**软件构建与离线校验通过；候选固件，未烧录，实机验收待完成。**

以上为首次重构建时的历史状态。随后用户授权烧录与真实互发测试，当前运行镜像、硬件结果及未通过项见 [实机测试报告](hardware_test_20261015.md)，不要将本报告的初始镜像摘要用于核对后续修正版。

## 本轮范围

按用户最新要求，以 5.5.5 覆盖原计划的 6.0.2 SDK 固定版本。继续在 `D:\Workspace\SMS-Forwarder-C3-upstream-dual`、`codex/upstream-dual-modem` 分支维护上游原生工程。上游源码基线仍为 1.1.7 / `d4271d46f40bca215d2fba966b83051a1a4460be`。没有导入旧本地应用、私有配置或凭据，没有替换 `D:\Workspace\SMS-Forwarder-C3`。

## 环境核对

| 项目 | 实际使用 |
| --- | --- |
| ESP-IDF | v5.5.5，提交 `b774170ff46c393eeb5e495ea37936038d3f4f4f` |
| 独立 SDK | `D:\dev\sms-sdk-idf-v5.5.5`，从本机干净 5.5.5 及其子模块复制 |
| Mbed TLS | 3.6.6，提交 `9d669eadb1955d348986b9280156710aaaadf79f` |
| C3 GCC | 14.2.0，`esp-14.2.0_20260121` |
| Python | 3.11.9，`C:\Espressif\python_env\idf5.5_py3.11_env\Scripts\python.exe` |
| esptool | 4.12.0，由上述 IDF Python 环境提供 |
| 构建目录 | `build/idf5.5.5` |
| 配置 | 从当前 `sdkconfig.defaults` 新生成 `build/sdkconfig.idf5.5.5` |
| 固件身份 | `sms_forwarding_dual` / `1.1.7-dual.2-idf555` |

SDK 显示 `v5.5.5-dirty`，原因是唯一活动的 certificate policy OID 补丁。审计已核对子模块提交，并反向应用该补丁，验证文件与 SDK 原文完全一致；没有混入 6.x TLS 源码。原共享 `C:\esp\v5.5.5\esp-idf` 未被本轮补丁修改。

构建使用 `--no-ccache`，已在构建入口及 CI 固定，并检查 CMake 缓存及编译命令确认关闭。新目录执行 fullclean，重新生成配置和全部目标；之后仅更新了同一迁移代码的中文注释并再次构建核验。没有使用旧 `build/idf6` 的对象、配置或镜像。

环境审计检查应用和 bootloader 共 **1007 个编译单元、2527 个实际依赖文件**，源码、组件、头文件路径均在本工程、指定 5.5.5 SDK 或 GCC 14.2.0 工具链内。外部目录启动 `tools/build.ps1` 也会正确进入工程根目录。错误 SDK 版本在 CMake 配置阶段拒绝。

机器上仍可保留其他 SDK/工具版本，是否混用以实际编译记录为准。本轮审计覆盖了最终产物所用路径和版本。

## 必要适配

- LPA 使用 Mbed TLS 3.6.6 原生 SHA-256，保留原确认码双重哈希算法和敏感缓冲清理。
- 5.5.5 不支持 `HTTP_EVENT_ON_STATUS_CODE`；在首段正文前读取已解析的 HTTP 状态，状态或协议头异常时禁止 BPP 解析。
- 仅应用 `patches/idf5.5.5/` 中的适配补丁。旧 6.0.2 补丁保留为历史资料，活动脚本不引用。
- 移除 6.x 专属交叉签名配置，使用 5.5.5 原生完整证书包验证；保留证书链、签名及主机名检查。
- 明确 5.5.5 的 FreeRTOS/环形缓冲 flash 放置、ELF coredump 与 SHA-256 配置。
- 安装工具命令同步为 esptool 4.x 语法；本轮只执行默认预演，不打开串口。
- 上游组件结构、双卡引脚、NVS/Wi-Fi 方式和 OTA 分区布局保持不变；应用与 bootloader 均使用 USB Serial/JTAG 控制台。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| 全量原生编译 | 通过，1,034 个应用构建步骤及 bootloader 构建；日志无编译 warning/error |
| 双卡、配置、队列、短信、推送、任务、网页主机回归 | 21 组全部通过 |
| SDK/交付专项 | 14 个测试全部通过，零跳过 |
| 证书回调 | 6,000 次成功/失败循环；密钥清理、未知根拒绝、其他错误标志保留通过；密码学边界使用桩 |
| LPA 5.5.5 适配 | 使用真实 SDK SHA-256 与独立 Python 预期值；HTTP 200/400/403/500 与协议头矩阵通过 |
| 错误 SDK / 错误镜像 | CMake 拒绝模拟 6.0.2；打包器拒绝单卡、6.0.2、错误 5.5.x 标识及损坏镜像 |
| 分区表 | SDK 原生解析、MD5、容量和源 CSV 对照通过；双 OTA 槽各 0x1A0000 |
| 镜像 | C3 身份、ESP 校验和、附加 SHA-256、应用/ELF 摘要关联通过 |
| 烧录、真实短信、TLS 服务交互、12 小时稳定性 | 本轮未执行，不计为通过 |

## 固件

输出：`dist/1.1.7-dual.2-idf555-candidate/`。应用 **1,380,880 字节**，单 OTA 槽 **1,703,936 字节**，剩余 **323,056 字节（18.96%）**。

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| `ota.bin` | 1380880 | `316fd6c535f048a2e290a7b2df59c0aad9eac12dfb5864c8761b6b4a25bbcdb4` |
| `bootloader.bin` | 19936 | `c0b77b894439abf367c03a50eae6eeaeedfb13622297d26cf89ec9f9d3b09218` |
| `partition-table.bin` | 3072 | `491e510e1dae5013ad4aa0d3b2b4856dd11e5d3dc2addc9f5f2b63f46c34fd3c` |
| `first-install-4MB.bin` | 4194304 | `54109eef74a8f94672e2a5e9d61ba11c577aa259bad89b17f23f9decd7014390` |

`first-install-4MB.bin` 是首次安装完整包，会覆盖 ESP 上旧业务配置；`ota.bin` 是应用 OTA 包，不能从地址 0 写入。均为未通过实机验收的候选。本轮没有执行安装或清除任何设备数据。

`manifest.json` 记录最终源码 Git 提交，`source-manifest.json` 记录源码逐文件摘要，`environment-audit.json` 记录 SDK/编译器/Python/组件/配置/分区核查。交付清单包含所有固件及环境说明的 SHA-256。

原始证据：`build/idf555-fullclean.log`、`build/idf555-build-final.log`、`build/idf555-build-verified.log`、`build/idf555-tests-final.log`、`build/regression-idf5.5.5/`、`build/idf555-reject-wrong-sdk.log`。旧 6.0.2 构建报告单独保留，不混作此次证据。

后续须在设备接入并获得烧录授权后完成身份/供电核对、Flash 备份、首次安装、双卡实际收发/通知、OTA、异常恢复与固定镜像 12 小时验收。来电和 eSIM 能力仍未实测。
