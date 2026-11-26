# serial-spm-mcp

An MCP server combining serial device control with passive capture through Electronic Team Serial Port Monitor (SPM).

This repository is a fixed snapshot based on `pyserial-mcp` 0.8.0, extended with SPM automation. The package version is `serial-spm-mcp` 0.8.1. Direct runtime dependencies are pinned in `pyproject.toml`.

## Features

The server retains the serial tools from its upstream base, including port discovery, baud detection, interactive sessions, one-shot commands, text and binary I/O, prompt handling, signal control, logging, and XMODEM transfers.

It adds SPM integration:

- Starts SPM in Terminal view before opening or probing a local COM port.
- Keeps SPM open after the serial session closes. Use `spm_close_monitor` only when the user asks to close SPM.
- Saves captures under `<workspace>/logs/spm/`.
- Provides `spm_list_monitors`, `spm_start_monitor`, `spm_read_log`, and `spm_close_monitor` MCP tools.
- Stores monitor state under `<workspace>/.serial-spm-mcp/`.

SPM capture works on Windows with local COM ports. Serial tools can still use network serial URLs such as `socket://` and `rfc2217://`, but SPM cannot monitor those URLs. Monitoring a port already held by another application may require SPM Professional or Company. If SPM is missing or cannot start, the serial operation can continue and reports an SPM warning.

Terminal view is suited to readable received text. For binary analysis or detailed read/write direction records, use SPM's Dump or Table views manually. Captures may contain sensitive serial output; review logs before sharing them.

## Install with uv

Install the tool from this GitHub repository:

```powershell
uv tool install git+https://github.com/wichayen/serial-spm-mcp.git
```

Register the installed server with Codex:

```powershell
codex mcp add serial-spm-mcp --env "SERIAL_SPM_WORKSPACE=D:\hong\github\serial-spm-mcp" -- serial-spm-mcp
```

If Codex cannot find the installed executable, run `uv tool update-shell` and restart Codex. Set `SERIAL_SPM_MONITOR_EXE` if SPM is installed outside the standard locations.

## Example workflows

For a one-shot command:

```text
serial_execute(port="COM3", data="help")
```

For an interactive session, use `serial_open`, one or more serial commands, then `serial_close`. Closing the serial session releases the COM port but leaves SPM open.

To inspect a capture, call `spm_read_log(port="COM3", tail_lines=100)`. Use `pattern` to filter matching lines. Logs remain readable after closing SPM.

## References

1. **Serial MCP base:** [alxgmpr/serial-mcp](https://github.com/alxgmpr/serial-mcp), pinned to upstream commit [0673565](https://github.com/alxgmpr/serial-mcp/commit/0673565fb6465a1ec1d23731d879c0b2e025665b) (`pyserial-mcp` 0.8.0). It provides the serial MCP server and serial communication tools.
2. **SPM capture workflow reference:** [Electronic-Team/serial-agent-toolkit — spm-serial-capture](https://github.com/Electronic-Team/serial-agent-toolkit/tree/main/skills/spm-serial-capture). Its guidance informed the SPM capture workflow adapted for this MCP server.

## License

[MIT](LICENSE). Serial Port Monitor is a separate product from Electronic Team and is subject to its own license.
