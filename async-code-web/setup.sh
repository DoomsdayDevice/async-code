#!/bin/bash

# setup.sh - Sandbox environment setup script
echo "🚀 Starting sandbox environment setup..."

# Set environment to development if not already set
export NODE_ENV=${NODE_ENV:-development}

# Install any additional dependencies if needed
echo "📦 Installing dependencies..."
npm install

# Run any database migrations or setup commands here
# Example:
# npm run db:migrate
# npm run db:seed

# Build the application if needed
echo "🔨 Building the application..."
npm run build 2>/dev/null || echo "⚠️  No build script found, skipping build step"

# Start the development server
echo "🌟 Starting the development server..."
echo "🎉 Sandbox environment is ready!"

# Start the application (adjust command based on your package.json scripts)
if npm run dev >/dev/null 2>&1; then
    npm run dev
elif npm start:prod >/dev/null 2>&1; then
    npm start:prod
else
    echo "⚠️  No dev or start script found in package.json"
    echo "🔧 Starting Node.js directly..."
    node server.js 2>/dev/null || node index.js 2>/dev/null || echo "❌ No entry point found"
fi 