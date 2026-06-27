# 部署指南

## 服务器部署（Linux）

```bash
# 克隆
git clone https://github.com/tsingyun/weibo-monitor.git
cd weibo-monitor

# 一键安装
bash scripts/install.sh

# 编辑 .env（填写你的微博 Cookie 和 Telegram 配置）
nano .env

# 后台运行（使用 screen 或 systemd）
screen -S weibo-monitor
python app.py
# Ctrl+A D 断开
```

## 使用 systemd 自启动

```bash
sudo nano /etc/systemd/system/weibo-monitor.service
```

```
[Unit]
Description=岁己SUI 微博监控
After=network.target

[Service]
Type=simple
User=your-user
WorkingDirectory=/path/to/weibo-monitor
ExecStart=/usr/bin/python3 app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable weibo-monitor
sudo systemctl start weibo-monitor
```

## Windows 部署

```bash
# 双击即可（会自动弹出命令行窗口）
python app.py

# WebUI 可在浏览器打开
# http://localhost:8765
```
