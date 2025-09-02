#!/usr/bin/env bash
set -e

echo "Setting up repository..."

# Build authenticated repo URL
if echo "$REPO_URL" | grep -q "gitlab.com"; then
  REPO_URL_WITH_TOKEN=$(echo "$REPO_URL" | sed "s|https://gitlab.com/|https://oauth2:${GIT_AUTH_TOKEN}@gitlab.com/|")
else
  REPO_URL_WITH_TOKEN=$(echo "$REPO_URL" | sed "s|https://github.com/|https://${GIT_AUTH_TOKEN}@github.com/|")
fi

git clone -b "$TARGET_BRANCH" "$REPO_URL_WITH_TOKEN" /workspace/repo
cd /workspace/repo

# Configure git
git config user.email "claude-code@automation.com"
git config user.name "Claude Code Automation"

echo "📋 Will extract changes as patch for later PR creation..."

echo "Starting ${MODEL_CLI^^} Code with prompt..."

# Decode prompt
PROMPT_TEXT=""
if [ -n "$PROMPT_B64" ]; then
  PROMPT_TEXT=$(echo "$PROMPT_B64" | base64 -d)
fi
printf "%s" "$PROMPT_TEXT" > /tmp/prompt.txt

# Ensure temp directory exists
mkdir -p /tmp

# Setup Claude credentials if provided
if [ "$MODEL_CLI" = "claude" ]; then
  mkdir -p ~/.claude
  if [ -n "$CLAUDE_CREDENTIALS_B64" ]; then
    echo "📋 Writing credentials to ~/.claude/.credentials.json"
    echo "$CLAUDE_CREDENTIALS_B64" | base64 -d > ~/.claude/.credentials.json
    echo "✅ Claude credentials configured"
  else
    echo "⚠️  No credentials content available"
  fi
fi

# Execute model-specific CLI
if [ "$MODEL_CLI" = "codex" ]; then
  echo "Using Codex (OpenAI Codex) CLI..."
  
  # Check if OPENAI_API_KEY is set
  if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ OPENAI_API_KEY is not set"
    echo "ERROR: OPENAI_API_KEY environment variable is required for Codex CLI"
    exit 1
  else
    echo "✅ OPENAI_API_KEY is set"
  fi
  
  # Force non-interactive environment and set sandbox to allow writes
  export CODEX_QUIET_MODE=1
  export CODEX_SANDBOX=workspace-write  # Allow writing to workspace
  export CI=1
  export NO_COLOR=1
  export FORCE_COLOR=0
  export OPENAI_NONINTERACTIVE=1
  export NODE_NO_READLINE=1
  export TERM=dumb  # Use 'dumb' terminal to prevent any TTY features
  export GIT_TERMINAL_PROMPT=0
  # Disable landlock sandbox which fails in Docker
  export CODEX_DISABLE_LANDLOCK=1
  export DISABLE_LANDLOCK=1
  export NO_LANDLOCK=1
  export RUST_BACKTRACE=0  # Suppress panic backtraces
  export CODEX_UNSAFE_DISABLE_SANDBOX=1  # Try to completely disable sandboxing
  
  # Write prompt to file for debugging and execution
  echo "$PROMPT_TEXT" > /tmp/codex_prompt.txt
  echo "📝 Prompt written to /tmp/codex_prompt.txt"
  
  # Execute Codex with danger-full-access sandbox (safe in Docker container)
  if [ -f /usr/local/bin/codex ] || command -v codex >/dev/null 2>&1; then
    CODEX_CMD="codex"
    [ -f /usr/local/bin/codex ] && CODEX_CMD="/usr/local/bin/codex"
    echo "Found codex at: $CODEX_CMD"
    
    echo "Executing Codex with danger-full-access sandbox (Docker-safe)..."
    set +e
    $CODEX_CMD exec --sandbox danger-full-access "$PROMPT_TEXT"
    CODEX_EXIT_CODE=$?
    set -e
    
    if [ $CODEX_EXIT_CODE -eq 0 ]; then
      echo "✅ Codex completed successfully"
    else
      echo "❌ Codex failed with exit code: $CODEX_EXIT_CODE"
      echo "Debug info:"
      echo "- Codex location: $CODEX_CMD"
      echo "- Current directory: $(pwd)"
      echo "- Prompt first 100 chars: $(echo "$PROMPT_TEXT" | head -c 100)"
      exit $CODEX_EXIT_CODE
    fi
  else
    echo "ERROR: codex command not found anywhere"
    echo "Please ensure Codex CLI is installed in the container"
    exit 1
  fi
else
  echo "Using Claude CLI..."
  if [ -f /usr/local/bin/claude ]; then
    echo "Found claude at /usr/local/bin/claude"
    # Try non-interactive execution via Node if needed
    if head -1 /usr/local/bin/claude | grep -Eq "#!/usr/bin/env.*node|#!/usr/bin/node"; then
      if command -v node >/dev/null 2>&1; then
        echo "Using --print flag for non-interactive mode..."
        cat /tmp/prompt.txt | node /usr/local/bin/claude --print --allowedTools "Edit,Bash"
        CLAUDE_EXIT_CODE=$?
        echo "Claude Code finished with exit code: $CLAUDE_EXIT_CODE"
        if [ $CLAUDE_EXIT_CODE -ne 0 ]; then
          echo "ERROR: Claude Code failed with exit code $CLAUDE_EXIT_CODE"
          exit $CLAUDE_EXIT_CODE
        fi
      else
        /usr/local/bin/claude < /tmp/prompt.txt
        CLAUDE_EXIT_CODE=$?
        if [ $CLAUDE_EXIT_CODE -ne 0 ]; then
          echo "ERROR: Claude Code failed with exit code $CLAUDE_EXIT_CODE"
          exit $CLAUDE_EXIT_CODE
        fi
      fi
    else
      /usr/local/bin/claude < /tmp/prompt.txt
      CLAUDE_EXIT_CODE=$?
      if [ $CLAUDE_EXIT_CODE -ne 0 ]; then
        echo "ERROR: Claude Code failed with exit code $CLAUDE_EXIT_CODE"
        exit $CLAUDE_EXIT_CODE
      fi
    fi
  elif command -v claude >/dev/null 2>&1; then
    claude < /tmp/prompt.txt
    CLAUDE_EXIT_CODE=$?
    if [ $CLAUDE_EXIT_CODE -ne 0 ]; then
      echo "ERROR: Claude Code failed with exit code $CLAUDE_EXIT_CODE"
      exit $CLAUDE_EXIT_CODE
    fi
  else
    echo "ERROR: claude command not found anywhere"
    which python3 2>/dev/null && echo "python3: available" || echo "python3: not found"
    which node 2>/dev/null && echo "node: available" || echo "node: not found"
    which sh 2>/dev/null && echo "sh: available" || echo "sh: not found"
    exit 1
  fi
fi

# Check for changes (both staged and unstaged)
git add .
if git diff --cached --quiet; then
  echo "ℹ️  No changes made by ${MODEL_CLI^^} - this is a valid outcome"
  echo "The AI tool ran successfully but decided not to make changes"
  echo "=== PATCH START ==="
  echo "No changes were made"
  echo "=== PATCH END ==="
  echo "=== GIT DIFF START ==="
  echo "No changes were made"
  echo "=== GIT DIFF END ==="
  echo "=== CHANGED FILES START ==="
  echo "No files were changed"
  echo "=== CHANGED FILES END ==="
  echo "=== FILE CHANGES START ==="
  echo "No file changes to display"
  echo "=== FILE CHANGES END ==="
  echo "COMMIT_HASH="
else
  # Build commit message prefix and prompt snippet
  MODEL_PREFIX=$(echo "$MODEL_CLI" | awk '{print toupper(substr($0,1,1)) tolower(substr($0,2))}')
  PROMPT_SNIPPET=$(printf "%s" "$PROMPT_TEXT" | head -c 100 | tr -d '\n')
  git commit -m "${MODEL_PREFIX}: ${PROMPT_SNIPPET}"

  COMMIT_HASH=$(git rev-parse HEAD)
  echo "COMMIT_HASH=$COMMIT_HASH"

  echo "📦 Generating patch file..."
  git format-patch HEAD~1 --stdout > /tmp/changes.patch
  echo "=== PATCH START ==="
  cat /tmp/changes.patch
  echo "=== PATCH END ==="

  echo "=== GIT DIFF START ==="
  git diff HEAD~1 HEAD
  echo "=== GIT DIFF END ==="

  echo "=== CHANGED FILES START ==="
  git diff --name-only HEAD~1 HEAD
  echo "=== CHANGED FILES END ==="

  echo "=== FILE CHANGES START ==="
  for file in $(git diff --name-only HEAD~1 HEAD); do
    echo "FILE: $file"
    echo "=== BEFORE START ==="
    git show HEAD~1:"$file" 2>/dev/null || echo "FILE_NOT_EXISTS"
    echo "=== BEFORE END ==="
    echo "=== AFTER START ==="
    cat "$file" 2>/dev/null || echo "FILE_DELETED"
    echo "=== AFTER END ==="
    echo "=== FILE END ==="
  done
  echo "=== FILE CHANGES END ==="
fi

echo "Container work completed successfully"
exit 0


