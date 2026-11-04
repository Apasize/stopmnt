FROM python:3.11-alpine

RUN apk add --no-cache gcc musl-dev libffi-dev openssl-dev

RUN addgroup -S stopmnt && adduser -S stopmnt -G stopmnt

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R stopmnt:stopmnt /app

USER stopmnt

CMD ["python3", "-u", "worker.py"]
