# Model connection and natural-language generation

## Existing API endpoint (selected workflow)

Open the sidebar's Model settings, or the settings button in the description dialog.

1. Choose **OpenAI-compatible · chat completions**.
2. Enter the provider's API base URL, for example `https://api.openai.com/v1`. Do not append `/chat/completions`; the adapter adds it. For another provider, use its documented compatible base URL.
3. Enter an exact model identifier available to your account. The application does not guess or substitute models.
4. Enter the API key. Save configuration, then Test connection.
5. In From description, select Natural language. Write the process in your own words and Generate diagram. Review the source quotes, assumptions and control-flow result. Only then create the family.

The adapter sends `messages` and `response_format: {type: json_object}` to the chat-completions endpoint. Your provider/model must support that contract. A syntactically compatible endpoint is not a guarantee of model quality or available context length. Models must follow the schema, produce valid activity evidence quotes, and generate supported acyclic graphs. Invalid output is repaired once with validator diagnostics, then rejected if still invalid.

Keys stay in server memory. Reopen settings and replace a key to rotate it. Restarting resets UI-entered configuration. Do not paste keys into process descriptions, screenshots, backups or project source.

For persistent configuration, set process environment variables before launching:

```powershell
$env:STUDIO_AI_PROVIDER = "openai-compatible"
$env:STUDIO_AI_BASE_URL = "https://api.openai.com/v1"
$env:STUDIO_AI_MODEL = "YOUR_EXACT_MODEL_ID"
$env:STUDIO_AI_API_KEY = "YOUR_KEY"
python backend/server.py
```

This is an example of local environment setup; no real credentials are shipped. Environment values are not exported by the application. Credentials at a remote endpoint are sent only over HTTPS. Redirects are rejected so credentials are not forwarded to an unexpected destination.

## Local Ollama option

Start Ollama and install an appropriate model through its official tools. Choose Ollama in settings, set `http://localhost:11434`, and enter the installed model name. The adapter uses `/api/chat`, JSON output and non-streaming responses. The application does not ship model weights or install Ollama automatically.

## What is and is not guaranteed

The current description is sent verbatim after outer whitespace normalization. Samples are only inserted by explicit example selection. Switching modes retains the text. Editing text after generation invalidates the preview. Responses are limited to 2 MB and two generation attempts; each model call has a 120-second timeout.

Every generated activity needs a supporting quote that appears exactly in the description. This detects fabricated citations, not invented interpretations supported by an overly broad quote. The preview requires human semantic review. Control-flow validation cannot establish compliance with a law, financial policy or real business requirement.

No live external endpoint was configured during delivery. Adapter tests use an explicit local fixture server; those tests verify payload/response behavior, not a real model's reasoning quality.

## Troubleshooting

- **No model connected:** enter provider, URL and model name in settings.
- **HTTP 401/403:** verify key and account/model permission.
- **HTTP 404:** verify base URL and exact model name.
- **HTTP 400:** the chosen model may not accept the JSON-mode/chat contract.
- **Could not reach endpoint:** verify network access or that local Ollama is running.
- **Generation invalid after repair:** refine decisions, parallel work and completion; use a stronger model if necessary. Nothing is saved on failure.
- **Loop/timer/collaboration requirement:** this release cannot implement that execution behavior. Do not present an acyclic approximation as equivalent to the original process.

Official protocol references: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [Ollama chat API](https://docs.ollama.com/api/chat).
