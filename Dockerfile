FROM python:3.7

RUN apt update
RUN apt install -y firefox-esr

ADD geckodriver /usr/bin
RUN mkdir /home/bot
WORKDIR /home/bot
ADD requirements.txt .
RUN pip install -r requirements.txt
ADD bot.py .
ADD .env .

CMD ["python", "bot.py"]
