.PHONY: setup dev build test deploy clean status prompt-test help

help: ## Show all available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies and configure environment
	@echo "TODO: Add setup commands for your tech stack (npm install, pip install, etc.)"
	@cp -n .env.example .env 2>/dev/null || true
	@echo "Setup complete. Edit .env with your API keys and configuration."

dev: ## Start development server
	@echo "TODO: Add dev server command (npm run dev, python manage.py runserver, etc.)"

build: ## Build for production
	@echo "TODO: Add build command (npm run build, etc.)"

test: ## Run all tests
	@echo "TODO: Add test command (npm test, pytest, etc.)"

deploy: ## Deploy to production
	@echo "TODO: Add deploy command"

clean: ## Remove build artifacts and caches
	@echo "TODO: Add clean commands (rm -rf dist, rm -rf __pycache__, etc.)"

status: ## Show project status from docs
	@echo "=== PROJECT STATUS ==="
	@echo ""
	@echo "--- Tasks ---"
	@cat docs/TASK_PIPELINE.md 2>/dev/null | grep -E "^\|" | tail -n +3 || echo "No tasks found"
	@echo ""
	@echo "--- Tech Stack ---"
	@cat docs/TECH_STACK.md 2>/dev/null | grep -E "^\|" | tail -n +3 || echo "No stack found"
	@echo ""
	@echo "--- Last Session ---"
	@head -20 docs/SESSION_LOG.md 2>/dev/null || echo "No session log"
	@echo "===================="

prompt-test: ## Run prompt test cases (update path to your test runner)
	@echo "TODO: Add prompt testing command"
	@echo "Example: node scripts/test-prompts.js or python scripts/test_prompts.py"
