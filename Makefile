.PHONY: help install kafka-up kafka-down topics deploy simulate ingest dashboard test clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n",$$1,$$2}'

install:  ## Create venv and install dependencies
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

kafka-up:  ## Start local Kafka stack
	docker compose up -d

kafka-down:  ## Stop local Kafka stack
	docker compose down

topics:  ## Create Kafka topics
	bash scripts/create_topics.sh

deploy:  ## Provision all Snowflake objects
	bash scripts/deploy_snowflake.sh

simulate:  ## Stream synthetic broker traffic into Kafka (RATE msgs/sec)
	python kafka/producers/broker_simulator.py --rate $(or $(RATE),5)

ingest:  ## Consume Kafka and stream into Snowflake (Snowpipe Streaming)
	python ingestion/snowpipe_streaming.py

dashboard:  ## Launch the Streamlit dashboard + AI agent
	streamlit run dashboard/app.py

test:  ## Run unit tests
	pytest -q

clean:  ## Remove caches
	find . -type d -name __pycache__ -exec rm -rf {} + ; rm -rf .pytest_cache
