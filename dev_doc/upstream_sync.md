# 上游更新：提醒、批准、候选构建

Fork：<https://github.com/Elon-Smith/sms_forwarding>。默认分支 `codex/upstream-dual-modem` 保存双模组工程；`master` 是批准过的上游源码对照。`origin` 为本 Fork，`upstream` 为 `MineSunshineone/sms_forwarding`。固定 SDK 5.5.5，不自动合并 PR、发布稳定版或访问设备。

初次配置验证见 [2026-10-18 验证记录](upstream_sync_validation_20261018.md)。

## 当前版本与回退

同步配置前已保存当前修正，回退标签为 `codex/dual-idf555-before-sync-20261018`，提交 `30af225867f643b1bc832e3b1be9a1c741850610`。硬件验收仍未完成。工作区外保留经验证的 Git bundle、当时固件和 SHA-256 清单；原始日志、号码、凭据、Flash 备份不上传。

需要回退源码时，从该标签建立新分支；不强制覆盖工作分支。固件回退必须另行确认设备、分区和配置兼容性，本流程不执行烧录。旧本地工程仍保留，不从其导入代码或配置。

## 日常操作

1. [检查上游更新](https://github.com/Elon-Smith/sms_forwarding/actions/workflows/upstream-check.yml)每天约 09:17（UTC+8）运行，也可以点击 **Run workflow**。无更新时只记录成功摘要；有更新时创建并分配给仓库所有者的 `upstream-sync` Issue。通知遵循 GitHub 账号的通知设置。
2. 阅读 Issue 中的提交范围与变更。决定同步后打开 [批准同步并构建](https://github.com/Elon-Smith/sms_forwarding/actions/workflows/upstream-approve.yml)，分支保留默认双模组分支，填写 Issue 编号和提醒中的完整 40 位上游 SHA，再点击 **Run workflow**。
3. 批准仅适用于提醒中的上游和双模组基线。基线变化会使旧提醒失效并重新检查；新上游提交不会被偷偷包含。仅 `Elon-Smith` 可以批准或重跑此流程。
4. 无冲突时创建草稿 PR，运行回归与原生构建。成功后 PR 转为可审核；失败保持草稿，日志链接写回 PR/Issue。同一请求重复批准不会重复创建或构建。需要重试失败构建时使用原 Actions 运行的 **Re-run failed jobs**；需要修改候选代码时应人工复查并手动构建确切的新 SHA，原结果不会自动认定新代码通过。
5. 在关联 Actions 运行的 **Artifacts** 下载候选包。保留 30 天，名称包含上游 SHA 和源码 SHA。通过代码审核和必要实机检查后，再人工合并 PR、决定是否 OTA。创建候选不表示设备验收通过。

## 冲突和兼容边界

正常 Git merge 保留双方历史；不使用强制覆盖、不自动选择 ours/theirs。文本冲突、上游历史改写，以及流水线、同步/打包/审计脚本、SDK 补丁、CMake、默认 sdkconfig、分区表的变化，均停止自动处理并在 Issue 列明原因。即使 Git 能合并这些文件，也需要人工适配；不静默丢弃上游改动。主分支保持不变，不产生候选固件。

上游采用 6.x 的新接口也可能使 5.5.5 编译失败。这时调整兼容代码，而不是安装 6.x 绕过检查。完成适配需记录新的基线，再使用新提醒批准。

`upstream.lock.json` 是当前已合入上游的唯一机器可读来源：仓库、分支、完整提交 SHA 和固定 SDK。仅准备成功的合并提交更新其 SHA；打包校验该 SHA 是当前源码祖先。候选分支、上游对照 `master` 更新不等于双模组主分支已合并。

## 构建与权限

本机 SDK 入口为 `C:\esp\v5.5.5\esp-idf`，通过 `IDF_PATH` 或 `-IdfPath` 指定；脚本不写死本机盘符。仍应用现有仓库管理的 5.5.5 补丁。CI 使用 `espressif/idf:v5.5.5`，验证 SDK 提交、工具链、补丁、源文件路径、网页资源、镜像标识和 OTA 容量。

候选构建任务只有读取权限且不持久化 checkout 凭据。创建分支/PR、发送状态通知使用独立任务，只执行默认分支的控制脚本，不运行候选代码；不需要个人访问令牌或设备凭据。构建结果由批准工作流直接调用复用流程取得，不依赖机器人 PR 是否自动触发第二次 CI。

产物包括完整首次安装包、OTA 包、源码清单、环境审计和 SHA-256。`hardware_acceptance` 保持 false。首次安装包会覆盖业务配置；日常 OTA 使用 `ota.bin`，不能将完整包当成 OTA 上传。

## 定时任务检查

GitHub 定时任务可能延迟；公开仓库连续 60 天无活动时可能自动停用。可到“检查上游更新”页面查看最近运行时间、重新启用或手动运行。Fork 的 Actions、Issues 和工作流创建 PR 权限必须开启；不要将默认分支改回未包含本流程的 `master`。

本流程的定时检测不依赖本机或 Codex 在线。暂停更新提醒可在 Actions 禁用“检查上游更新”，不会修改源码或设备。
