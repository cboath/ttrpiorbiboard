# Adding a module

A module is one file: `orbiboard/modules/<id>.py`. Use `weather.py` (simple)
or `claude_usage.py` (has OAuth/refresh state) as a template.

1. **Write the module.**

   ```python
   from PIL import Image
   from orbiboard.modules.base import Module
   from orbiboard.render_utils import new_canvas, draw_centered_text, load_font

   class MyModule(Module):
       MODULE_ID = "my_module"
       DEFAULT_INTERVAL_SEC = 600

       def fetch(self, params: dict) -> dict:
           # Raise on any failure — base.py handles falling back to the
           # last-known-good cache and marking the render as stale for you.
           ...
           return {"value": 42}

       def render(self, data: dict, stale: bool) -> Image.Image:
           canvas, draw = new_canvas()
           draw_centered_text(draw, 120, 110, str(data.get("value")), load_font(40))
           return canvas

   MODULE = MyModule()   # required — this is what runner.py imports
   ```

   Never import `spidev`/`gpiozero`/`orbiboard.display.*` here — modules
   only fetch + render; only `orbiboard/display/server.py` touches SPI/GPIO.

2. **Preview it without hardware:**

   ```
   python3 scripts/sim_preview.py --module my_module
   ```

   Saves `state/previews/my_module.png` so you can check the layout on your
   own machine before it ever touches a Pi.

3. **Wire a spare CS pin** (already provisioned — see `docs/WIRING.md`) and
   add one entry to `config/modules.yaml`:

   ```yaml
   my_module:
     enabled: true
     cs_pin: 13   # one of the reserved slots
     refresh_interval_sec: 600
     params: {}
   ```

4. **Enable + start it:**

   ```
   sudo systemctl enable --now orbiboard-module@my_module
   ```

No changes to any other module, the display server, or existing systemd
units — that's the whole point of the split.
