#!/bin/bash

echo "🚀 Building Code Automation MVP (Claude + Codex)..."

# Create .env file if it doesn't exist
if [ ! -f server/.env ]; then
    echo "📝 Creating .env file from example..."
    cp server/.env.example server/.env
    echo "⚠️  Please edit server/.env with your actual API keys"
fi

# Build the automation images first to avoid runtime pulls
echo "🔨 Building Claude Code automation image..."
docker build -f Dockerfile.claude-automation -t claude-code-automation:latest . || exit 1

echo "🔨 Building Codex automation image..."
docker build -f Dockerfile.codex-automation -t codex-automation:latest . || exit 1

# Build and start all services
echo "🔨 Building and starting all services..."
docker-compose up --build -d

echo "✅ Build complete!"
echo ""
echo "🌐 Frontend: http://localhost:9020"
echo "🔧 Backend API: http://localhost:9010"
echo ""
echo "⚠️  Don't forget to:"
echo "1. Set your ANTHROPIC_API_KEY in server/.env"
echo "2. Get a GitHub personal access token for the frontend"
echo ""
echo "📖 Check the logs with: docker-compose logs -f"