### Requirements

* Best Buy Account
* Credit card entered in Best Buy Account and set as default

also

* Python 3.7 
or
* Docker

### Usage

Create a file named `.env` in this directory with the same contents as the `.env-example` provided in this repo.

Fill out the variables in the `.env` file to the correct values.


If using Docker use the command:

```make```

or

```
docker build -t 3080_bot .
docker run 3080_bot
```


If not using docker run the python script bot.py with the command:

```python bot.py```


If using an IDE, create a run target or run configuration for `bot.py` and press the run button
