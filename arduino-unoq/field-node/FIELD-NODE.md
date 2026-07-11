# field-node — the UNO Q's Linux-side mesh code

This is the **same code the Raspberry Pi gateway runs** (`pi-code/`), deployed here so the
Arduino UNO Q is fully self-contained: you upload only the `arduino-unoq/` folder to the
UNO Q and nothing else. The Pi keeps its own copy in `pi-code/`.

The `.py` files, `run.sh` and `config.example.json` here are **copies of `../../pi-code`**.
`pi-code/` remains the single source of truth. If you change the mesh code there, refresh
this copy with:

```bash
../sync-from-pi-code.sh        # from inside arduino-unoq/field-node
```

The only file that is NOT a copy is `config.json` — it is preconfigured for this board:
the `field` node, radio over the serial modem. Edit `serial_port` in it to match your
device (`ls /dev/ttyACM* /dev/ttyUSB*`).

## Run

```bash
./run.sh check     # pre-flight: deps, Bluetooth, and the serial LoRa modem
./run.sh           # start the field node (waits for phones, then relays over LoRa)
```

`run.sh` builds a venv in `arduino-unoq/.venv`, installs `bleak` + `requests` + `pyserial`
(all permissive-licensed), unblocks Bluetooth, and starts the field node.
