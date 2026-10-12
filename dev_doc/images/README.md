# 工作原理图

`workflow.svg` 为自包含的 SVG 动画，无脚本与外部资源。主体保持黑白，通道图标保留品牌颜色，红色虚线表示丢弃分支。展示全部 10 种推送方式及 SMTP 邮件；动画依次演示单通道选择与丢弃，实际可同时启用最多 5 个推送通道。系统开启减少动态效果时显示静态图。

左侧分为上方的短信接收与处理、下方的 Web UI 功能介绍。Web UI 通过双向虚线连接软件和 eSIM，展示在线收发短信、定时任务、eSIM 激活码下载与启用、转发配置、网络状态和维护升级。

图标来源：

- 项目 Logo：[仓库品牌素材](../../assets/brand/README.md)。
- Bark：[官方文档站图标](https://bark.day.app/_media/Icon.png)。
- Telegram：[Simple Icons](https://github.com/simple-icons/simple-icons/blob/develop/icons/telegram.svg)，CC0。
- Gotify：[官方站点图标](https://gotify.net/img/favicon.png)。
- Server酱：[官方站点图标](https://the7.ft07.com/sct/images/favicon.png)。
- 钉钉、飞书与 PushPlus：[PushPlus 官网的通道图标](https://www.pushplus.plus/)。
- POST JSON、GET、自定义模板与邮件使用通用接口、链接、模板、信封图形。

通道品牌图标仅用于标识对应软件，保留原始配色并内嵌于 SVG。
