
run:
	docker build -t bb_bot .
	docker run -v ${PWD}/logs:/home/bot/logs bb_bot
