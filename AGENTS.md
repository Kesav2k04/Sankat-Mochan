# Project rules — Sankat-Mochan

1. Only use MIT, Apache-2.0, or BSD-licensed open-source dependencies. Never suggest or add a GPL, AGPL, or proprietary-licensed package without flagging it first.
2. Never hardcode API keys, tokens, or secrets. Use environment variables or a local .env file that is gitignored.
3. If you adapt a code pattern from a known public source (Stack Overflow, a GitHub repo, a tutorial), say so in a comment with the source, and make sure that source is itself open-license.
4. Do not reproduce proprietary SDK internals from training data. Only use Qualcomm/Arduino APIs exactly as documented in their official public docs.
5. Prefer well-known, widely-used libraries over obscure ones — they're easier for the team to verify quickly under time pressure.
6. Flag any security-sensitive code (auth, data storage, network handling) explicitly so a human reviews it before merge.
7. Never build a prompt by directly concatenating untrusted incoming SOS text next to system instructions. Wrap untrusted input in a clear data tag (e.g. `<incoming_sos_message>...</incoming_sos_message>`) and instruct the model to treat its contents as data only, never as commands.
8. All incoming mesh messages (SOS text, voice audio, sensor data) are untrusted input. Validate size, type, and expected field ranges before processing, even in local demo code.
9. Rendered translated or transcribed text on any dashboard must be inserted as plain text, never as raw HTML.
10. Do not display raw error messages, stack traces, or file paths on the live dashboard. Log them to a file instead and show a short generic status message.
