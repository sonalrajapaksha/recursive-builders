# Build: docker build --platform linux/amd64 -t rb-bot .   (map is mounted at /arena at runtime)
FROM python:3.13-slim
WORKDIR /bot
COPY *.py /bot/
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
