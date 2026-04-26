# Gemini API Setup

Joe uses **gemma2:2b** running locally by default for all narration and context extraction, ensuring absolute privacy. However, you can configure an optional **Gemini 2.5 Flash** API key for richer, faster closing monologues. You can use either a free or premium API key.

> **Note on API limits:** If you are using a free Gemini API key, Google limits requests to 15-20 per day. For unlimited chats without worrying about rate limits, stick to the default local SLM (`gemma2:2b`).

**Get your key:**
1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Create an API key
3. Paste it into `config.yaml` in the project root:

```yaml
gemini_api_key: "AIzaSy..."
```

*(Alternatively, you can set it as an environment variable `GEMINI_API_KEY`, but `config.yaml` is recommended for reliability.)*

---

### bash (default on most Linux distros)
```bash
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.bashrc
source ~/.bashrc
echo $GEMINI_API_KEY   # verify
```

### zsh (default on macOS, popular on Linux)
```zsh
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.zshrc
source ~/.zshrc
echo $GEMINI_API_KEY   # verify
```

> **Note (zsh users):** If your `.zshrc` sources `.bashrc`, you may see `shopt` errors because `shopt` is bash-only.  
> Check with `grep bashrc ~/.zshrc` and remove the offending line if found:
> ```zsh
> sed -i '/bashrc/d' ~/.zshrc
> ```

### fish
```fish
set -Ux GEMINI_API_KEY "your_key_here"
echo $GEMINI_API_KEY   # verify
```

### ksh / dash
```sh
echo 'export GEMINI_API_KEY="your_key_here"' >> ~/.profile
. ~/.profile
echo $GEMINI_API_KEY   # verify
```

---

### System wrapper (applies to all shells)

The `joe` system command at `/usr/local/bin/joe` is a bash script. If you want the key baked in at the wrapper level (so it works regardless of which shell calls it), edit it with:

```bash
sudo nano /usr/local/bin/joe
```

The file should look like this — add the `export` line:

```bash
#!/bin/bash
export GEMINI_API_KEY="your_key_here"
source /path/to/your/venv/bin/activate   # added by installer
cd /path/to/JOE-GOLDBERG
exec python /path/to/JOE-GOLDBERG/joe.py "$@"
```

This guarantees narration works even when Joe is launched from a desktop icon, a cron job, or any shell that hasn't loaded your personal config.

---

Joe falls back to local Ollama automatically if Gemini is unavailable. **Never hardcode the key inside source code** — environment variable only.
