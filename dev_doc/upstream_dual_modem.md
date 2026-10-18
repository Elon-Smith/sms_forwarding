# 上游原生 ESP32-C3 双模组候选版

当前状态：`CANDIDATE_HARDWARE_PENDING`。已完成目标 C3 的备份、安装和部分实机验收；正常测试卡 A 卡分别在两路通过短短信、中文长短信及 HTTP 推送，异常测试卡 B 卡的短信异常随卡移动。固定镜像 12 小时采样及两张正常卡的并发验收仍待完成，不能标记为“可直接使用”。详见 [2026-10-15 实机报告](hardware_test_20261015.md)。保留旧工程和外部归档，不替换原工作目录。

## 基线和目录

- 上游：<https://github.com/MineSunshineone/sms_forwarding/tree/d4271d46f40bca215d2fba966b83051a1a4460be>，1.1.7，提交固定为 `d4271d46f40bca215d2fba966b83051a1a4460be`。
- SDK：ESP-IDF **5.5.5**，使用适配后的 `tools/apply_idf_patches.py` 与 `patches/idf5.5.5/`；不自动升级。SDK 改动按 2026-10-15 最新指令覆盖原 6.0.2 计划。应用版本 `1.1.7-dual.2-idf555`，项目标识 `sms_forwarding_dual`。
- 开发分支 `codex/upstream-dual-modem`。开发目录为原工程的同级目录 `SMS-Forwarder-C3-upstream-dual`；这是交付前的独立工作副本。
- 保留 `main/`、`components/`、`code/web_src/`、上游 PDU/TLS/LPA 实现。没有迁入本地旧 Arduino/IDF 源码、凭据、适配层或配置。新增的 `idf_board` 集中板级约束，`idf_network` 串行化 TLS 资源。
- 编译依赖由上游源码和固定 SDK 提供；没有要求安装旧工程 Arduino 库。主机测试需要 Python 3、Node.js、C++17 编译器（Linux g++/clang++，Windows 可用 Zig C++，通过 `CXX` 指定）。

## 接线和准入

方向以 ESP32-C3 为准，TX 接模组 RX，RX 接模组 TX。

| 对象 | 外设 | TX | RX | EN |
| --- | --- | --- | --- | --- |
| SIM1 | UART1 | GPIO3 | GPIO4 | GPIO5 |
| SIM2 | UART0 | GPIO6 | GPIO7 | GPIO10 |
| 调试、下载 | USB Serial/JTAG | GPIO18/19 | — | — |

`components/idf_board/include/idf_board.h` 编译检查 UART 唯一、GPIO 唯一、BOOT/板载 LED/启动绑带与 USB 冲突。应用及 bootloader 控制台均使用 USB Serial/JTAG，UART0 不输出应用控制台。没有启用屏幕。

预期模组型号为两块 `ML307C-DC-CN-MBRH0S00`。软件能分配 C3 的两路 UART，并独立处理两卡；供电、电平和 AT 固件兼容性仍须上电核对。确认使用的具体模组板是否已带电平转换，不能把裸模组 UART 电平当成 ESP32 的 3.3 V。检查 EN 的极性/供电控制实际行为、供电分支、共地，以及两卡同时注册/发送时的电压和复位。没有这些实物证据不能承诺稳定性。

## 运行结构与边界

`idf_modem` 内两份 `ModemInstance` 各拥有 UART、事件队列、命令队列（4 项）、任务、URC 缓冲及故障状态。其他组件经带 `IdfModemId` 的接口提交操作，单卡兼容重载固定指向 SIM1。没有可变的“全局当前卡”。AT 等待持续解析 URC；CMGS 提示符、PDU 和结果由同一事务处理。超时增加事务代际并恢复对应模组，旧请求失效，不自动重发结果不明的计费操作。

`idf_sms` 两份实例隔离 PDU 对象、长短信、去重、存储索引、发信队列。PDU 库内部少量全局解析状态通过短互斥保护。换卡增加身份代际：旧 URC、未完成分段及待发短信失效；读/确认/删除存储索引的请求携带代际。独立实例实现跨卡去重隔离，换卡重置实现卡身份隔离。保留上游“接收→收件箱→转发队列→各投递完成确认”的生命周期，没有替换为旧工程实现。

推送和 SMTP 共用上游工作线程、队列容量与完成关联；通知正文包含 `[SIM1]` / `[SIM2]`。推送重试保留接收卡、接收号码快照和收件箱完成 ID。共享网络互斥限制 HTTP/SMTP/LPA 同时建立 TLS 会话。断网恢复继续按原退避处理；RAM 队列不提供断电补发保证。

全局收件箱仍为 50 条、发件箱 10 条、正文预览上限 320 字节，五个推送通道、六个自定义定时任务，不因双卡翻倍。发件箱重填仍遵循上游预览数据边界，长短信需检查完整正文。没有持久化完整短信数据库。

定时任务绑定卡位及创建时的配置快照，执行前先持久化尝试标记。换卡或配置已改变时取消旧任务；完成时只更新仍匹配的任务槽。计费动作失败或结果不明不做即时自动重试，下一次正常周期仍受用户配置控制。默认保号、自动定时任务、每日重启及心跳保持上游关闭状态。心跳启用后汇总两卡状态。

eSIM 操作只占用对应模组会话；另一卡收信任务继续运行。成功读取 EID 才认定 eSIM 能力已识别；超时/未识别为“待确认”，相关变更按钮及后端变更接口受能力校验。来电能力依据 AT 支持探测展示，**不等于实际来电成功**。普通 SIM 默认没有 PIN/PUK 凭据，不自动解锁或切换 Profile。两卡来电、eSIM 下载/切换均未实测。

## 配置与 HTTP

Wi-Fi、Web 账号、时间、邮件、五通道共享。网络/APN/运营商/号码备注、PIN/PUK、保号设置按卡保存。转发规则前缀 `SIM1:` 或 `SIM2:` 限定来源，不加前缀表示全部；保留原有 tab 分隔规则语法。

模组 HTTP 接口使用查询参数 `sim=1|2`。缺省为 SIM1；空、非法和重复 `sim` 拒绝。响应头 `X-Modem-Sim` 标识处理卡位。状态 `/status` 保留选中卡的原字段并增加 `sim`、`modems[]`、`firmwareElfSha256`；后者是应用 ELF 的 SHA-256，用于固定运行镜像识别，与 OTA 文件 SHA-256 区分。

网页选卡通过 URL 与页面实例固定卡位；切卡重新载入，不改变已提交任务。任务保存带目标 SIM，手动执行按任务目标提交。`/messages?sim=2` 只列 SIM2，`scope=all` 列全部；记录带 SIM，删除和重新转发校验记录来源。配置导出在同一快照内包含两卡，SIM2 字段使用 `sim2.` 前缀，任务使用 `stNSim`。

配置继续用 ESP-IDF NVS 键/类型，但为避免两卡半份保存，改用**现有 `smsdata` 分区**里的独立双 bank：`cfg0/cfg1` 存全局和 SIM1，`modem0/modem1` 存对应 bank 的 SIM2，`dual_cfg/active` 最后提交选择器。先检查空间，再完整写入非活动 bank，最后切换；RAM 只在成功后更新。收件箱占用独立命名空间，未改变分区表。不能用上游单卡固件回读该双卡配置。

新配置没有活动 bank 时使用上游默认值，不从旧配置导入。候选固件没有编译期 Wi-Fi 凭据。首次完整安装覆盖旧 ESP Flash 业务数据，**不发送清空模组短信命令**；启动后收到/读到的存储短信仍按上游正常接收及确认后处理流程处理。

## 构建和回归

Windows，在已安装独立 IDF 5.5.5 环境后：

```powershell
# 指向自己的安装路径；脚本不包含固定盘符。
$env:IDF_PATH = '<ESP-IDF 5.5.5 目录>'
$env:IDF_TOOLS_PATH = '<IDF 工具目录>'
./tools/build.ps1
# Windows 主机测试需另行配置 CC / CXX（见下文）；构建入口清理其继承值。
python -X utf8 tools/test_all.py
python -X utf8 tools/package_candidate.py
```

若 Windows 主机编译器为 Zig，可设置 `$env:CXX = '<zig.exe 的路径> c++ -Dtimegm=_mkgmtime -Wno-nullability-completeness'`。C 测试同时设置 `$env:CC = '<zig.exe 的路径> cc'`。含空格的编译器路径用引号包住。Linux 使用 `CXX=c++`，导出 IDF 环境后运行上游补丁脚本，再 `idf.py --no-ccache -B build/idf5.5.5 -D SDKCONFIG=build/sdkconfig.idf5.5.5 build`。网页只编辑 `code/web_src/`，执行 `python tools/build_web_assets.py` 更新资源；CI 检查生成文件一致性。

CI 固定 `espressif/idf:v5.5.5`，先主机回归再编译并上传候选 artifact。当前取消自动发布稳定 Release。构建日志、回归原始输出位于忽略跟踪的 `build/`；本次结果见 `dev_doc/idf555_rebuild_report.md`；旧 6.0.2 记录保留于 `dev_doc/upstream_dual_test_report.md`，不代表本次构建。

构建目录固定为 `build/idf5.5.5`，配置为 `build/sdkconfig.idf5.5.5`。不复用 `build/idf6` 或机器级 ccache。构建后自动核查 SDK 提交、全部子模块及活动补丁、GCC 14.2.0、IDF 5.5 Python、组件/编译路径；打包再次核查，并验证应用和 bootloader 的 ESP 校验和与附加 SHA-256、应用/ELF 对应关系。详情保存在 `environment-audit.json`。

## 首次安装与配网

当前实机镜像位于 `dist/1.1.7-dual.2-idf555-hwfix-candidate/`；原 `dist/1.1.7-dual.2-idf555-candidate/` 保留为首次构建记录。当前包包含：

| 文件 | 用途 |
| --- | --- |
| `first-install-4MB.bin` | 从地址 0 写入的完整 4 MiB 首次安装包，覆盖旧 ESP 配置/收件箱/分区/应用 |
| `ota.bin` | 后续网页 OTA，仅应用镜像，不能从地址 0 烧录 |
| `bootloader.bin`、`partition-table.bin` | 对照和恢复辅助文件 |
| `manifest.json`、`SHA256SUMS.txt` | 芯片、版本、SDK、ELF 身份、各文件大小及 SHA-256 |
| `environment-audit.json` | SDK、工具链、编译路径和应用/bootloader 校验记录 |
| `source-manifest.json` | 本地源码逐文件校验，用于关联确切源码 |

目标硬件接入后先核对芯片、MAC、4 MiB Flash、两块 ATI 和接线电平/供电。工具默认预演，不打开串口：

```powershell
# 在 ESP-IDF Python 环境运行；COM 和 MAC 必须来自本次硬件识别。
python tools/first_install.py --port '<实际COM>' --expected-mac '<实际MAC>' --backup-dir '<工作区外备份目录>'
# 完成硬件检查后，同一命令添加 --apply 才实际安装。
```

实际安装先核对 MAC/容量，再读取完整 Flash 两次，要求大小和 SHA 一致，保存备份与记录，之后写入新完整镜像并 `verify-flash`。没有使用 `erase-flash`，也不操作模组短信存储。写入完成后手动断电重启。

连接 `SMS-Forwarder-XXXX` 开放配网热点，访问 `http://192.168.1.1/`，默认账号 `admin/admin123`。在网页重新配置 Wi-Fi、账号、通知通道和两卡号码备注；不导入旧凭据。两卡分别刷新型号/注册/身份状态，保持不使用的计费任务关闭。

后续 OTA 上传 `ota.bin` 并使用清单 SHA-256。应用检查 ESP-IDF 镜像有效性、项目标识 `sms_forwarding_dual` 和版本中的 `-dual.`，拒绝上游单卡镜像及错误文件后不会切换启动分区。实机已验证有效 OTA、损坏文件拒绝，以及校验和正确但项目标识错误的镜像拒绝；仍按候选版交付。

## 硬件验收与 12 小时采样

1. 两卡真实收信，包含相同发件人/内容与交错长短信；逐条核对 SIM 来源、收件箱、通知正文及完成状态。
2. 从网页指定卡发送，核对收件人收到的卡号和正文。2026-10-15 用户已明确授权自动化互发测试；本轮使用持久化计费段预算和唯一标记，结果不明不自动重发，不启用自动保号。该授权不表示可持续自动发送无关短信。
3. 仅重启一块模组，另一块继续收信；检查无串口越界、复位或供电掉压。随后进行 Wi-Fi 断开恢复、冷启动与积压恢复。
4. 实测 OTA 正确镜像、错误/单卡镜像拒绝；记录升级前后镜像及启动结果。
5. 冻结最终镜像，连续运行 12 小时，按分钟采样。采样只 GET `/status`：

```powershell
$env:SMS_WEB_USER = 'admin'
$env:SMS_WEB_PASSWORD = '<当前网页密码>'
python -X utf8 tools/soak_dual.py --url 'http://<设备地址>' --output hardware-tests/soak.jsonl
python -X utf8 tools/soak_dual.py --analyse hardware-tests/soak.jsonl
```

采样文件独占新建，不把不同运行拼接。记录版本/ELF 身份、堆、运行时长、两卡 UART 错误和任务栈等，不记录密码、号码、ICCID 或短信正文。发生请求失败、采样断档、镜像改变、重启或 UART 错误即未通过。预热 10 分钟后四段堆中位数连续下降且总降幅超过 4 KiB，标记待排查。

采样程序只评价可观测指标，不自动宣称整机通过；跨卡操作、通知正文、供电、真实来电/eSIM 必须另附实测证据。缺少条件的功能标“未实测/不可用”，不计为通过。

## 回退与最终替换

旧工程、Git 未提交文件、私有配置、实测资料和旧构建已归档到工作区外，清单与校验说明见测试报告。当前旧目录没有清空；目标设备已在两次完整 Flash 备份一致后安装新分区和固件。硬件验收全部完成后再把新分支交付到原目录，按明确目录清单清理旧残留，保留外部归档与 Git 历史。

设备回退使用本次 `first_install.py` 保存的完整 Flash 备份及原 MAC/容量核验；旧分区和配置必须随旧应用完整恢复，不把旧应用与新分区混刷。代码回退使用外部归档或原分支，不向新分支混入旧适配层。
