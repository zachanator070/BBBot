FROM python:3.7

RUN apt update
RUN apt install -y firefox-esr wget

RUN wget https://github.com/mozilla/geckodriver/releases/download/v0.28.0/geckodriver-v0.28.0-linux32.tar.gz
RUN tar -xzf geckodriver-v0.28.0-linux32.tar.gz
RUN mv geckodriver /usr/bin

RUN mkdir /home/bot
WORKDIR /home/bot
ADD requirements.txt .
RUN pip install -r requirements.txt
ADD bot.py .
ADD .env .

CMD ["python", "bot.py"]
