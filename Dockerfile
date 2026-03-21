# Railway подхватывает Dockerfile только из корня репозитория (или Root Directory сервиса).
# Копия логики из docker/Dockerfile — при изменениях синхронизируйте оба файла или оставьте один источник.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["python", "-m", "app.main"]
