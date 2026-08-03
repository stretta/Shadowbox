# Shadowbox custom UI editor screenshots

These PNGs are deterministic 800x480 documentation renders made with the same
Pillow canvas and `ShadowboxRenderer` used by the Waveshare 5-inch touch UI.
They do not require a connected display or framebuffer.

Regenerate the complete set from the repository root:

```bash
.venv/bin/python tools/generate_ui_screenshots.py
```

The active Python environment must contain the packages in `requirements.txt`,
including Pillow. Use `--output PATH` to write a copy somewhere else.

## Parameter-scoped editors

| Editor | Screenshot |
| --- | --- |
| TTID | [ttid.png](ttid.png) |
| Step 16 | [step16.png](step16.png) |

## Export-level instance surfaces

| Surface | Screenshot |
| --- | --- |
| Organ | [organ.png](organ.png) |
| Analog Sequencer | [analog-sequencer.png](analog-sequencer.png) |
| Time Domain Scope | [time-domain-scope.png](time-domain-scope.png) |
| Tuner | [tuner.png](tuner.png) |
| List Sequencer | [list-sequencer.png](list-sequencer.png) |
| List Velocity Sequencer | [list-vel-sequencer.png](list-vel-sequencer.png) |

`manifest.json` provides the same inventory in machine-readable form.
