systemctl status orbiboard-display orbiboard-module@weather orbiboard-module@claude_usage
journalctl -u orbiboard-display -n 50 --no-pager
ls -la /run/orbiboard/frames/
