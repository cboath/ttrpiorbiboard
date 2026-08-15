systemctl status orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
journalctl -u orbiboard-display -n 50 --no-pager
ls -la /run/orbiboard/frames/



sudo cp systemd/orbiboard-display.service systemd/orbiboard-module@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart orbiboard-display
sudo systemctl restart orbiboard-module@weather orbiboard-module@claude_usage
systemctl status orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage





On the Pi, run:


systemctl is-active orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
If any of those say active, stop them before running the standalone test:


sudo systemctl stop orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
python3 scripts/test_display.py
Then restart them afterward:


sudo systemctl start orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage