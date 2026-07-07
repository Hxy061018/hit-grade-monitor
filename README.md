# 哈工大教务成绩邮件提醒

这是一个哈工大本科教学管理与服务平台成绩检测脚本。它会使用 Chromium 浏览器登录教务系统，定时检查期末成绩；发现新出课程成绩或已有课程成绩变更时，会把课程名称和分数发到邮箱。

## 功能

- 每 30 分钟检查一次教务系统成绩。
- 两次检查之间每 5 分钟访问一次教务首页，尽量保持登录态。
- 支持期末成绩分页，会抓取多页成绩。
- 邮件只在“新出课程成绩”或“成绩变更”时发送。
- 邮件内容包含课程名称和成绩。
- 如果登录态失效并停留在登录页超过 60 秒，会发送需要手动登录的提醒邮件。

## 使用步骤

1. 安装 Python 3.10 或更高版本。
2. 解压本压缩包。
3. 双击 `setup.bat` 安装依赖。
4. 打开 `.env`，填写发件邮箱、SMTP 授权码、收件邮箱。
5. 双击 `refresh_cache.bat`，先登录一次教务系统并刷新当前已有成绩作为基准。
6. 双击 `run_monitor.bat` 启动长期监控。

## QQ 邮箱配置

`.env` 默认按 QQ 邮箱配置：

```env
SENDER_EMAIL="你的QQ号@qq.com"
SMTP_AUTH_CODE="QQ邮箱SMTP授权码"
RECEIVER_EMAIL="接收提醒的邮箱"
SMTP_HOST="smtp.qq.com"
SMTP_PORT=465
SMTP_USE_SSL=true
```

注意：`SMTP_AUTH_CODE` 不是 QQ 密码，需要在 QQ 邮箱设置中开启 POP3/SMTP 服务后获取。

## 登录说明

脚本不会保存或自动输入教务系统密码。第一次运行时会弹出浏览器，需要手动登录哈工大统一认证。之后脚本会使用本地浏览器登录态继续运行。

如果学校登录态过期，脚本会停在登录页等待手动登录，并通过邮件提醒。

## 常用命令

安装依赖：

```bat
setup.bat
```

刷新当前成绩缓存，不发送成绩提醒：

```bat
refresh_cache.bat
```

启动长期监控：

```bat
run_monitor.bat
```

测试邮件：

```bat
test_email.bat
```

## 不要分享的文件

不要把这些本地文件发给别人：

- `.env`
- `.venv/`
- `playwright_userdata/`
- `grades_cache.json`
- `check_grades.log`
- `check_grades.err.log`

本压缩包已经排除了这些文件。
