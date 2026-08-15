systemctl status orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
journalctl -u orbiboard-display -n 50 --no-pager
ls -la /run/orbiboard/frames/



sudo cp systemd/orbiboard-display.service systemd/orbiboard-module@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart orbiboard-display
sudo systemctl restart orbiboard-module@weather orbiboard-module@claude_usage
systemctl status orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
