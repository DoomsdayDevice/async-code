.PHONY: deps build test-api test-model-selection

deps:
	@echo "Starting only Postgres via docker-compose..."
	docker-compose up -d postgres

build:
	@echo "🚀 Building Code Automation MVP (Claude + Codex)..."
	@if [ ! -f server/.env ]; then \
		echo "📝 Creating .env file from example..."; \
		cp server/.env.example server/.env; \
		echo "⚠️  Please edit server/.env with your actual API keys"; \
	fi
	@echo "🔨 Building Claude Code automation image..."
	@docker build -f Dockerfile.claude-automation -t claude-code-automation:latest . || exit 1
	@echo "🔨 Building Codex automation image..."
	@docker build -f Dockerfile.codex-automation -t codex-automation:latest . || exit 1
	@echo "🔨 Building and starting all services..."
	@docker-compose up --build -d
	@echo "✅ Build complete!"
	@echo ""
	@echo "🌐 Frontend: http://localhost:9020"
	@echo "🔧 Backend API: http://localhost:9010"
	@echo ""
	@echo "⚠️  Don't forget to:"
	@echo "1. Set your ANTHROPIC_API_KEY in server/.env"
	@echo "2. Get a GitHub personal access token for the frontend"
	@echo ""
	@echo "📖 Check the logs with: docker-compose logs -f"

test-api:
	@echo "🧪 Testing Claude Code Automation API..."
	@API_BASE="http://localhost:5000"; \
	echo "📋 Testing health check..."; \
	curl -s "$$API_BASE/ping" | jq . || echo "❌ Health check failed"; \
	echo "📋 Testing root endpoint..."; \
	curl -s "$$API_BASE/" | jq . || echo "❌ Root endpoint failed"; \
	echo ""; \
	echo "✅ Basic API tests completed"; \
	echo "💡 For full testing, you'll need:"; \
	echo "  1. Anthropic API key in server/.env"; \
	echo "  2. GitHub token for task creation"; \
	echo "  3. A target repository URL"

test-model-selection:
	@echo "Testing Model Selection API..."; \
	echo "Testing Claude Code model..."; \
	curl -X POST http://localhost:5000/start-task \
	  -H "Content-Type: application/json" \
	  -d '{ \
	    "prompt": "Add a test comment to README", \
	    "repo_url": "https://github.com/test/repo", \
	    "branch": "main", \
	    "github_token": "test_token", \
	    "model": "claude" \
	  }'; \
	printf "\n\n"; \
	echo "Testing Codex CLI model..."; \
	curl -X POST http://localhost:5000/start-task \
	  -H "Content-Type: application/json" \
	  -d '{ \
	    "prompt": "Add a test comment to README", \
	    "repo_url": "https://github.com/test/repo", \
	    "branch": "main", \
	    "github_token": "test_token", \
	    "model": "codex" \
	  }'; \
	printf "\n\n"; \
	echo "Testing invalid model..."; \
	curl -X POST http://localhost:5000/start-task \
	  -H "Content-Type: application/json" \
	  -d '{ \
	    "prompt": "Add a test comment to README", \
	    "repo_url": "https://github.com/test/repo", \
	    "branch": "main", \
	    "github_token": "test_token", \
	    "model": "invalid_model" \
	  }'

